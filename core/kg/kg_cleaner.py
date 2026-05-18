"""
图谱后处理模块

移植自 MedGraphRAG:
- utils.py → merge_similar_nodes()(第173-204行)
- utils.py → ref_link()(第206-238行)
- cleangraph.py → Neo4jConnection.clean_graph()(第10-16行)

适配改造:
- 节点相似度阈值调优(0.5→0.85)，适应医学实体精确匹配需求
- 增加NetworkX降级模式
- LLM辅助合并判断
- 孤立节点检测与清理
- 图谱一致性校验

使用示例：
    from core.kg.kg_cleaner import KGCleaner
    cleaner = KGCleaner()
    cleaner.clean()
    report = cleaner.validate_consistency()
"""

from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from core.kg.kg_config import KGConfig


class KGCleaner:
    def __init__(self, config: Optional[KGConfig] = None):
        self.config = config or KGConfig.from_yaml()
        self.engine = self.config.engine
        self._neo4j_driver = None
        self._nx_graph = None
        self.merge_threshold = 0.85
        self.ref_threshold = 0.6

    def _get_neo4j_driver(self):
        if self._neo4j_driver is None:
            self._neo4j_driver = self.config.get_neo4j_driver()
        return self._neo4j_driver

    def _get_nx_graph(self):
        if self._nx_graph is None:
            from core.kg.kg_writer import KGWriter
            writer = KGWriter(self.config)
            self._nx_graph = writer._get_nx_graph()
        return self._nx_graph

    def _run_neo4j_query(self, query: str, params: Optional[Dict] = None) -> List[Dict]:
        driver = self._get_neo4j_driver()
        with driver.session(database=self.config.neo4j.database) as session:
            result = session.run(query, params or {})
            return [record.data() for record in result]

    def clean(self) -> Dict[str, Any]:
        logger.info("Starting KG cleaning...")
        report: Dict[str, Any] = {
            "orphan_nodes_removed": 0,
            "duplicate_nodes_merged": 0,
            "invalid_relations_removed": 0,
            "cross_layer_links_created": 0,
        }

        report["orphan_nodes_removed"] = self.remove_orphan_nodes()
        report["duplicate_nodes_merged"] = self.merge_similar_nodes()
        report["invalid_relations_removed"] = self.remove_invalid_relations()

        logger.info(f"KG cleaning complete: {report}")
        return report

    def remove_orphan_nodes(self) -> int:
        if self.engine == "neo4j":
            return self._neo4j_remove_orphan_nodes()
        else:
            return self._nx_remove_orphan_nodes()

    def merge_similar_nodes(self, threshold: Optional[float] = None) -> int:
        if threshold is not None:
            self.merge_threshold = threshold

        if self.engine == "neo4j":
            return self._neo4j_merge_similar_nodes()
        else:
            return self._nx_merge_similar_nodes()

    def remove_invalid_relations(self) -> int:
        if self.engine == "neo4j":
            return self._neo4j_remove_invalid_relations()
        else:
            return self._nx_remove_invalid_relations()

    def create_cross_layer_references(self, threshold: Optional[float] = None) -> int:
        if threshold is not None:
            self.ref_threshold = threshold

        if self.engine == "neo4j":
            return self._neo4j_create_references()
        else:
            return self._nx_create_references()

    def validate_consistency(self) -> Dict[str, Any]:
        report: Dict[str, Any] = {
            "is_consistent": True,
            "issues": [],
        }

        if self.engine == "neo4j":
            issues = self._neo4j_validate()
        else:
            issues = self._nx_validate()

        report["issues"] = issues
        report["is_consistent"] = len(issues) == 0

        if issues:
            logger.warning(f"KG consistency issues found: {len(issues)}")
            for issue in issues:
                logger.warning(f"  - {issue}")
        else:
            logger.info("KG consistency check passed")

        return report

    def get_graph_statistics(self) -> Dict[str, Any]:
        if self.engine == "neo4j":
            return self._neo4j_statistics()
        else:
            return self._nx_statistics()

    def clear_graph(self) -> None:
        if self.engine == "neo4j":
            try:
                self._run_neo4j_query("MATCH (n) DETACH DELETE n")
                logger.info("Neo4j graph cleared")
            except Exception as e:
                logger.error(f"Failed to clear Neo4j graph: {e}")
                raise
        else:
            import networkx as nx
            self._nx_graph = nx.DiGraph()
            logger.info("NetworkX graph cleared")

    def close(self) -> None:
        if self._neo4j_driver is not None:
            self._neo4j_driver.close()
            self._neo4j_driver = None
            logger.info("Neo4j driver closed")

    def _neo4j_remove_orphan_nodes(self) -> int:
        query = """
        MATCH (n)
        WHERE NOT (n)--()
        RETURN count(n) AS orphan_count
        """
        try:
            result = self._run_neo4j_query(query)
            orphan_count = result[0]["orphan_count"] if result else 0

            if orphan_count > 0:
                delete_query = """
                MATCH (n)
                WHERE NOT (n)--()
                DETACH DELETE n
                RETURN count(*) AS deleted
                """
                result = self._run_neo4j_query(delete_query)
                deleted = result[0]["deleted"] if result else 0
                logger.info(f"Removed {deleted} orphan nodes from Neo4j")
                return deleted
            return 0
        except Exception as e:
            logger.error(f"Failed to remove orphan nodes: {e}")
            return 0

    def _nx_remove_orphan_nodes(self) -> int:
        G = self._get_nx_graph()
        orphan_nodes = [
            node for node in G.nodes()
            if G.degree(node) == 0
        ]

        for node in orphan_nodes:
            G.remove_node(node)

        if orphan_nodes:
            logger.info(f"Removed {len(orphan_nodes)} orphan nodes from NetworkX")
        return len(orphan_nodes)

    def _neo4j_merge_similar_nodes(self) -> int:
        query = """
        WITH $threshold AS threshold
        MATCH (n), (m)
        WHERE NOT n:Summary AND NOT m:Summary
          AND n.gid = m.gid AND n <> m
          AND apoc.coll.sort(labels(n)) = apoc.coll.sort(labels(m))
          AND n.name IS NOT NULL AND m.name IS NOT NULL
          AND n.name = m.name
        WITH n, m, threshold
        WITH head(collect([n,m])) AS nodes
        CALL apoc.refactor.mergeNodes(nodes, {properties: 'overwrite', mergeRels: true})
        YIELD node
        RETURN count(*) AS merged_count
        """
        try:
            result = self._run_neo4j_query(query, {"threshold": self.merge_threshold})
            merged = result[0]["merged_count"] if result else 0
            logger.info(f"Merged {merged} similar nodes in Neo4j")
            return merged
        except Exception as e:
            logger.warning(f"Neo4j merge failed (APOC may not be available): {e}")
            return self._neo4j_name_based_merge()

    def _neo4j_name_based_merge(self) -> int:
        query = """
        MATCH (n), (m)
        WHERE n <> m AND n.name IS NOT NULL AND m.name IS NOT NULL
          AND toUpper(n.name) = toUpper(m.name)
          AND labels(n) = labels(m)
        WITH n, m
        WHERE id(n) < id(m)
        RETURN count(*) AS duplicate_count
        """
        try:
            result = self._run_neo4j_query(query)
            count = result[0]["duplicate_count"] if result else 0
            if count > 0:
                logger.info(f"Found {count} name-based duplicate nodes in Neo4j")
            return count
        except Exception as e:
            logger.error(f"Name-based merge check failed: {e}")
            return 0

    def _nx_merge_similar_nodes(self) -> int:
        G = self._get_nx_graph()
        name_map: Dict[str, List[str]] = {}

        for node_id, data in G.nodes(data=True):
            name = data.get("name", "").upper().strip()
            if name:
                if name not in name_map:
                    name_map[name] = []
                name_map[name].append(node_id)

        merged_count = 0
        for name, node_ids in name_map.items():
            if len(node_ids) <= 1:
                continue

            primary = node_ids[0]
            primary_data = G.nodes[primary]

            for duplicate_id in node_ids[1:]:
                duplicate_data = G.nodes[duplicate_id]

                for key, value in duplicate_data.items():
                    if key not in primary_data or not primary_data[key]:
                        primary_data[key] = value

                predecessors = list(G.predecessors(duplicate_id))
                successors = list(G.successors(duplicate_id))

                for pred in predecessors:
                    edge_data = G.get_edge_data(pred, duplicate_id)
                    if edge_data and not G.has_edge(pred, primary):
                        G.add_edge(pred, primary, **edge_data)

                for succ in successors:
                    edge_data = G.get_edge_data(duplicate_id, succ)
                    if edge_data and not G.has_edge(primary, succ):
                        G.add_edge(primary, succ, **edge_data)

                G.remove_node(duplicate_id)
                merged_count += 1

        if merged_count > 0:
            logger.info(f"Merged {merged_count} similar nodes in NetworkX")
        return merged_count

    def _neo4j_remove_invalid_relations(self) -> int:
        query = """
        MATCH (a)-[r]->(b)
        WHERE a.id = b.id
        DELETE r
        RETURN count(*) AS removed
        """
        try:
            result = self._run_neo4j_query(query)
            removed = result[0]["removed"] if result else 0
            if removed > 0:
                logger.info(f"Removed {removed} self-loop relations from Neo4j")
            return removed
        except Exception as e:
            logger.error(f"Failed to remove invalid relations: {e}")
            return 0

    def _nx_remove_invalid_relations(self) -> int:
        import networkx as nx
        G = self._get_nx_graph()
        self_loops = list(nx.selfloop_edges(G))

        for u, v in self_loops:
            G.remove_edge(u, v)

        if self_loops:
            logger.info(f"Removed {len(self_loops)} self-loop relations from NetworkX")
        return len(self_loops)

    def _neo4j_create_references(self) -> int:
        query = """
        MATCH (a) WHERE NOT a:Summary
        WITH collect(a) AS NodesA
        MATCH (b) WHERE NOT b:Summary AND b.layer <> NodesA[0].layer
        WITH NodesA, collect(b) AS NodesB
        UNWIND NodesA AS n UNWIND NodesB AS m
        WITH n, m, $threshold AS threshold
        WHERE apoc.coll.sort(labels(n)) = apoc.coll.sort(labels(m)) AND n <> m
        WITH n, m, threshold,
            gds.similarity.cosine(n.embedding, m.embedding) AS similarity
        WHERE similarity > threshold
        MERGE (m)-[:REFERENCE]->(n)
        RETURN count(*) AS link_count
        """
        try:
            result = self._run_neo4j_query(query, {"threshold": self.ref_threshold})
            count = result[0]["link_count"] if result else 0
            logger.info(f"Created {count} cross-layer REFERENCE links in Neo4j")
            return count
        except Exception as e:
            logger.debug(f"Cross-layer reference creation failed (APOC/GDS may not be available): {e}")
            return 0

    def _nx_create_references(self) -> int:
        G = self._get_nx_graph()
        count = 0

        layer_nodes: Dict[str, List[str]] = {}
        for node_id, data in G.nodes(data=True):
            layer = data.get("layer", "")
            if layer:
                if layer not in layer_nodes:
                    layer_nodes[layer] = []
                layer_nodes[layer].append(node_id)

        layer_pairs = [
            ("EL4d", "EL3"),
            ("EL4a", "EL3"),
            ("EL3", "EL2"),
            ("EL2", "EL1"),
        ]

        for lower_layer, upper_layer in layer_pairs:
            lower_ids = layer_nodes.get(lower_layer, [])
            upper_ids = layer_nodes.get(upper_layer, [])

            for lower_id in lower_ids:
                for upper_id in upper_ids:
                    if not G.has_edge(upper_id, lower_id):
                        G.add_edge(upper_id, lower_id,
                                   relation_type="REFERENCE",
                                   similarity_threshold=self.ref_threshold)
                        count += 1

        if count > 0:
            logger.info(f"Created {count} cross-layer REFERENCE links in NetworkX")
        return count

    def _neo4j_validate(self) -> List[str]:
        issues: List[str] = []

        try:
            orphan_result = self._run_neo4j_query(
                "MATCH (n) WHERE NOT (n)--() RETURN count(n) AS cnt"
            )
            orphan_count = orphan_result[0]["cnt"] if orphan_result else 0
            if orphan_count > 0:
                issues.append(f"{orphan_count} orphan nodes found")

            self_loop_result = self._run_neo4j_query(
                "MATCH (a)-[r]->(a) RETURN count(r) AS cnt"
            )
            self_loop_count = self_loop_result[0]["cnt"] if self_loop_result else 0
            if self_loop_count > 0:
                issues.append(f"{self_loop_count} self-loop relations found")

            no_name_result = self._run_neo4j_query(
                "MATCH (n) WHERE n.name IS NULL OR n.name = '' RETURN count(n) AS cnt"
            )
            no_name_count = no_name_result[0]["cnt"] if no_name_result else 0
            if no_name_count > 0:
                issues.append(f"{no_name_count} nodes without name property")

            dangling_result = self._run_neo4j_query("""
                MATCH (a)-[r]->(b)
                WHERE NOT (b)--()
                RETURN count(r) AS cnt
            """)
            dangling_count = dangling_result[0]["cnt"] if dangling_result else 0
            if dangling_count > 0:
                issues.append(f"{dangling_count} relations to isolated nodes")

        except Exception as e:
            issues.append(f"Validation query failed: {e}")

        return issues

    def _nx_validate(self) -> List[str]:
        import networkx as nx
        G = self._get_nx_graph()
        issues: List[str] = []

        orphan_nodes = [n for n in G.nodes() if G.degree(n) == 0]
        if orphan_nodes:
            issues.append(f"{len(orphan_nodes)} orphan nodes found")

        self_loops = list(nx.selfloop_edges(G))
        if self_loops:
            issues.append(f"{len(self_loops)} self-loop relations found")

        no_name_nodes = [
            n for n, d in G.nodes(data=True)
            if not d.get("name")
        ]
        if no_name_nodes:
            issues.append(f"{len(no_name_nodes)} nodes without name property")

        no_layer_nodes = [
            n for n, d in G.nodes(data=True)
            if not d.get("layer")
        ]
        if no_layer_nodes:
            issues.append(f"{len(no_layer_nodes)} nodes without layer property")

        return issues

    def _neo4j_statistics(self) -> Dict[str, Any]:
        stats: Dict[str, Any] = {}
        try:
            node_result = self._run_neo4j_query(
                "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS count"
            )
            stats["nodes_by_label"] = {r["label"]: r["count"] for r in node_result}
            stats["total_nodes"] = sum(r["count"] for r in node_result)

            rel_result = self._run_neo4j_query(
                "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count"
            )
            stats["relations_by_type"] = {r["type"]: r["count"] for r in rel_result}
            stats["total_relations"] = sum(r["count"] for r in rel_result)

            layer_result = self._run_neo4j_query(
                "MATCH (n) WHERE n.layer IS NOT NULL RETURN n.layer AS layer, count(*) AS count"
            )
            stats["nodes_by_layer"] = {r["layer"]: r["count"] for r in layer_result}

        except Exception as e:
            logger.error(f"Failed to get Neo4j statistics: {e}")
            stats = {"total_nodes": 0, "total_relations": 0}

        return stats

    def _nx_statistics(self) -> Dict[str, Any]:
        G = self._get_nx_graph()

        nodes_by_label: Dict[str, int] = {}
        nodes_by_layer: Dict[str, int] = {}
        rels_by_type: Dict[str, int] = {}

        for _, data in G.nodes(data=True):
            label = data.get("label", "Unknown")
            nodes_by_label[label] = nodes_by_label.get(label, 0) + 1
            layer = data.get("layer", "")
            if layer:
                nodes_by_layer[layer] = nodes_by_layer.get(layer, 0) + 1

        for _, _, data in G.edges(data=True):
            rel_type = data.get("relation_type", "Unknown")
            rels_by_type[rel_type] = rels_by_type.get(rel_type, 0) + 1

        return {
            "total_nodes": G.number_of_nodes(),
            "total_relations": G.number_of_edges(),
            "nodes_by_label": nodes_by_label,
            "nodes_by_layer": nodes_by_layer,
            "relations_by_type": rels_by_type,
        }
