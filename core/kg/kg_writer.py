"""
Neo4j节点/关系写入模块

移植自 MedGraphRAG:
- creat_graph_with_description.py → create_neo4j_nodes_and_relationships()(第133-223行)

适配改造:
- Cypher语句适配罕见肝病KG Schema(见实施计划4.3.1-4.3.3节)
- UNWIND批量导入优化
- 支持8种诊断KG关系类型
- 增加NetworkX降级模式
- 幂等写入(MERGE ON CREATE/ON MATCH)

使用示例：
    from core.kg.kg_writer import KGWriter
    writer = KGWriter()
    writer.write_disease_node(disease_node)
    writer.write_feature_node(feature_node)
    writer.write_relation(relation_edge)
"""

from typing import Any, Dict, List, Optional

from loguru import logger

from core.kg.kg_schema import (
    DiseaseNode, FeatureNode, RelationEdge, ExtractionResult,
    GuidelineNode, DifferentialEdge, ContradictEdge, RelationType,
)
from core.kg.kg_config import KGConfig


class KGWriter:
    def __init__(self, config: Optional[KGConfig] = None):
        self.config = config or KGConfig.from_yaml()
        self.engine = self.config.engine
        self._neo4j_driver = None
        self._nx_graph = None
        self._write_count = {"nodes": 0, "relations": 0}

    def _get_neo4j_driver(self):
        if self._neo4j_driver is None:
            self._neo4j_driver = self.config.get_neo4j_driver()
        return self._neo4j_driver

    def _get_nx_graph(self):
        if self._nx_graph is None:
            import networkx as nx
            self._nx_graph = nx.DiGraph()
        return self._nx_graph

    def _run_neo4j_query(self, query: str, params: Optional[Dict] = None) -> List[Dict]:
        driver = self._get_neo4j_driver()
        with driver.session(database=self.config.neo4j.database) as session:
            result = session.run(query, params or {})
            return [record.data() for record in result]

    def write_disease_node(self, disease: DiseaseNode, gid: Optional[str] = None) -> bool:
        properties = disease.to_neo4j_dict()

        if self.engine == "neo4j":
            return self._write_neo4j_disease(disease.disease_id, properties, gid)
        else:
            G = self._get_nx_graph()
            G.add_node(disease.disease_id, label="Disease", **properties)
            self._write_count["nodes"] += 1
            return True

    def write_feature_node(self, feature: FeatureNode, gid: Optional[str] = None) -> bool:
        properties = feature.to_neo4j_dict()

        if self.engine == "neo4j":
            return self._write_neo4j_feature(feature.feature_id, properties, gid)
        else:
            G = self._get_nx_graph()
            G.add_node(feature.feature_id, label="Feature", **properties)
            self._write_count["nodes"] += 1
            return True

    def write_guideline_node(self, guideline: GuidelineNode, gid: Optional[str] = None) -> bool:
        properties = guideline.to_neo4j_dict()

        if self.engine == "neo4j":
            return self._write_neo4j_guideline(guideline.guideline_id, properties, gid)
        else:
            G = self._get_nx_graph()
            G.add_node(guideline.guideline_id, label="ClinicalGuideline", **properties)
            self._write_count["nodes"] += 1
            return True

    def write_relation(self, edge: RelationEdge) -> bool:
        rel_type = edge.relation_type.value
        properties = edge.to_neo4j_dict()

        if self.engine == "neo4j":
            return self._write_neo4j_relation(
                edge.source_id, edge.target_id, rel_type, properties
            )
        else:
            G = self._get_nx_graph()
            if not G.has_node(edge.source_id):
                G.add_node(edge.source_id, label="Unknown")
            if not G.has_node(edge.target_id):
                G.add_node(edge.target_id, label="Unknown")
            G.add_edge(edge.source_id, edge.target_id,
                       relation_type=rel_type, **properties)
            self._write_count["relations"] += 1
            return True

    def write_differential_edge(self, diff: DifferentialEdge) -> bool:
        properties = diff.to_neo4j_dict()

        if self.engine == "neo4j":
            return self._write_neo4j_relation(
                diff.disease_a_id, diff.disease_b_id,
                "differential_from", properties
            )
        else:
            G = self._get_nx_graph()
            if not G.has_node(diff.disease_a_id):
                G.add_node(diff.disease_a_id, label="Disease")
            if not G.has_node(diff.disease_b_id):
                G.add_node(diff.disease_b_id, label="Disease")
            G.add_edge(diff.disease_a_id, diff.disease_b_id,
                       relation_type="differential_from", **properties)
            self._write_count["relations"] += 1
            return True

    def write_contradict_edge(self, contra: ContradictEdge) -> bool:
        properties = contra.to_neo4j_dict()

        if self.engine == "neo4j":
            return self._write_neo4j_contradict(contra, properties)
        else:
            G = self._get_nx_graph()
            if not G.has_node(contra.feature_id):
                G.add_node(contra.feature_id, label="Feature")
            if not G.has_node(contra.disease_id):
                G.add_node(contra.disease_id, label="Disease")
            G.add_edge(contra.feature_id, contra.disease_id,
                       relation_type="contradicts", **properties)
            self._write_count["relations"] += 1
            return True

    def write_extraction_result(self, result: ExtractionResult) -> Dict[str, int]:
        stats = {"diseases": 0, "features": 0, "guidelines": 0, "relations": 0, "differentials": 0, "contradicts": 0}

        for disease in result.disease_nodes:
            if self.write_disease_node(disease):
                stats["diseases"] += 1

        for feature in result.feature_nodes:
            if self.write_feature_node(feature):
                stats["features"] += 1

        for guideline in result.guideline_nodes:
            if self.write_guideline_node(guideline):
                stats["guidelines"] += 1

        for edge in result.relation_edges:
            if self.write_relation(edge):
                stats["relations"] += 1

        for diff in result.differential_edges:
            if self.write_differential_edge(diff):
                stats["differentials"] += 1

        for contra in result.contradict_edges:
            if self.write_contradict_edge(contra):
                stats["contradicts"] += 1

        logger.info(
            f"Write complete: diseases={stats['diseases']}, features={stats['features']}, "
            f"guidelines={stats['guidelines']}, relations={stats['relations']}, "
            f"differentials={stats['differentials']}, contradicts={stats['contradicts']}"
        )
        return stats

    def batch_write_diseases(self, diseases: List[DiseaseNode]) -> int:
        if self.engine != "neo4j":
            count = 0
            for d in diseases:
                if self.write_disease_node(d):
                    count += 1
            return count

        data = []
        for d in diseases:
            props = d.to_neo4j_dict()
            props["id"] = d.disease_id
            data.append(props)

        if not data:
            return 0

        query = """
        UNWIND $data AS row
        MERGE (n:Disease {id: row.id})
        ON CREATE SET n.layer = row.layer, n.name = row.name,
                      n.name_en = row.name_en, n.icd10 = row.icd10,
                      n.omim = row.omim, n.orpha = row.orpha,
                      n.prevalence = row.prevalence, n.inheritance = row.inheritance,
                      n.description = row.description, n.severity = row.severity,
                      n.category = row.category
        ON MATCH SET
            n.description = CASE WHEN n.description IS NULL OR n.description = ''
                                 THEN row.description ELSE n.description END
        RETURN count(*) AS cnt
        """
        try:
            result = self._run_neo4j_query(query, {"data": data})
            count = result[0]["cnt"] if result else 0
            self._write_count["nodes"] += count
            logger.info(f"Batch wrote {count} disease nodes")
            return count
        except Exception as e:
            logger.error(f"Batch disease write failed: {e}")
            return 0

    def batch_write_features(self, features: List[FeatureNode]) -> int:
        if self.engine != "neo4j":
            count = 0
            for f in features:
                if self.write_feature_node(f):
                    count += 1
            return count

        data = []
        for f in features:
            props = f.to_neo4j_dict()
            props["id"] = f.feature_id
            data.append(props)

        if not data:
            return 0

        query = """
        UNWIND $data AS row
        MERGE (n:Feature {id: row.id})
        ON CREATE SET n.layer = row.layer, n.name = row.name,
                      n.name_en = row.name_en, n.category = row.category,
                      n.is_core = row.is_core, n.specificity = row.specificity,
                      n.sensitivity = row.sensitivity, n.hpo_id = row.hpo_id,
                      n.description = row.description,
                      n.abnormal_direction = row.abnormal_direction,
                      n.unit = row.unit, n.normal_range = row.normal_range
        ON MATCH SET
            n.description = CASE WHEN n.description IS NULL OR n.description = ''
                                 THEN row.description ELSE n.description END,
            n.is_core = CASE WHEN n.is_core IS NULL THEN row.is_core ELSE n.is_core END
        RETURN count(*) AS cnt
        """
        try:
            result = self._run_neo4j_query(query, {"data": data})
            count = result[0]["cnt"] if result else 0
            self._write_count["nodes"] += count
            logger.info(f"Batch wrote {count} feature nodes")
            return count
        except Exception as e:
            logger.error(f"Batch feature write failed: {e}")
            return 0

    def batch_write_relations(self, relations: List[RelationEdge]) -> int:
        if self.engine != "neo4j":
            count = 0
            for r in relations:
                if self.write_relation(r):
                    count += 1
            return count

        data = []
        for r in relations:
            props = r.to_neo4j_dict()
            data.append({
                "source_id": r.source_id,
                "target_id": r.target_id,
                "relation_type": r.relation_type.value.upper(),
                "confidence": props.get("confidence", 1.0),
                "weight": props.get("weight", 1.0),
                "is_core": props.get("is_core", False),
                "evidence": props.get("evidence", ""),
            })

        if not data:
            return 0

        count = 0
        for rel_data in data:
            rel_type = rel_data["relation_type"]
            query = f"""
            MATCH (a {{id: $src}})
            MATCH (b {{id: $tgt}})
            MERGE (a)-[r:{rel_type}]->(b)
            ON CREATE SET r.confidence = $confidence, r.weight = $weight,
                          r.is_core = $is_core, r.evidence = $evidence
            RETURN r
            """
            try:
                self._run_neo4j_query(query, {
                    "src": rel_data["source_id"],
                    "tgt": rel_data["target_id"],
                    "confidence": rel_data["confidence"],
                    "weight": rel_data["weight"],
                    "is_core": rel_data["is_core"],
                    "evidence": rel_data["evidence"],
                })
                count += 1
            except Exception as e:
                logger.warning(f"Relation write failed {rel_data['source_id']}-{rel_type}->{rel_data['target_id']}: {e}")

        self._write_count["relations"] += count
        logger.info(f"Batch wrote {count} relations")
        return count

    def write_summary_node(
        self, entity_name: str, summary_content: str, gid: str
    ) -> bool:
        summary_id = f"SUMMARY_{entity_name}"

        if self.engine == "neo4j":
            query = """
            MERGE (s:Summary {id: $summary_id})
            ON CREATE SET s.content = $content
            WITH s
            MATCH (e {id: $entity_name})
            MERGE (s)-[:SUMMARIZES]->(e)
            RETURN s
            """
            try:
                self._run_neo4j_query(query, {
                    "summary_id": summary_id,
                    "content": summary_content,
                    "entity_name": entity_name,
                })
                self._write_count["nodes"] += 1
                return True
            except Exception as e:
                logger.error(f"Summary node write failed for {entity_name}: {e}")
                return False
        else:
            G = self._get_nx_graph()
            G.add_node(summary_id, label="Summary", content=summary_content, gid=gid)
            if G.has_node(entity_name):
                G.add_edge(summary_id, entity_name, relation_type="SUMMARIZES")
            self._write_count["nodes"] += 1
            return True

    def get_write_stats(self) -> Dict[str, int]:
        return dict(self._write_count)

    def get_nx_graph(self):
        return self._get_nx_graph()

    def close(self) -> None:
        if self._neo4j_driver is not None:
            self._neo4j_driver.close()
            self._neo4j_driver = None
            logger.info("Neo4j driver closed")

    def _write_neo4j_disease(
        self, node_id: str, properties: Dict[str, Any], gid: Optional[str]
    ) -> bool:
        query = """
        MERGE (n:Disease {id: $id})
        ON CREATE SET n.layer = $layer, n.name = $name,
                      n.name_en = $name_en, n.icd10 = $icd10,
                      n.omim = $omim, n.orpha = $orpha,
                      n.prevalence = $prevalence, n.inheritance = $inheritance,
                      n.description = $description, n.severity = $severity,
                      n.category = $category
        ON MATCH SET
            n.description = CASE WHEN n.description IS NULL OR n.description = ''
                                 THEN $description ELSE n.description END,
            n.name_en = CASE WHEN n.name_en IS NULL OR n.name_en = ''
                             THEN $name_en ELSE n.name_en END
        RETURN n
        """
        params = {
            "id": node_id,
            "layer": properties.get("layer", "EL3"),
            "name": properties.get("name", ""),
            "name_en": properties.get("name_en", ""),
            "icd10": properties.get("icd10", ""),
            "omim": properties.get("omim", ""),
            "orpha": properties.get("orpha", ""),
            "prevalence": properties.get("prevalence", ""),
            "inheritance": properties.get("inheritance", ""),
            "description": properties.get("description", ""),
            "severity": properties.get("severity", ""),
            "category": properties.get("category", ""),
        }
        if gid:
            params["gid"] = gid

        try:
            self._run_neo4j_query(query, params)
            self._write_count["nodes"] += 1
            return True
        except Exception as e:
            logger.error(f"Disease node write failed for {node_id}: {e}")
            return False

    def _write_neo4j_feature(
        self, node_id: str, properties: Dict[str, Any], gid: Optional[str]
    ) -> bool:
        query = """
        MERGE (n:Feature {id: $id})
        ON CREATE SET n.layer = $layer, n.name = $name,
                      n.name_en = $name_en, n.category = $category,
                      n.is_core = $is_core, n.specificity = $specificity,
                      n.sensitivity = $sensitivity, n.hpo_id = $hpo_id,
                      n.description = $description,
                      n.abnormal_direction = $abnormal_direction,
                      n.unit = $unit, n.normal_range = $normal_range
        ON MATCH SET
            n.description = CASE WHEN n.description IS NULL OR n.description = ''
                                 THEN $description ELSE n.description END,
            n.is_core = CASE WHEN n.is_core IS NULL THEN $is_core ELSE n.is_core END
        RETURN n
        """
        params = {
            "id": node_id,
            "layer": properties.get("layer", "EL4d"),
            "name": properties.get("name", ""),
            "name_en": properties.get("name_en", ""),
            "category": properties.get("category", ""),
            "is_core": properties.get("is_core", False),
            "specificity": properties.get("specificity", 0.5),
            "sensitivity": properties.get("sensitivity", 0.5),
            "hpo_id": properties.get("hpo_id", ""),
            "description": properties.get("description", ""),
            "abnormal_direction": properties.get("abnormal_direction", ""),
            "unit": properties.get("unit", ""),
            "normal_range": properties.get("normal_range", ""),
        }
        if gid:
            params["gid"] = gid

        try:
            self._run_neo4j_query(query, params)
            self._write_count["nodes"] += 1
            return True
        except Exception as e:
            logger.error(f"Feature node write failed for {node_id}: {e}")
            return False

    def _write_neo4j_guideline(
        self, node_id: str, properties: Dict[str, Any], gid: Optional[str]
    ) -> bool:
        query = """
        MERGE (n:ClinicalGuideline {id: $id})
        ON CREATE SET n.title = $title, n.year = $year,
                      n.organization = $organization, n.doi = $doi,
                      n.description = $description, n.source_file = $source_file
        ON MATCH SET
            n.description = CASE WHEN n.description IS NULL OR n.description = ''
                                 THEN $description ELSE n.description END
        RETURN n
        """
        params = {
            "id": node_id,
            "title": properties.get("title", ""),
            "year": properties.get("year", ""),
            "organization": properties.get("organization", ""),
            "doi": properties.get("doi", ""),
            "description": properties.get("description", ""),
            "source_file": properties.get("source_file", ""),
        }
        if gid:
            params["gid"] = gid

        try:
            self._run_neo4j_query(query, params)
            self._write_count["nodes"] += 1
            return True
        except Exception as e:
            logger.error(f"Guideline node write failed for {node_id}: {e}")
            return False

    def _write_neo4j_relation(
        self,
        source_id: str,
        target_id: str,
        rel_type: str,
        properties: Dict[str, Any],
    ) -> bool:
        safe_rel_type = rel_type.upper()
        query = f"""
        MATCH (a {{id: $src}})
        MATCH (b {{id: $tgt}})
        MERGE (a)-[r:{safe_rel_type}]->(b)
        ON CREATE SET r.confidence = $confidence, r.weight = $weight,
                      r.is_core = $is_core, r.evidence = $evidence
        ON MATCH SET
            r.confidence = CASE WHEN r.confidence IS NULL THEN $confidence ELSE r.confidence END,
            r.weight = CASE WHEN r.weight IS NULL THEN $weight ELSE r.weight END
        RETURN r
        """
        params = {
            "src": source_id,
            "tgt": target_id,
            "confidence": properties.get("confidence", 1.0),
            "weight": properties.get("weight", 1.0),
            "is_core": properties.get("is_core", False),
            "evidence": properties.get("evidence", ""),
        }
        try:
            self._run_neo4j_query(query, params)
            self._write_count["relations"] += 1
            return True
        except Exception as e:
            logger.warning(f"Relation write failed {source_id}-{safe_rel_type}->{target_id}: {e}")
            return False

    def _write_neo4j_contradict(
        self, contra: ContradictEdge, properties: Dict[str, Any]
    ) -> bool:
        query = """
        MATCH (f:Feature {id: $feature_id})
        MATCH (d:Disease {id: $disease_id})
        MERGE (f)-[r:CONTRADICTS]->(d)
        ON CREATE SET r.contradict_condition = $contradict_condition,
                      r.strength = $strength,
                      r.confidence = $confidence,
                      r.weight = $weight,
                      r.evidence = $evidence,
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
            "contradict_condition": properties.get("contradict_condition", ""),
            "strength": properties.get("strength", "moderate"),
            "confidence": properties.get("confidence", 0.8),
            "weight": properties.get("weight", 1.5),
            "evidence": properties.get("evidence", ""),
            "source": properties.get("source", ""),
            "source_page": properties.get("source_page"),
        }
        try:
            self._run_neo4j_query(query, params)
            self._write_count["relations"] += 1
            return True
        except Exception as e:
            logger.warning(f"Contradict edge write failed {contra.feature_id}-CONTRADICTS->{contra.disease_id}: {e}")
            return False
