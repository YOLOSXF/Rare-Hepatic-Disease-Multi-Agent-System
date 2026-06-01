"""
四级级联检索管道

移植自 MedGraphRAG:
- nano_graphrag/_op.py → _build_local_query_context() (L596-687): 级联检索管道
- nano_graphrag/_op.py → _find_most_related_edges_from_entities() (L562-593): 1-hop图扩展
- nano_graphrag/_utils.py → truncate_list_by_token_size() (L35-42): Token预算截断

移植自 MedRAG:
- KG_Retrieve.py → find_closest_category() (L150-197): 投票排序逻辑

适配改造:
- NetworkX图遍历 → Neo4j Cypher查询
- tiktoken → 中文0.75字/token估算
- 通用实体类型 → 罕见肝病KG Schema (EL1-EL4)
- 通用关系 → 8种诊断KG关系类型

四级管道:
Stage 1: Milvus向量粗排 → Stage 2: Neo4j 1-hop图扩展 →
Stage 3: 投票排序 → Stage 4: 差异KG + 指南溯源

使用示例:
    from core.kg.kg_retriever import KGRetriever
    retriever = KGRetriever()
    result = retriever.retrieve(patient_data={"symptoms": ["黄疸", "腹水"]})
"""

import time
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Tuple

from loguru import logger

from core.kg.kg_config import KGConfig
from core.kg.kg_schema import (
    CandidateDisease,
    DiagnosticDifference,
    KGRetrievalResult,
    RelevantEntity,
    RelevantRelation,
    SourceCitation,
)


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    others = len(text) - chinese_chars
    return int(chinese_chars / 0.75 + others / 2.5)


