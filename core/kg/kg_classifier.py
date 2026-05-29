"""
投票激活分类器

移植自 MedRAG:
- KG_Retrieve.py → find_closest_category() (L150-197): 最短路径投票分类
- KG_Retrieve.py → compute_shortest_path_length() (L116-120): 最短路径长度
- KG_Retrieve.py → get_diagnoses_for_symptom() (L139-147): 症状→诊断映射
- KG_Retrieve.py → get_keyinfo_for_category() (L200-209): 类别关键信息

适配改造:
- NetworkX图遍历 → Neo4j Cypher查询
- nx.shortest_path_length → Cypher shortestPath
- 通用类别 → 罕见肝病EL2亚类(铜代谢/自身免疫/胆汁淤积/代谢性)
- 增加激活评分计算(加权投票 + 矛盾惩罚)

分类流程:
Step 1: 特征匹配投票 → Step 2: 最短路径投票 →
Step 3: 激活评分计算 → Step 4: 证据路径构建

使用示例:
    from core.kg.kg_classifier import KGClassifier
    classifier = KGClassifier()
    results = classifier.classify(patient_data, retrieval_result)
"""

from collections import defaultdict
from typing import Any, Dict, List, Optional

from loguru import logger

from core.kg.kg_config import KGConfig
from core.kg.kg_schema import (
    ActivationResult,
    CandidateDisease,
    KGRetrievalResult,
)


