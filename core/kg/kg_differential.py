"""
诊断差异KG预计算模块

职责：
1. 从DiseasePipeline配置写入差异诊断边(differential_from)
2. 从DiseasePipeline配置写入矛盾排除边(contradicts)
3. 从Neo4j图自动计算疾病间差异关系(基于共享特征)
4. 写入差异疾病节点和类别链接

所有疾病特定数据通过方法参数传入，本模块不硬编码任何疾病知识。

使用示例:
    from core.kg.kg_differential import KGDifferential
    from core.kg.diseases import DiseasePipeline

    pipeline = DiseasePipeline("data/disease_configs/wilson_disease.yaml")
    diff = KGDifferential()

    diff_edges = pipeline.get_differential_edges()
    disease_nodes = pipeline.get_differential_disease_nodes()
    contradicts = pipeline.get_contradicts()

    stats = diff.write_from_config(diff_edges, disease_nodes, contradicts)
    diff.close()
"""

from typing import Any, Dict, List, Optional

from loguru import logger

from core.kg.kg_schema import (
    DifferentialEdge, ContradictEdge, RelationEdge, RelationType, DiseaseNode,
)
from core.kg.kg_config import KGConfig


class KGDifferential:
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

    def write_from_config(
        self,
        diff_edges: List[DifferentialEdge],
        disease_nodes: Optional[List[DiseaseNode]] = None,
        contradicts: Optional[List[Any]] = None,
    ) -> Dict[str, int]:
        stats = {"differentials": 0, "contradicts": 0, "disease_nodes": 0}

        if disease_nodes:
            for d in disease_nodes:
                try:
                    self._write_disease_node(d)
                    stats["disease_nodes"] += 1
                except Exception as e:
                    logger.warning(f"Failed to write disease node {d.disease_id}: {e}")

        for diff in diff_edges:
            try:
                self._write_differential_edge(diff)
                stats["differentials"] += 1
            except Exception as e:
                logger.warning(f"Failed to write differential {diff.disease_a_id}-{diff.disease_b_id}: {e}")

        if contradicts:
            for contra in contradicts:
                try:
                    if isinstance(contra, ContradictEdge):
                        self._write_contradict_edge(contra)
                    else:
                        self._write_contradicts_from_config(contra)
                    stats["contradicts"] += 1
                except Exception as e:
                    cid = contra.feature_id if isinstance(contra, ContradictEdge) else contra.get('feature_id', '')
                    did = contra.disease_id if isinstance(contra, ContradictEdge) else contra.get('disease_id', '')
                    logger.warning(f"Failed to write contradicts {cid}->{did}: {e}")

        logger.info(f"Differential write_from_config complete: {stats}")
        return stats

    def compute_from_graph(self) -> List[DifferentialEdge]:
        try:
            return self._compute_from_neo4j()
        except Exception as e:
            logger.warning(f"Neo4j-based differential computation failed: {e}")
            return []

    def _compute_from_neo4j(self) -> List[DifferentialEdge]:
        query = """
        MATCH (d1:Disease)-[:HAS_MANIFESTATION|HAS_DIAGNOSTIC_KEY]->(f1:Feature)
        WITH d1, collect(f1.id) AS d1_features
        MATCH (d2:Disease)-[:HAS_MANIFESTATION|HAS_DIAGNOSTIC_KEY]->(f2:Feature)
        WHERE d1.id < d2.id
        WITH d1, d2, d1_features, d2_features,
             [f IN d1_features WHERE f IN d2_features] AS overlap_ids
        WITH d1, d2, overlap_ids,
             [f IN d1_features WHERE NOT f IN d2_features] AS d1_only,
             [f IN d2_features WHERE NOT f IN d1_features] AS d2_only
        RETURN d1.id AS d1_id, d2.id AS d2_id,
               overlap_ids, d1_only, d2_only,
               size(overlap_ids) AS overlap_count,
               size(d1_features) + size(d2_features) - size(overlap_ids) AS total_count
        """
        results = self._run_neo4j_query(query)

        edges = []
        for r in results:
            overlap_count = r.get("overlap_count", 0)
            total_count = r.get("total_count", 1)
            similarity = overlap_count / total_count if total_count > 0 else 0.0

            overlap_names = self._resolve_feature_names(r.get("overlap_ids", []))
            d1_only_names = self._resolve_feature_names(r.get("d1_only", []))
            d2_only_names = self._resolve_feature_names(r.get("d2_only", []))

            distinguishing = d1_only_names + d2_only_names

            difficulty = "easy"
            if similarity > 0.6:
                difficulty = "hard"
            elif similarity > 0.3:
                difficulty = "moderate"

            edge = DifferentialEdge(
                disease_a_id=r["d1_id"],
                disease_b_id=r["d2_id"],
                distinguishing_features=distinguishing,
                overlap_features=overlap_names,
                similarity_score=round(similarity, 3),
                difficulty=difficulty,
            )
            edges.append(edge)

        logger.info(f"Computed {len(edges)} differential edges from graph")
        return edges

    def _resolve_feature_names(self, feature_ids: List[str]) -> List[str]:
        if not feature_ids:
            return []
        query = """
        UNWIND $ids AS fid
        MATCH (f:Feature {id: fid})
        RETURN f.name AS name
        """
        try:
            results = self._run_neo4j_query(query, {"ids": feature_ids})
            return [r["name"] for r in results if r.get("name")]
        except Exception:
            return feature_ids

    def _write_disease_node(self, disease: DiseaseNode) -> None:
        query = """
        MERGE (n:Disease {id: $id})
        ON CREATE SET n.name = $name, n.name_en = $name_en,
                      n.icd10 = $icd10, n.category = $category,
                      n.description = $description, n.layer = 'EL3'
        ON MATCH SET
            n.description = CASE WHEN n.description IS NULL OR n.description = ''
                                 THEN $description ELSE n.description END
        RETURN n
        """
        params = {
            "id": disease.disease_id,
            "name": disease.name,
            "name_en": disease.name_en or "",
            "icd10": disease.icd10 or "",
            "category": disease.category or "",
            "description": disease.description or "",
        }
        self._run_neo4j_query(query, params)

    def _write_differential_edge(self, diff: DifferentialEdge) -> None:
        query = """
        MATCH (d1:Disease {id: $d1_id})
        MATCH (d2:Disease {id: $d2_id})
        MERGE (d1)-[r:DIFFERENTIAL_FROM]->(d2)
        ON CREATE SET r.distinguishing_features = $distinguishing,
                      r.overlap_features = $overlap,
                      r.similarity_score = $similarity,
                      r.difficulty = $difficulty,
                      r.evidence = $evidence,
                      r.source = $source
        RETURN r
        """
        params = {
            "d1_id": diff.disease_a_id,
            "d2_id": diff.disease_b_id,
            "distinguishing": diff.distinguishing_features,
            "overlap": diff.overlap_features,
            "similarity": diff.similarity_score,
            "difficulty": diff.difficulty or "moderate",
            "evidence": diff.evidence or "",
            "source": diff.source or "",
        }
        self._run_neo4j_query(query, params)

    def _write_contradicts_from_config(self, contra: Dict[str, Any]) -> None:
        feature_id = contra.get("feature_id", "")
        disease_id = contra.get("disease_id", "")
        strength = contra.get("strength", "moderate")
        evidence = contra.get("evidence", "")
        contradict_condition = contra.get("contradict_condition", "")

        confidence = 0.95 if strength == "strong" else 0.80
        weight = 2.0 if strength == "strong" else 1.5

        query = """
        MATCH (f:Feature {id: $feature_id})
        MATCH (d:Disease {id: $disease_id})
        MERGE (f)-[r:CONTRADICTS]->(d)
        ON CREATE SET r.strength = $strength,
                      r.confidence = $confidence,
                      r.weight = $weight,
                      r.evidence = $evidence,
                      r.contradict_condition = $contradict_condition
        RETURN r
        """
        params = {
            "feature_id": feature_id,
            "disease_id": disease_id,
            "strength": strength,
            "confidence": confidence,
            "weight": weight,
            "evidence": evidence,
            "contradict_condition": contradict_condition,
        }
        self._run_neo4j_query(query, params)

    def _write_contradict_edge(self, contra: ContradictEdge) -> None:
        query = """
        MATCH (f:Feature {id: $feature_id})
        MATCH (d:Disease {id: $disease_id})
        MERGE (f)-[r:CONTRADICTS]->(d)
        ON CREATE SET r.strength = $strength,
                      r.confidence = $confidence,
                      r.weight = $weight,
                      r.evidence = $evidence,
                      r.contradict_condition = $contradict_condition,
                      r.source = $source,
                      r.source_page = $source_page
        ON MATCH SET
            r.contradict_condition = CASE WHEN r.contradict_condition IS NULL OR r.contradict_condition = ''
                                          THEN $contradict_condition ELSE r.contradict_condition END
        RETURN r
        """
        params = {
            "feature_id": contra.feature_id,
            "disease_id": contra.disease_id,
            "strength": contra.strength,
            "confidence": contra.confidence,
            "weight": contra.weight,
            "evidence": contra.evidence or "",
            "contradict_condition": contra.contradict_condition,
            "source": contra.source or "",
            "source_page": contra.source_page,
        }
        self._run_neo4j_query(query, params)

    def write_disease_category_links(
        self, differential_disease_nodes: Optional[List[DiseaseNode]] = None
    ) -> int:
        links = 0
        if differential_disease_nodes is None:
            logger.warning("No differential disease nodes provided for category links")
            return 0

        for d in differential_disease_nodes:
            cat_id = d.category
            disease_id = d.disease_id
            if cat_id:
                try:
                    query = """
                    MATCH (d:Disease {id: $disease_id})
                    MATCH (e:Entity {id: $cat_id})
                    MERGE (e)-[r:IS_A]->(d)
                    ON CREATE SET r.confidence = 0.9, r.evidence = '层级归属'
                    RETURN r
                    """
                    self._run_neo4j_query(query, {
                        "disease_id": disease_id,
                        "cat_id": cat_id,
                    })
                    links += 1
                except Exception as e:
                    logger.warning(f"Failed to write category link {disease_id}->{cat_id}: {e}")
        logger.info(f"Wrote {links} disease-category links")
        return links

    def close(self) -> None:
        if self._neo4j_driver is not None:
            self._neo4j_driver.close()
            self._neo4j_driver = None
            logger.info("Neo4j driver closed")
