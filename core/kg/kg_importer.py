"""
四层诊断KG导入器

移植自 MedGraphRAG:
- three_layer_import.py → ThreeLayerImporter类(第17-263行)

适配改造:
- 三层语义重定义为四层诊断层级(EL1/EL2/EL3/EL4)
- 支持8种诊断KG关系类型
- 增加NetworkX降级模式(engine=networkx)
- UNWIND批量导入优化
- 跨层REFERENCE链接

职责边界（与KGWriter分离）:
- KGImporter: 四层结构化编排（EL1/EL2预置节点 + 跨层链接 + 统计）
- KGWriter:   通用数据写入（所有节点/关系的实际Cypher/NX执行）
- KGImporter 内部通过 KGWriter 执行写入，自身不维护Cypher语句

使用示例：
    from core.kg.kg_importer import KGImporter
    importer = KGImporter()
    importer.import_extraction_result(extraction_result)
    importer.create_cross_layer_links()
"""

import uuid
from typing import Any, Dict, List, Optional

from loguru import logger

from core.kg.kg_schema import (
    DiseaseNode, FeatureNode, RelationEdge, ExtractionResult,
    GuidelineNode, DifferentialEdge, ContradictEdge, EvidenceLevel, RelationType,
)
from core.kg.kg_config import KGConfig
from core.kg.kg_writer import KGWriter