class KGClassifier:
    def __init__(self, config: Optional[KGConfig] = None):
        self.config = config or KGConfig.from_yaml()
        self._neo4j_driver = None

    def _get_neo4j_driver(self):
        if self._neo4j_driver is None:
            self._neo4j_driver = self.config.get_neo4j_driver()
        return self._neo4j_driver

    def _run_neo4j_query(self, query: str, params: Optional[Dict] = None) -> List[Dict]:
        driver = self._get_neo4j_driver()
        with driver.session(database=self.config.neo4j.database) as session:
            result = session.run(query, params or {})
            return [record.data() for record in result]

    def classify(
        self,
        patient_data: Dict,
        retrieval_result: KGRetrievalResult,
    ) -> List[ActivationResult]:
        logger.info(
            f"KGClassifier: classifying with "
            f"{len(retrieval_result.candidate_diseases)} candidates"
        )

        if not retrieval_result.candidate_diseases:
            logger.warning("KGClassifier: no candidate diseases to classify")
            return []

        matched_feature_ids = self._extract_matched_feature_ids(retrieval_result)
        logger.info(f"KGClassifier: {len(matched_feature_ids)} matched features")

        category_votes = self._find_closest_category(matched_feature_ids)
        logger.info(f"KGClassifier: category votes = {category_votes}")

        all_disease_features = self._get_all_disease_features(
            retrieval_result.candidate_diseases
        )

        contradicts = self._get_contradicts(patient_data)

        results = []
        for candidate in retrieval_result.candidate_diseases:
            matched = [
                f for f in candidate.matched_features
                if f.get("feature")
            ]

            disease_key = candidate.disease_id
            if disease_key not in all_disease_features:
                disease_key = candidate.name
            all_features = all_disease_features.get(disease_key, [])

            activation_score = self._compute_activation_score(
                matched=matched,
                all_features=all_features,
                contradicts=contradicts,
                disease_id=candidate.disease_id,
                disease_name=candidate.name,
            )

            evidence_path = self._build_evidence_path(matched)

            unmatched = self._get_unmatched_features(
                candidate.disease_id, matched_feature_ids
            )

            results.append(ActivationResult(
                disease_id=candidate.disease_id,
                disease_name=candidate.name,
                activation_score=activation_score,
                matched_features=matched,
                unmatched_features=unmatched,
                evidence_path=evidence_path,
                source="kg",
            ))

        results.sort(key=lambda r: r.activation_score, reverse=True)
        logger.info(
            f"KGClassifier: classification complete, "
            f"top result: {results[0].disease_name} ({results[0].activation_score:.3f})"
            if results else "KGClassifier: no results"
        )
        return results

    def _extract_matched_feature_ids(
        self, retrieval_result: KGRetrievalResult
    ) -> List[str]:
        feature_ids = set()
        for candidate in retrieval_result.candidate_diseases:
            for f in candidate.matched_features:
                name = f.get("feature", "")
                if name:
                    feature_ids.add(name)
        for entity in retrieval_result.relevant_entities:
            if entity.entity_type == "Feature":
                feature_ids.add(entity.name)
        return list(feature_ids)

    def _find_closest_category(
        self, feature_ids: List[str],
    ) -> Dict[str, float]:
        if not feature_ids:
            return {}

        category_votes: Dict[str, float] = defaultdict(float)

        for feature_id in feature_ids:
            diagnoses = self._get_diagnoses_for_symptom(feature_id)
            for disease_id in diagnoses:
                categories = self._get_el2_categories(disease_id)
                for cat_id in categories:
                    distance = self._compute_shortest_path(feature_id, cat_id)
                    if distance < float('inf'):
                        path_weight = 1.0 / (1.0 + distance)
                        category_votes[cat_id] += path_weight

        return dict(category_votes)

    def _get_diagnoses_for_symptom(self, feature_id: str) -> List[str]:
        query = """
        MATCH (f:Feature)-[:HAS_MANIFESTATION|HAS_DIAGNOSTIC_KEY]-(d:Disease)
        WHERE f.name = $feature_id OR f.id = $feature_id
        RETURN d.id AS disease_id, d.name AS disease_name
        """
        try:
            results = self._run_neo4j_query(query, {"feature_id": feature_id})
            return [r.get("disease_id") or r.get("disease_name", "") for r in results]
        except Exception as e:
            logger.warning(f"get_diagnoses_for_symptom failed for '{feature_id}': {e}")
            return []

    def _get_el2_categories(self, disease_id: str) -> List[str]:
        query = """
        MATCH (d:Disease)-[:IS_A]->(cat)
        WHERE (d.id = $disease_id OR d.name = $disease_id)
          AND cat.layer = 'EL2'
        RETURN cat.id AS cat_id, cat.name AS cat_name
        """
        try:
            results = self._run_neo4j_query(query, {"disease_id": disease_id})
            return [r.get("cat_id") or r.get("cat_name", "") for r in results]
        except Exception as e:
            logger.warning(f"get_el2_categories failed for '{disease_id}': {e}")
            return []

    def _compute_shortest_path(
        self, source_id: str, category_id: str,
    ) -> int:
        query = """
        MATCH (start), (end)
        WHERE (start.name = $source_id OR start.id = $source_id)
          AND (end.name = $category_id OR end.id = $category_id)
        WITH start, end
        MATCH p = shortestPath((start)-[*]-(end))
        RETURN length(p) AS distance
        LIMIT 1
        """
        try:
            results = self._run_neo4j_query(query, {
                "source_id": source_id,
                "category_id": category_id,
            })
            if results and results[0].get("distance") is not None:
                return results[0]["distance"]
            return float('inf')
        except Exception as e:
            logger.debug(f"shortest_path failed for '{source_id}' → '{category_id}': {e}")
            return float('inf')

    def _get_keyinfo_for_category(self, category_id: str) -> Dict:
        query = """
        MATCH (cat)-[:IS_A]->(d:Disease)
        WHERE (cat.id = $category_id OR cat.name = $category_id)
          AND cat.layer = 'EL2'
        MATCH (d)-[:HAS_DIAGNOSTIC_KEY]->(f:Feature)
        WHERE f.is_core = true
        RETURN d.name AS disease, collect(f.name) AS core_features
        """
        try:
            results = self._run_neo4j_query(query, {"category_id": category_id})
            if results:
                return {
                    "category": category_id,
                    "diseases": results,
                }
            return {}
        except Exception as e:
            logger.warning(f"get_keyinfo_for_category failed: {e}")
            return {}

    def _get_all_disease_features(self, candidates: List[CandidateDisease]) -> Dict[str, List[Dict]]:
        disease_features: Dict[str, List[Dict]] = {}
        disease_ids = [c.disease_id for c in candidates]
        disease_names = [c.name for c in candidates]

        if not disease_ids and not disease_names:
            return disease_features

        query = """
        MATCH (d:Disease)-[r:HAS_MANIFESTATION|HAS_DIAGNOSTIC_KEY]->(f:Feature)
        WHERE d.name IN $disease_names OR d.id IN $disease_ids
        RETURN d.name AS disease_id, f.name AS feature_name,
               f.is_core AS is_core, type(r) AS rel_type
        """
        try:
            results = self._run_neo4j_query(query, {
                "disease_ids": disease_ids,
                "disease_names": disease_names,
            })
            for r in results:
                did = r.get("disease_id", "")
                if did not in disease_features:
                    disease_features[did] = []
                disease_features[did].append({
                    "feature": r.get("feature_name", ""),
                    "is_core": r.get("is_core", False),
                    "relation": r.get("rel_type", ""),
                })
        except Exception as e:
            logger.warning(f"get_all_disease_features failed: {e}")

        return disease_features

    def _compute_activation_score(
        self,
        matched: List[Dict],
        all_features: List[Dict],
        contradicts: List[Dict],
        disease_id: str,
        disease_name: str = "",
    ) -> float:
        core_weight = self.config.activation.core_feature_weight
        supporting_weight = self.config.activation.supporting_feature_weight

        matched_weight = 0.0
        for f in matched:
            is_core = f.get("is_core", False)
            matched_weight += core_weight if is_core else supporting_weight

        total_weight = 0.0
        for f in all_features:
            is_core = f.get("is_core", False)
            total_weight += core_weight if is_core else supporting_weight

        if total_weight == 0:
            return 0.0

        activation_score = matched_weight / total_weight

        contradicts_penalty = 0.0
        for c in contradicts:
            c_disease = c.get("disease_id", "")
            if c_disease == disease_id or c_disease == disease_name:
                contradicts_penalty = 0.3
                break

        final_score = activation_score * (1.0 - contradicts_penalty)
        return round(final_score, 4)

    def _get_contradicts(self, patient_data: Dict) -> List[Dict]:
        query = """
        MATCH (f:Feature)-[r:CONTRADICTS]->(d:Disease)
        RETURN f.name AS feature_id, d.name AS disease_id,
               r.contradict_condition AS condition, r.strength AS strength
        """
        try:
            results = self._run_neo4j_query(query)
            contradicts = []
            patient_text = self._patient_data_to_text(patient_data)
            for r in results:
                condition = r.get("condition", "")
                if condition and condition.lower() in patient_text.lower():
                    contradicts.append(r)
            return contradicts
        except Exception as e:
            logger.warning(f"get_contradicts failed: {e}")
            return []

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

    def _build_evidence_path(self, matched_features: List[Dict]) -> List[Dict]:
        if not matched_features:
            return []

        feature_names = [
            f.get("feature", "") for f in matched_features if f.get("feature")
        ]
        if not feature_names:
            return []

        query = """
        MATCH path = (f:Feature)-[:HAS_MANIFESTATION|HAS_DIAGNOSTIC_KEY]->(d:Disease)-[:IS_A]->(cat)
        WHERE f.name IN $feature_names
        RETURN f.name AS feature, d.name AS disease,
               cat.name AS category, cat.layer AS layer
        """
        try:
            results = self._run_neo4j_query(query, {"feature_names": feature_names})
            paths = []
            for r in results:
                path_entry = {
                    "feature": r.get("feature", ""),
                    "disease": r.get("disease", ""),
                    "category": r.get("category", ""),
                    "layer": r.get("layer", ""),
                }
                paths.append(path_entry)
            return paths
        except Exception as e:
            logger.warning(f"build_evidence_path failed: {e}")
            return []

    def _get_unmatched_features(
        self, disease_id: str, matched_feature_ids: List[str],
    ) -> List[str]:
        query = """
        MATCH (d:Disease)-[:HAS_MANIFESTATION|HAS_DIAGNOSTIC_KEY]->(f:Feature)
        WHERE d.name = $name_or_id OR d.id = $name_or_id
        RETURN f.name AS feature_name
        """
        try:
            results = self._run_neo4j_query(query, {"name_or_id": disease_id})
            unmatched = []
            matched_set = set(matched_feature_ids)
            for r in results:
                name = r.get("feature_name", "")
                if name and name not in matched_set:
                    unmatched.append(name)
            return unmatched
        except Exception as e:
            logger.warning(f"get_unmatched_features failed: {e}")
            return []

    def close(self) -> None:
        if self._neo4j_driver is not None:
            self._neo4j_driver.close()
            self._neo4j_driver = None
