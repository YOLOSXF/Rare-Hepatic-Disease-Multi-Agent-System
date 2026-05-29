"""
统一查询API + 三级降级策略

移植自 MedGraphRAG:
- retrieve.py → seq_ret() (L7-41): LLM降级检索
- utils.py → ret_context() (L150-171): 子图检索上下文
- utils.py → link_context() (L121-148): 跨层链接上下文

适配改造:
- Neo4j Python Driver → 本项目KGConfig连接
- REFERENCE关系 → GUIDED_BY关系
- Summary节点 → ClinicalGuideline节点
- 增加三级降级检测和自动切换

三级降级策略:
Level 1: Neo4j+Milvus均可用 → 完整四级管道
Level 2: Neo4j不可用，Milvus可用 → Milvus纯向量检索
Level 3: Milvus也不可用 → LLM降级检索

使用示例:
    from core.kg.kg_interface import KGInterface
    interface = KGInterface()
    if interface.is_enabled():
        result, activations = interface.retrieve_and_classify(patient_data)
"""

import time
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from core.kg.kg_config import KGConfig
from core.kg.kg_schema import (
    ActivationResult,
    CandidateDisease,
    KGRetrievalResult,
    RelevantEntity,
    SourceCitation,
)


_DEFAULT_LLM_SCORE_PROMPT = """评估以下医学实体描述与患者数据的相似度，返回1-5分的评分：
5分: 非常相关，直接描述了患者的症状或检验结果
4分: 相关，与患者情况有较强关联
3分: 一般相关，存在一定关联
2分: 不太相关，关联较弱
1分: 完全不相关

只返回数字评分，不要返回其他内容。"""