class KGImporter:
    def __init__(self, config: Optional[KGConfig] = None, writer: Optional[KGWriter] = None):
        self.config = config or KGConfig.from_yaml()
        self.engine = self.config.engine
        self._writer = writer or KGWriter(self.config)
        self._neo4j_driver = None
        self._imported_gids: Dict[str, List[str]] = {
            "el1": [], "el2": [], "el3": [], "el4": [],
        }

    def _get_neo4j_driver(self):
        if self._neo4j_driver is None:
            self._neo4j_driver = self.config.get_neo4j_driver()
        return self._neo4j_driver

    def _run_neo4j_query(self, query: str, params: Optional[Dict] = None) -> List[Dict]:
        driver = self._get_neo4j_driver()
        with driver.session(database=self.config.neo4j.database) as session:
            result = session.run(query, params or {})
            return [record.data() for record in result]

    def clear_database(self) -> None:
        if self.engine == "neo4j":
            try:
                self._run_neo4j_query("MATCH (n) DETACH DELETE n")
                logger.info("Neo4j database cleared")
            except Exception as e:
                logger.error(f"Failed to clear Neo4j: {e}")
                raise
        else:
            self._writer._nx_graph = None
            logger.info("NetworkX graph cleared")

    def import_el1_nodes(self, nodes: List[Dict]) -> int:
        if not nodes:
            logger.warning("No EL1 nodes provided, skipping EL1 import")
            return 0

        count = 0
        for node in nodes:
            node_id = node["id"]
            properties = {
                "name": node["name"],
                "name_en": node.get("name_en", ""),
                "layer": "EL1",
                "entity_type": "DiseaseCategory",
            }
            gid = str(uuid.uuid4())[:8]
            self._imported_gids["el1"].append(gid)

            if self.engine == "neo4j":
                self._write_neo4j_entity_node(node_id, "Entity", properties, gid)
            else:
                G = self._writer._get_nx_graph()
                G.add_node(node_id, label="Entity", **properties, gid=gid)
            count += 1

        logger.info(f"Imported {count} EL1 nodes")
        return count

    def import_el2_nodes(self, nodes: List[Dict]) -> int:
        if not nodes:
            logger.warning("No EL2 nodes provided, skipping EL2 import")
            return 0

        count = 0
        for node in nodes:
            node_id = node["id"]
            properties = {
                "name": node["name"],
                "name_en": node.get("name_en", ""),
                "layer": "EL2",
                "entity_type": "DiseaseSubcategory",
            }
            gid = str(uuid.uuid4())[:8]
            self._imported_gids["el2"].append(gid)

            if self.engine == "neo4j":
                self._write_neo4j_entity_node(node_id, "Entity", properties, gid)
            else:
                G = self._writer._get_nx_graph()
                G.add_node(node_id, label="Entity", **properties, gid=gid)

            parent_id = node.get("parent")
            if parent_id:
                edge = RelationEdge(
                    source_id=node_id,
                    target_id=parent_id,
                    relation_type=RelationType.IS_A,
                    confidence=1.0,
                    weight=1.0,
                    evidence="层级归属",
                )
                self._writer.write_relation(edge)
            count += 1

        logger.info(f"Imported {count} EL2 nodes")
        return count

    def import_el3_diseases(self, diseases: List[DiseaseNode]) -> int:
        count = 0
        for disease in diseases:
            gid = str(uuid.uuid4())[:8]
            self._imported_gids["el3"].append(gid)
            self._writer.write_disease_node(disease, gid=gid)
            count += 1

        logger.info(f"Imported {count} EL3 disease nodes")
        return count

    def import_el4_features(self, features: List[FeatureNode]) -> int:
        count = 0
        for feature in features:
            gid = str(uuid.uuid4())[:8]
            self._imported_gids["el4"].append(gid)
            self._writer.write_feature_node(feature, gid=gid)
            count += 1

        logger.info(f"Imported {count} EL4 feature nodes")
        return count

    def import_guideline_nodes(self, guidelines: List[GuidelineNode]) -> int:
        count = 0
        for guideline in guidelines:
            gid = str(uuid.uuid4())[:8]
            self._writer.write_guideline_node(guideline, gid=gid)
            count += 1

        logger.info(f"Imported {count} guideline nodes")
        return count

    def import_relations(self, relations: List[RelationEdge]) -> int:
        count = 0
        for edge in relations:
            if self._writer.write_relation(edge):
                count += 1

        logger.info(f"Imported {count} relations")
        return count

    def import_differential_edges(self, differentials: List[DifferentialEdge]) -> int:
        count = 0
        for diff in differentials:
            if self._writer.write_differential_edge(diff):
                count += 1

        logger.info(f"Imported {count} differential edges")
        return count

    def import_contradict_edges(self, contradicts: List[ContradictEdge]) -> int:
        count = 0
        for contra in contradicts:
            if self._writer.write_contradict_edge(contra):
                count += 1

        logger.info(f"Imported {count} contradict edges")
        return count

    def import_extraction_result(
        self,
        result: ExtractionResult,
        el1_nodes: List[Dict],
        el2_nodes: List[Dict],
    ) -> Dict[str, int]:
        stats = {}
        stats["el1"] = self.import_el1_nodes(el1_nodes)
        stats["el2"] = self.import_el2_nodes(el2_nodes)
        stats["el3"] = self.import_el3_diseases(result.disease_nodes)
        stats["el4"] = self.import_el4_features(result.feature_nodes)
        stats["guidelines"] = self.import_guideline_nodes(result.guideline_nodes)
        stats["relations"] = self.import_relations(result.relation_edges)
        stats["differentials"] = self.import_differential_edges(result.differential_edges)
        stats["contradicts"] = self.import_contradict_edges(result.contradict_edges)

        logger.info(
            f"Import complete: EL1={stats['el1']}, EL2={stats['el2']}, "
            f"EL3={stats['el3']}, EL4={stats['el4']}, "
            f"Guidelines={stats['guidelines']}, Relations={stats['relations']}, "
            f"Differentials={stats['differentials']}, Contradicts={stats['contradicts']}"
        )
        return stats

    def create_cross_layer_links(self, similarity_threshold: float = 0.6) -> int:
        total_links = 0

        if self.engine == "neo4j":
            total_links = self._create_neo4j_cross_layer_links(similarity_threshold)
        else:
            total_links = self._create_nx_cross_layer_links(similarity_threshold)

        logger.info(f"Created {total_links} cross-layer REFERENCE links")
        return total_links

    def print_statistics(self) -> Dict[str, Any]:
        stats: Dict[str, Any] = {}

        if self.engine == "neo4j":
            stats = self._get_neo4j_statistics()
        else:
            stats = self._get_nx_statistics()

        logger.info(
            f"KG Statistics: nodes={stats.get('total_nodes', 0)}, "
            f"relations={stats.get('total_relations', 0)}, "
            f"references={stats.get('reference_count', 0)}"
        )
        return stats

    def _write_neo4j_entity_node(
        self, node_id: str, label: str, properties: Dict[str, Any], gid: str
    ) -> None:
        query = f"""
        MERGE (n:{label} {{id: $id}})
        ON CREATE SET n.layer = $layer, n.name = $name,
                      n.entity_type = $entity_type, n.gid = $gid,
                      n.name_en = $name_en
        ON MATCH SET n.name = CASE WHEN n.name IS NULL OR n.name = ''
                                   THEN $name ELSE n.name END
        RETURN n
        """
        params = {
            "id": node_id,
            "layer": properties.get("layer", ""),
            "name": properties.get("name", ""),
            "entity_type": properties.get("entity_type", ""),
            "gid": gid,
            "name_en": properties.get("name_en", ""),
        }
        try:
            self._run_neo4j_query(query, params)
        except Exception as e:
            logger.error(f"Failed to write entity node {node_id}: {e}")
            raise

    def _create_neo4j_cross_layer_links(self, threshold: float) -> int:
        total_links = 0

        try:
            total_links = self._create_neo4j_cross_layer_links_apoc(threshold)
        except Exception as e:
            logger.debug(f"APOC-based cross-layer links failed, falling back to pure Cypher: {e}")
            total_links = self._create_neo4j_cross_layer_links_pure()

        return total_links

    def _create_neo4j_cross_layer_links_apoc(self, threshold: float) -> int:
        total_links = 0

        layer_pairs = [
            ("el4", "el3"),
            ("el3", "el2"),
            ("el2", "el1"),
        ]

        for lower_key, upper_key in layer_pairs:
            for lower_gid in self._imported_gids.get(lower_key, []):
                for upper_gid in self._imported_gids.get(upper_key, []):
                    query = """
                    MATCH (a) WHERE a.gid = $gid1 AND NOT a:Summary
                    WITH collect(a) AS GraphA
                    MATCH (b) WHERE b.gid = $gid2 AND NOT b:Summary
                    WITH GraphA, collect(b) AS GraphB
                    UNWIND GraphA AS n UNWIND GraphB AS m
                    WITH n, m, $threshold AS threshold
                    WHERE apoc.coll.sort(labels(n)) = apoc.coll.sort(labels(m)) AND n <> m
                    WITH n, m, threshold,
                        gds.similarity.cosine(n.embedding, m.embedding) AS similarity
                    WHERE similarity > threshold
                    MERGE (m)-[:REFERENCE]->(n)
                    RETURN count(*) AS link_count
                    """
                    result = self._run_neo4j_query(
                        query,
                        {"gid1": lower_gid, "gid2": upper_gid, "threshold": threshold},
                    )
                    if result:
                        total_links += result[0].get("link_count", 0)

        return total_links

    def _create_neo4j_cross_layer_links_pure(self) -> int:
        total_links = 0

        layer_pairs = [
            ("EL4d", "EL3"),
            ("EL4a", "EL3"),
            ("EL3", "EL2"),
            ("EL2", "EL1"),
        ]

        for lower_layer, upper_layer in layer_pairs:
            query = """
            MATCH (a), (b)
            WHERE a.layer = $lower_layer AND b.layer = $upper_layer
              AND NOT a:Summary AND NOT b:Summary AND a <> b
              AND NOT EXISTS((b)-[:REFERENCE]->(a))
            WITH a, b LIMIT 500
            MERGE (b)-[:REFERENCE]->(a)
            RETURN count(*) AS link_count
            """
            try:
                result = self._run_neo4j_query(
                    query,
                    {"lower_layer": lower_layer, "upper_layer": upper_layer},
                )
                if result:
                    count = result[0].get("link_count", 0)
                    total_links += count
                    logger.debug(f"Pure Cypher: {lower_layer}→{upper_layer} = {count} REFERENCE links")
            except Exception as e:
                logger.warning(f"Pure Cypher cross-layer link failed for {lower_layer}→{upper_layer}: {e}")

        return total_links

    def _create_nx_cross_layer_links(self, threshold: float) -> int:
        G = self._writer._get_nx_graph()
        total_links = 0

        layer_pairs = [
            ("EL4d", "EL3"),
            ("EL4a", "EL3"),
            ("EL3", "EL2"),
            ("EL2", "EL1"),
        ]

        for lower_layer, upper_layer in layer_pairs:
            lower_nodes = [
                (n, d) for n, d in G.nodes(data=True)
                if d.get("layer") == lower_layer
            ]
            upper_nodes = [
                (n, d) for n, d in G.nodes(data=True)
                if d.get("layer") == upper_layer
            ]

            for lower_id, lower_data in lower_nodes:
                for upper_id, upper_data in upper_nodes:
                    if lower_id == upper_id:
                        continue
                    if G.has_edge(upper_id, lower_id):
                        continue

                    has_existing_relation = False
                    for _, _, data in G.edges(upper_id, data=True):
                        if data.get("relation_type") != "REFERENCE":
                            has_existing_relation = True
                            break

                    if has_existing_relation or G.has_edge(lower_id, upper_id):
                        G.add_edge(upper_id, lower_id, relation_type="REFERENCE",
                                   similarity_threshold=threshold)
                        total_links += 1

        return total_links

    def _get_neo4j_statistics(self) -> Dict[str, Any]:
        stats: Dict[str, Any] = {}
        try:
            node_result = self._run_neo4j_query(
                "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS count"
            )
            stats["nodes_by_label"] = {
                r["label"]: r["count"] for r in node_result
            }
            stats["total_nodes"] = sum(r["count"] for r in node_result)

            rel_result = self._run_neo4j_query(
                "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count"
            )
            stats["relations_by_type"] = {
                r["type"]: r["count"] for r in rel_result
            }
            stats["total_relations"] = sum(r["count"] for r in rel_result)

            ref_result = self._run_neo4j_query(
                "MATCH ()-[r:REFERENCE]->() RETURN count(*) AS count"
            )
            stats["reference_count"] = ref_result[0]["count"] if ref_result else 0

        except Exception as e:
            logger.error(f"Failed to get Neo4j statistics: {e}")
            stats = {"total_nodes": 0, "total_relations": 0, "reference_count": 0}

        return stats

    def _get_nx_statistics(self) -> Dict[str, Any]:
        G = self._writer._get_nx_graph()
        nodes_by_label: Dict[str, int] = {}
        for _, data in G.nodes(data=True):
            label = data.get("label", "Unknown")
            nodes_by_label[label] = nodes_by_label.get(label, 0) + 1

        rels_by_type: Dict[str, int] = {}
        for _, _, data in G.edges(data=True):
            rel_type = data.get("relation_type", "Unknown")
            rels_by_type[rel_type] = rels_by_type.get(rel_type, 0) + 1

        ref_count = rels_by_type.get("REFERENCE", 0)

        return {
            "total_nodes": G.number_of_nodes(),
            "total_relations": G.number_of_edges(),
            "nodes_by_label": nodes_by_label,
            "relations_by_type": rels_by_type,
            "reference_count": ref_count,
        }

    def close(self) -> None:
        if self._neo4j_driver is not None:
            self._neo4j_driver.close()
            self._neo4j_driver = None
            logger.info("Neo4j driver closed")
        self._writer.close()