class KGRetriever:
    def __init__(self, config: Optional[KGConfig] = None):
        self.config = config or KGConfig.from_yaml()
        self._neo4j_driver = None
        self._embedder = None

    def _get_neo4j_driver(self):
        if self._neo4j_driver is None:
            self._neo4j_driver = self.config.get_neo4j_driver()
        return self._neo4j_driver

    def _get_embedder(self):
        if self._embedder is None:
            from core.kg.kg_embedder import KGEmbedder
            self._embedder = KGEmbedder(config=self.config)
        return self._embedder

    def _run_neo4j_query(self, query: str, params: Optional[Dict] = None) -> List[Dict]:
        driver = self._get_neo4j_driver()
        with driver.session(database=self.config.neo4j.database) as session:
            result = session.run(query, params or {})
            return [record.data() for record in result]

    def retrieve(
        self,
        patient_data: Dict,
        triage_hint: Optional[str] = None,
    ) -> KGRetrievalResult:
        start_time = time.time()
        logger.info(f"KGRetriever: starting retrieval, triage_hint={triage_hint}")

        queries = self._extract_queries(patient_data)
        if not queries:
            logger.warning("KGRetriever: no queries extracted from patient_data")
            return KGRetrievalResult(retrieval_latency_ms=0.0)

        logger.info(f"KGRetriever: extracted {len(queries)} queries")

        matched_entities, guideline_chunks = self._vector_search(
            queries, top_k=self.config.retrieval.vector_top_k
        )
        if not matched_entities:
            logger.warning("KGRetriever: vector search returned no results")
            return KGRetrievalResult(retrieval_latency_ms=0.0)

        logger.info(f"KGRetriever: vector search returned {len(matched_entities)} KG entities, {len(guideline_chunks)} guideline chunks")

        kg_entity_ids = [
            e.get("entity_name", "")
            for e in matched_entities
            if e.get("entity_name") and e.get("entity_type") in ("Feature", "Disease", "LabTest", "Gene", "Phenotype")
        ]

        if triage_hint:
            filtered = self._apply_triage_filter(kg_entity_ids, triage_hint)
            if filtered:
                kg_entity_ids = filtered
                logger.info(f"KGRetriever: triage filter reduced to {len(kg_entity_ids)} entities")

        expanded_relations = self._graph_expand(kg_entity_ids)
        logger.info(f"KGRetriever: graph expand returned {len(expanded_relations)} relations")

        candidates = self._vote_and_rank(matched_entities, expanded_relations)
        logger.info(f"KGRetriever: vote and rank produced {len(candidates)} candidates")

        differentials = self._fetch_differentials(candidates)
        citations = self._fetch_citations(candidates, guideline_chunks)

        relevant_entities = self._build_relevant_entities(matched_entities)
        relevant_relations = self._build_relevant_relations(expanded_relations)

        relevant_entities = self._truncate_by_token_size(
            relevant_entities,
            key_fn=lambda e: f"{e.name} {e.description or ''}",
            max_tokens=self.config.retrieval.max_context_tokens // 2,
        )
        relevant_relations = self._truncate_by_token_size(
            relevant_relations,
            key_fn=lambda r: f"{r.source} {r.relation_type} {r.target}",
            max_tokens=self.config.retrieval.max_context_tokens // 4,
        )

        latency_ms = (time.time() - start_time) * 1000
        logger.info(f"KGRetriever: retrieval complete in {latency_ms:.1f}ms")

        return KGRetrievalResult(
            candidate_diseases=candidates,
            diagnostic_differences=differentials,
            relevant_entities=relevant_entities,
            relevant_relations=relevant_relations,
            source_citations=citations,
            retrieval_latency_ms=latency_ms,
            degradation_level=1,
        )

    def _extract_queries(self, patient_data: Dict) -> List[str]:
        queries = []

        symptoms = patient_data.get("symptoms", [])
        if symptoms:
            if isinstance(symptoms, dict):
                active = [k for k, v in symptoms.items() if v]
                if active:
                    queries.append(" ".join(active))
            elif isinstance(symptoms, list):
                queries.append(" ".join(str(s) for s in symptoms))
            else:
                queries.append(str(symptoms))

        labs = patient_data.get("labs", {})
        if labs:
            if isinstance(labs, dict):
                lab_parts = []
                for k, v in labs.items():
                    if v is not None:
                        lab_parts.append(f"{k}{v}")
                if lab_parts:
                    queries.append(" ".join(lab_parts))
            elif isinstance(labs, list):
                queries.append(" ".join(str(l) for l in labs))
            else:
                queries.append(str(labs))

        abnormal_labs = patient_data.get("abnormal_labs", [])
        if abnormal_labs:
            if isinstance(abnormal_labs, list):
                queries.append(" ".join(str(l) for l in abnormal_labs))
            else:
                queries.append(str(abnormal_labs))

        imaging = patient_data.get("imaging_findings", [])
        if imaging:
            if isinstance(imaging, list):
                queries.append(" ".join(str(i) for i in imaging))
            else:
                queries.append(str(imaging))

        imaging_results = patient_data.get("imaging_results", {})
        if imaging_results:
            if isinstance(imaging_results, dict):
                img_parts = [f"{k}: {v}" for k, v in imaging_results.items() if v]
                if img_parts:
                    queries.append(" ".join(img_parts))
            else:
                queries.append(str(imaging_results))

        clinical_notes = patient_data.get("clinical_notes", "")
        if clinical_notes:
            queries.append(str(clinical_notes))

        chief_complaint = patient_data.get("chief_complaint", "")
        if chief_complaint:
            queries.append(str(chief_complaint))

        history = patient_data.get("history", {})
        if history:
            if isinstance(history, dict):
                hist_parts = [f"{k}: {v}" for k, v in history.items() if v]
                if hist_parts:
                    queries.append(" ".join(hist_parts))
            else:
                queries.append(str(history))

        queries = [q.strip() for q in queries if q and str(q).strip()]
        return queries

    def _vector_search(self, queries: List[str], top_k: int = 20) -> Tuple[List[Dict], List[Dict]]:
        embedder = self._get_embedder()
        all_results = []
        seen_names = set()

        threshold = self.config.activation.similarity_threshold

        for query in queries:
            try:
                results = embedder.search(query, top_k=top_k * 2)
                for r in results:
                    name = r.get("entity_name", "")
                    distance = r.get("distance", 0.0)
                    similarity = 1.0 - distance
                    if similarity < threshold:
                        continue
                    if name not in seen_names:
                        seen_names.add(name)
                        r["similarity"] = similarity
                        all_results.append(r)
            except Exception as e:
                logger.warning(f"Vector search failed for query '{query[:50]}': {e}")

        kg_entity_types = ("Feature", "Disease", "LabTest", "Gene", "Phenotype")
        kg_entities = [r for r in all_results if r.get("entity_type") in kg_entity_types]
        guideline_chunks = [r for r in all_results if r.get("entity_type") == "GuidelineChunk"]

        kg_entities.sort(key=lambda x: x.get("similarity", 0.0), reverse=True)

        return kg_entities[:top_k], guideline_chunks

    def _graph_expand(self, entity_ids: List[str]) -> List[Dict]:
        if not entity_ids:
            return []

        limit = self.config.retrieval.graph_expand_limit

        query = """
        MATCH (e)-[r]-(neighbor)
        WHERE e.name IN $entity_ids OR e.id IN $entity_ids
        RETURN e.name AS source_name, e.id AS source_id,
               type(r) AS rel_type,
               coalesce(neighbor.name, neighbor.id) AS target_name,
               coalesce(neighbor.id, neighbor.name) AS target_id,
               labels(neighbor)[0] AS target_label,
               neighbor.layer AS target_layer,
               neighbor.is_core AS is_core,
               coalesce(r.weight, 1.0) AS weight,
               coalesce(r.strength, 'moderate') AS strength
        ORDER BY weight DESC
        LIMIT $limit
        """

        try:
            results = self._run_neo4j_query(query, {
                "entity_ids": entity_ids,
                "limit": limit,
            })
        except Exception as e:
            logger.warning(f"Graph expand failed: {e}")
            return []

        return results

    def _apply_triage_filter(
        self, entity_ids: List[str], triage_hint: str
    ) -> List[str]:
        query = """
        MATCH (e)-[:IS_A]->(cat)
        WHERE (e.name IN $entity_ids OR e.id IN $entity_ids)
          AND cat.layer = 'EL2'
          AND (cat.name CONTAINS $hint OR cat.id CONTAINS $hint)
        RETURN DISTINCT e.name AS name, e.id AS id
        """
        try:
            results = self._run_neo4j_query(query, {
                "entity_ids": entity_ids,
                "hint": triage_hint,
            })
            return [r.get("name") or r.get("id", "") for r in results if r.get("name") or r.get("id")]
        except Exception as e:
            logger.warning(f"Triage filter failed: {e}")
            return entity_ids

    def _vote_and_rank(
        self,
        entities: List[Dict],
        relations: List[Dict],
    ) -> List[CandidateDisease]:
        disease_votes: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"name": "", "score": 0.0, "matched_features": []}
        )

        core_weight = self.config.activation.core_feature_weight
        supporting_weight = self.config.activation.supporting_feature_weight

        for rel in relations:
            target_name = rel.get("target_name", "")
            target_label = rel.get("target_label", "")
            source_name = rel.get("source_name", "")
            rel_type = rel.get("rel_type", "")
            is_core = rel.get("is_core", False)

            if target_label == "Disease" and rel_type in (
                "HAS_MANIFESTATION", "HAS_DIAGNOSTIC_KEY",
            ):
                weight = core_weight if is_core else supporting_weight
                disease_votes[target_name]["name"] = target_name
                disease_votes[target_name]["score"] += weight
                disease_votes[target_name]["matched_features"].append({
                    "feature": source_name,
                    "is_core": is_core,
                    "weight": weight,
                    "relation": rel_type,
                })

        for entity in entities:
            entity_name = entity.get("entity_name", "")
            entity_type = entity.get("entity_type", "")
            similarity = entity.get("similarity", 0.0)

            if entity_type == "Disease":
                disease_votes[entity_name]["name"] = entity_name
                disease_votes[entity_name]["score"] += similarity * supporting_weight

        query = """
        MATCH (f:Feature)-[:HAS_MANIFESTATION|HAS_DIAGNOSTIC_KEY]->(d:Disease)
        WHERE f.name IN $feature_names OR f.id IN $feature_names
        RETURN d.name AS disease_name, d.id AS disease_id
        """
        feature_names = [e.get("entity_name", "") for e in entities if e.get("entity_type") == "Feature"]
        if feature_names:
            try:
                disease_results = self._run_neo4j_query(query, {"feature_names": feature_names})
                for r in disease_results:
                    dname = r.get("disease_name", "")
                    if dname:
                        disease_votes[dname]["name"] = dname
                        disease_votes[dname]["score"] += supporting_weight
            except Exception as e:
                logger.warning(f"Feature-to-disease lookup failed: {e}")

        candidates = []
        for disease_name, data in disease_votes.items():
            if data["score"] > 0:
                candidates.append(CandidateDisease(
                    disease_id=disease_name,
                    name=data["name"] or disease_name,
                    score=data["score"],
                    matched_features=data["matched_features"],
                ))

        candidates.sort(key=lambda c: c.score, reverse=True)
        top_k = self.config.activation.top_k_diseases
        return candidates[:top_k]

    def _fetch_differentials(
        self, candidates: List[CandidateDisease],
    ) -> List[DiagnosticDifference]:
        if not candidates:
            return []

        disease_ids = [c.disease_id for c in candidates]
        query = """
        MATCH (d1:Disease)-[r:DIFFERENTIAL_FROM]-(d2:Disease)
        WHERE d1.name IN $disease_ids OR d1.id IN $disease_ids
        RETURN d1.name AS disease_a, d2.name AS disease_b,
               r.distinguishing_features AS distinguishing,
               r.overlap_features AS overlap,
               r.difficulty AS difficulty
        """
        try:
            results = self._run_neo4j_query(query, {"disease_ids": disease_ids})
        except Exception as e:
            logger.warning(f"Fetch differentials failed: {e}")
            return []

        diffs = []
        for r in results:
            disease_a = r.get("disease_a", "")
            disease_b = r.get("disease_b", "")
            if not disease_a or not disease_b:
                continue
            distinguishing = r.get("distinguishing", [])
            if isinstance(distinguishing, str):
                distinguishing = [d.strip() for d in distinguishing.split(",") if d.strip()]
            overlap = r.get("overlap", [])
            if isinstance(overlap, str):
                overlap = [o.strip() for o in overlap.split(",") if o.strip()]
            diffs.append(DiagnosticDifference(
                disease_pair=f"{disease_a} vs {disease_b}",
                key_features=distinguishing,
                overlap_features=overlap,
                difficulty=r.get("difficulty"),
            ))
        return diffs

    def _fetch_citations(
        self, candidates: List[CandidateDisease],
        guideline_chunks: List[Dict],
    ) -> List[SourceCitation]:
        if not candidates:
            return []

        disease_ids = [c.disease_id for c in candidates]
        query = """
        MATCH (d:Disease)-[:GUIDED_BY]->(g:ClinicalGuideline)
        WHERE d.name IN $disease_ids OR d.id IN $disease_ids
        RETURN d.name AS disease, g.title AS guideline,
               g.organization AS organization, g.year AS year
        """
        try:
            results = self._run_neo4j_query(query, {"disease_ids": disease_ids})
        except Exception as e:
            logger.warning(f"Fetch citations failed: {e}")
            return []

        chunk_by_guideline: Dict[str, List[Dict]] = defaultdict(list)
        for gc in guideline_chunks:
            src = gc.get("source_guideline", "")
            if src:
                chunk_by_guideline[src].append(gc)

        citations = []
        seen = set()
        for r in results:
            guideline = r.get("guideline", "")
            if not guideline or guideline in seen:
                continue
            seen.add(guideline)
            org = r.get("organization", "")
            year = r.get("year", "")
            section = f"{org} {year}".strip() if org or year else None

            evidence_text = None
            matching_chunks = chunk_by_guideline.get(guideline, [])
            if matching_chunks:
                matching_chunks.sort(key=lambda x: x.get("similarity", 0.0), reverse=True)
                evidence_text = matching_chunks[0].get("description", "")

            citations.append(SourceCitation(
                guideline=guideline,
                section=section,
                evidence_text=evidence_text,
            ))
        return citations

    def _build_relevant_entities(self, matched_entities: List[Dict]) -> List[RelevantEntity]:
        entities = []
        seen = set()
        for e in matched_entities:
            name = e.get("entity_name", "")
            if name in seen:
                continue
            seen.add(name)
            entities.append(RelevantEntity(
                name=name,
                entity_type=e.get("entity_type", ""),
                description=e.get("description", ""),
                source=e.get("source_guideline", ""),
            ))
        return entities

    def _build_relevant_relations(self, relations: List[Dict]) -> List[RelevantRelation]:
        result = []
        seen = set()
        for r in relations:
            source = r.get("source_name", "")
            target = r.get("target_name", "")
            rel_type = r.get("rel_type", "")
            key = f"{source}|{rel_type}|{target}"
            if key in seen:
                continue
            seen.add(key)
            weight = r.get("weight", 1.0)
            strength = r.get("strength", "moderate")
            strength_map = {"strong": 2.0, "moderate": 1.0, "weak": 0.5}
            strength_val = strength_map.get(strength, 1.0) if isinstance(strength, str) else float(weight)
            result.append(RelevantRelation(
                source=source,
                target=target,
                relation_type=rel_type,
                strength=strength_val,
            ))
        return result

    def _truncate_by_token_size(
        self,
        items: List,
        key_fn: Callable,
        max_tokens: int,
    ) -> List:
        tokens = 0
        for i, item in enumerate(items):
            tokens += _estimate_tokens(key_fn(item))
            if tokens > max_tokens:
                return items[:i]
        return items

    def close(self) -> None:
        if self._neo4j_driver is not None:
            self._neo4j_driver.close()
            self._neo4j_driver = None
        if self._embedder is not None:
            self._embedder.close()
            self._embedder = None