class KGInterface:
    def __init__(self, config: Optional[KGConfig] = None):
        self.config = config or KGConfig.from_yaml()
        self._retriever = None
        self._classifier = None
        self._embedder = None
        self._neo4j_driver = None
        self._degradation_level: Optional[int] = None

    def _get_retriever(self):
        if self._retriever is None:
            from core.kg.kg_retriever import KGRetriever
            self._retriever = KGRetriever(config=self.config)
        return self._retriever

    def _get_classifier(self):
        if self._classifier is None:
            from core.kg.kg_classifier import KGClassifier
            self._classifier = KGClassifier(config=self.config)
        return self._classifier

    def _get_embedder(self):
        if self._embedder is None:
            from core.kg.kg_embedder import KGEmbedder
            self._embedder = KGEmbedder(config=self.config)
        return self._embedder

    def _get_neo4j_driver(self):
        if self._neo4j_driver is None:
            self._neo4j_driver = self.config.get_neo4j_driver()
        return self._neo4j_driver

    def _run_neo4j_query(self, query: str, params: Optional[Dict] = None) -> List[Dict]:
        driver = self._get_neo4j_driver()
        with driver.session(database=self.config.neo4j.database) as session:
            result = session.run(query, params or {})
            return [record.data() for record in result]

    def is_enabled(self) -> bool:
        return self.config.enabled

    def retrieve_and_classify(
        self,
        patient_data: Dict,
        triage_hint: Optional[str] = None,
    ) -> Tuple[KGRetrievalResult, List[ActivationResult]]:
        if not self.is_enabled():
            logger.info("KGInterface: KG disabled, returning empty results")
            return KGRetrievalResult(), []

        level = self._detect_degradation_level()
        logger.info(f"KGInterface: degradation level = {level}")

        if level == 1:
            retrieval_result = self._retrieve_level1(patient_data, triage_hint)
        elif level == 2:
            retrieval_result = self._retrieve_level2(patient_data)
        else:
            retrieval_result = self._retrieve_level3(patient_data)

        retrieval_result.degradation_level = level

        if level == 1 and retrieval_result.candidate_diseases:
            classifier = self._get_classifier()
            activation_results = classifier.classify(patient_data, retrieval_result)
        else:
            activation_results = self._build_simple_activations(retrieval_result)

        return retrieval_result, activation_results

    def _detect_degradation_level(self) -> int:
        if self._degradation_level is not None:
            return self._degradation_level

        neo4j_ok = False
        milvus_ok = False

        timeout = self.config.degradation.neo4j_timeout_ms / 1000.0
        try:
            driver = self.config.get_neo4j_driver()
            with driver.session(database=self.config.neo4j.database) as session:
                session.run("RETURN 1")
            driver.close()
            neo4j_ok = True
        except Exception as e:
            logger.warning(f"Neo4j not available: {e}")

        try:
            embedder = self._get_embedder()
            client = embedder._get_milvus_client()
            collections = client.list_collections()
            if self.config.milvus.collection_name in collections:
                milvus_ok = True
            else:
                logger.warning(
                    f"Milvus collection '{self.config.milvus.collection_name}' not found"
                )
        except Exception as e:
            logger.warning(f"Milvus not available: {e}")

        if neo4j_ok and milvus_ok:
            level = 1
        elif milvus_ok:
            level = 2
        else:
            level = 3

        self._degradation_level = level
        return level

    def reset_degradation(self) -> None:
        self._degradation_level = None

    def _retrieve_level1(
        self,
        patient_data: Dict,
        triage_hint: Optional[str] = None,
    ) -> KGRetrievalResult:
        retriever = self._get_retriever()
        return retriever.retrieve(patient_data, triage_hint=triage_hint)

    def _retrieve_level2(self, patient_data: Dict) -> KGRetrievalResult:
        logger.info("KGInterface: Level 2 - Milvus-only retrieval")
        start_time = time.time()

        embedder = self._get_embedder()
        queries = self._extract_queries(patient_data)
        if not queries:
            return KGRetrievalResult(degradation_level=2)

        all_entities = []
        seen = set()
        for query in queries:
            try:
                results = embedder.search(
                    query, top_k=self.config.retrieval.vector_top_k
                )
                for r in results:
                    name = r.get("entity_name", "")
                    if name and name not in seen:
                        seen.add(name)
                        all_entities.append(r)
            except Exception as e:
                logger.warning(f"Level 2 vector search failed: {e}")

        candidates = []
        for e in all_entities:
            if e.get("entity_type") == "Disease":
                similarity = 1.0 - e.get("distance", 1.0)
                candidates.append(CandidateDisease(
                    disease_id=e.get("entity_name", ""),
                    name=e.get("entity_name", ""),
                    score=similarity,
                    matched_features=[],
                ))

        candidates.sort(key=lambda c: c.score, reverse=True)
        top_k = self.config.activation.top_k_diseases
        candidates = candidates[:top_k]

        relevant_entities = [
            RelevantEntity(
                name=e.get("entity_name", ""),
                entity_type=e.get("entity_type", ""),
                description=e.get("description", ""),
                source=e.get("source_guideline", ""),
            )
            for e in all_entities
        ]

        latency_ms = (time.time() - start_time) * 1000
        return KGRetrievalResult(
            candidate_diseases=candidates,
            relevant_entities=relevant_entities,
            retrieval_latency_ms=latency_ms,
            degradation_level=2,
        )

    def _retrieve_level3(self, patient_data: Dict) -> KGRetrievalResult:
        logger.info("KGInterface: Level 3 - LLM degradation retrieval")
        start_time = time.time()

        embedder = self._get_embedder()
        queries = self._extract_queries(patient_data)
        if not queries:
            return KGRetrievalResult(degradation_level=3)

        try:
            all_entities = []
            seen = set()
            for query in queries:
                results = embedder.search(query, top_k=10)
                for r in results:
                    name = r.get("entity_name", "")
                    if name and name not in seen:
                        seen.add(name)
                        all_entities.append(r)
        except Exception as e:
            logger.warning(f"Level 3 Milvus search also failed: {e}")
            return KGRetrievalResult(degradation_level=3)

        if not all_entities:
            return KGRetrievalResult(degradation_level=3)

        patient_text = self._patient_data_to_text(patient_data)
        scored_entities = self._llm_score_entities(all_entities, patient_text)

        candidates = []
        for e in scored_entities:
            if e.get("entity_type") == "Disease" and e.get("llm_score", 0) >= 3:
                candidates.append(CandidateDisease(
                    disease_id=e.get("entity_name", ""),
                    name=e.get("entity_name", ""),
                    score=float(e.get("llm_score", 0)) / 5.0,
                    matched_features=[],
                ))

        candidates.sort(key=lambda c: c.score, reverse=True)
        top_k = self.config.activation.top_k_diseases
        candidates = candidates[:top_k]

        relevant_entities = [
            RelevantEntity(
                name=e.get("entity_name", ""),
                entity_type=e.get("entity_type", ""),
                description=e.get("description", ""),
            )
            for e in scored_entities
            if e.get("llm_score", 0) >= 3
        ]

        latency_ms = (time.time() - start_time) * 1000
        return KGRetrievalResult(
            candidate_diseases=candidates,
            relevant_entities=relevant_entities,
            retrieval_latency_ms=latency_ms,
            degradation_level=3,
        )

    def _llm_score_entities(
        self, entities: List[Dict], patient_text: str,
    ) -> List[Dict]:
        prompt_template = self.config.degradation.llm_score_prompt or _DEFAULT_LLM_SCORE_PROMPT

        try:
            from openai import OpenAI
            client = OpenAI(
                api_key="dummy",
                base_url=self.config.neo4j.url.replace("bolt://", "http://").replace(":7687", ":8088/v1")
                if ":7687" in self.config.neo4j.url else None,
            )
        except Exception:
            logger.warning("OpenAI client not available for Level 3 scoring")
            return entities

        scored = []
        for e in entities:
            name = e.get("entity_name", "")
            desc = e.get("description", "")
            entity_text = f"{name}: {desc}" if desc else name

            try:
                llm_config = self.config
                from openai import OpenAI
                import os
                api_key = os.environ.get("OPENAI_API_KEY", os.environ.get("DASHSCOPE_API_KEY", "dummy"))
                api_base = os.environ.get("OPENAI_API_BASE", "http://localhost:8088/v1")
                model_name = os.environ.get("OPENAI_MODEL", "Qwen/Qwen2.5-32B-Instruct-AWQ")

                client = OpenAI(api_key=api_key, base_url=api_base)
                user_msg = f"患者数据: {patient_text}\n\n医学实体: {entity_text}"
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": prompt_template},
                        {"role": "user", "content": user_msg},
                    ],
                    max_tokens=10,
                    temperature=0.0,
                )
                score_text = response.choices[0].message.content.strip()
                try:
                    score = int(score_text)
                    score = max(1, min(5, score))
                except ValueError:
                    score = 3
                e["llm_score"] = score
            except Exception as ex:
                logger.debug(f"LLM scoring failed for '{name}': {ex}")
                e["llm_score"] = 3

            scored.append(e)

        return scored

    def get_falsification_context(self, hypotheses: List[str]) -> Dict:
        if not self.is_enabled():
            return {}

        query = """
        MATCH (f:Feature)-[r:CONTRADICTS]->(d:Disease)
        WHERE d.name IN $hypotheses OR d.id IN $hypotheses
        RETURN f.name AS feature, d.name AS disease,
               r.contradict_condition AS condition,
               r.strength AS strength, r.evidence AS evidence
        """
        try:
            results = self._run_neo4j_query(query, {"hypotheses": hypotheses})
            return {
                "contradicts": results,
                "hypotheses": hypotheses,
            }
        except Exception as e:
            logger.warning(f"get_falsification_context failed: {e}")
            return {"contradicts": [], "hypotheses": hypotheses}

    def get_guideline_context(self, disease_id: str) -> Dict:
        if not self.is_enabled():
            return {}

        query = """
        MATCH (d:Disease)-[:GUIDED_BY]->(g:ClinicalGuideline)
        WHERE d.name = $disease_id OR d.id = $disease_id
        WITH d, g
        OPTIONAL MATCH (g)<-[:GUIDED_BY]-(other)
        WHERE other.name <> d.name
        RETURN g.title AS guideline, g.organization AS organization,
               g.year AS year, g.doi AS doi,
               collect(DISTINCT other.name) AS related_diseases
        """
        try:
            results = self._run_neo4j_query(query, {"disease_id": disease_id})
            guidelines = []
            for r in results:
                guidelines.append({
                    "title": r.get("guideline", ""),
                    "organization": r.get("organization", ""),
                    "year": r.get("year"),
                    "doi": r.get("doi", ""),
                    "related_diseases": r.get("related_diseases", []),
                })
            return {
                "disease": disease_id,
                "guidelines": guidelines,
            }
        except Exception as e:
            logger.warning(f"get_guideline_context failed: {e}")
            return {"disease": disease_id, "guidelines": []}

    def get_info_gap_priority(
        self, patient_data: Dict,
    ) -> List[str]:
        if not self.is_enabled():
            return []

        matched_features = set()
        symptoms = patient_data.get("symptoms", [])
        if isinstance(symptoms, list):
            matched_features.update(str(s) for s in symptoms)

        query = """
        MATCH (f:Feature)
        WHERE NOT f.name IN $matched_names
        RETURN f.name AS feature_name, f.is_core AS is_core,
               f.specificity AS specificity, f.category AS category
        ORDER BY f.specificity DESC, f.is_core DESC
        LIMIT 10
        """
        try:
            results = self._run_neo4j_query(query, {
                "matched_names": list(matched_features),
            })
            return [r.get("feature_name", "") for r in results if r.get("feature_name")]
        except Exception as e:
            logger.warning(f"get_info_gap_priority failed: {e}")
            return []

    def get_debate_context(self, disease_id: str) -> Dict:
        if not self.is_enabled():
            return {}

        query = """
        MATCH (d1:Disease)-[r:DIFFERENTIAL_FROM]-(d2:Disease)
        WHERE d1.name = $disease_id OR d1.id = $disease_id
        RETURN d1.name AS disease_a, d2.name AS disease_b,
               r.distinguishing_features AS distinguishing,
               r.overlap_features AS overlap,
               r.difficulty AS difficulty
        """
        try:
            results = self._run_neo4j_query(query, {"disease_id": disease_id})
            differentials = []
            for r in results:
                distinguishing = r.get("distinguishing", [])
                if isinstance(distinguishing, str):
                    distinguishing = [d.strip() for d in distinguishing.split(",") if d.strip()]
                overlap = r.get("overlap", [])
                if isinstance(overlap, str):
                    overlap = [o.strip() for o in overlap.split(",") if o.strip()]
                differentials.append({
                    "disease_pair": f"{r.get('disease_a', '')} vs {r.get('disease_b', '')}",
                    "distinguishing_features": distinguishing,
                    "overlap_features": overlap,
                    "difficulty": r.get("difficulty"),
                })
            return {
                "disease": disease_id,
                "differentials": differentials,
            }
        except Exception as e:
            logger.warning(f"get_debate_context failed: {e}")
            return {"disease": disease_id, "differentials": []}

    def _extract_queries(self, patient_data: Dict) -> List[str]:
        queries = []
        for key in ("symptoms", "abnormal_labs", "imaging_findings"):
            val = patient_data.get(key, [])
            if val:
                if isinstance(val, dict):
                    if key == "symptoms":
                        active = [k for k, v in val.items() if v]
                        if active:
                            queries.append(" ".join(active))
                    else:
                        parts = [f"{k}: {v}" for k, v in val.items() if v]
                        if parts:
                            queries.append(" ".join(parts))
                elif isinstance(val, list):
                    queries.append(" ".join(str(v) for v in val))
                else:
                    queries.append(str(val))

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

        imaging_results = patient_data.get("imaging_results", {})
        if imaging_results:
            if isinstance(imaging_results, dict):
                img_parts = [f"{k}: {v}" for k, v in imaging_results.items() if v]
                if img_parts:
                    queries.append(" ".join(img_parts))
            else:
                queries.append(str(imaging_results))

        history = patient_data.get("history", {})
        if history:
            if isinstance(history, dict):
                hist_parts = [f"{k}: {v}" for k, v in history.items() if v]
                if hist_parts:
                    queries.append(" ".join(hist_parts))
            else:
                queries.append(str(history))

        for key in ("clinical_notes", "chief_complaint"):
            val = patient_data.get(key, "")
            if val:
                queries.append(str(val))
        return [q.strip() for q in queries if q and str(q).strip()]

    def _patient_data_to_text(self, patient_data: Dict) -> str:
        parts = []
        for key in ("symptoms", "abnormal_labs", "imaging_findings", "clinical_notes"):
            val = patient_data.get(key, "")
            if val:
                if isinstance(val, list):
                    parts.append(" ".join(str(v) for v in val))
                else:
                    parts.append(str(val))
        return " ".join(parts)

    def _build_simple_activations(
        self, retrieval_result: KGRetrievalResult,
    ) -> List[ActivationResult]:
        results = []
        for candidate in retrieval_result.candidate_diseases:
            results.append(ActivationResult(
                disease_id=candidate.disease_id,
                disease_name=candidate.name,
                activation_score=candidate.score,
                matched_features=candidate.matched_features,
                unmatched_features=[],
                evidence_path=[],
                source="kg_degraded",
            ))
        return results

    def close(self) -> None:
        if self._retriever is not None:
            self._retriever.close()
            self._retriever = None
        if self._classifier is not None:
            self._classifier.close()
            self._classifier = None
        if self._embedder is not None:
            self._embedder.close()
            self._embedder = None
        if self._neo4j_driver is not None:
            self._neo4j_driver.close()
            self._neo4j_driver = None
