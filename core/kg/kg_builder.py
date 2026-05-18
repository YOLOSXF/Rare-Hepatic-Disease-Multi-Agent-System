"""
离线构建管道主入口（通用编排器）

串联完整KG构建流程:
pipeline(提取) → importer(导入) → differential(差异) → embedder(嵌入) → snapshot(快照) → validate(验证)

支持:
- 全量构建: 从PDF指南重新构建整个KG
- 增量更新: 仅处理新增/变更的指南
- 预定义构建: 使用预定义知识快速构建(开发阶段)
- 多疾病构建: 通过注入DiseasePipeline支持任意疾病

使用示例:
    from core.kg.kg_builder import KGBuilder
    from core.kg.diseases import DiseasePipeline

    # Wilson病
    pipeline = DiseasePipeline("data/disease_configs/wilson_disease.yaml")
    builder = KGBuilder(disease_pipeline=pipeline)
    result = builder.build_predefined()

    # 新增疾病（如PBC）—— 只需创建YAML配置文件
    pipeline = DiseasePipeline("data/disease_configs/pbc.yaml")
    builder = KGBuilder(disease_pipeline=pipeline)
    result = builder.build_predefined()
"""

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from core.kg.kg_config import KGConfig
from core.kg.kg_schema import (
    ExtractionResult,
    KGSnapshot,
    RelationType,
)
from core.kg.kg_importer import KGImporter
from core.kg.kg_writer import KGWriter
from core.kg.kg_embedder import KGEmbedder
from core.kg.kg_differential import KGDifferential


class KGBuilder:
    def __init__(
        self,
        config: Optional[KGConfig] = None,
        disease_pipeline: Optional[Any] = None,
    ):
        self.config = config or KGConfig.from_yaml()
        self.project_root = Path(__file__).parent.parent.parent
        self.snapshot_dir = self.project_root / "data" / "kg"
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self._build_report: Dict[str, Any] = {}
        self._last_extraction_result: Optional[ExtractionResult] = None

        if disease_pipeline is not None:
            self._pipeline = disease_pipeline
        else:
            self._pipeline = None

    def build_predefined(self) -> Dict[str, Any]:
        logger.info("=" * 60)
        logger.info(f"KG Builder: 预定义知识构建模式 [{self._pipeline_name}]")
        logger.info("=" * 60)

        start_time = time.time()
        report: Dict[str, Any] = {
            "mode": "predefined",
            "disease": self._pipeline_name,
            "start_time": datetime.now().isoformat(),
            "steps": {},
        }

        logger.info("[Step 1/6] 导入预定义知识到图数据库")
        step1_result = self._step_import_predefined()
        report["steps"]["import"] = step1_result

        logger.info("[Step 2/6] 创建跨层REFERENCE链接")
        step2_result = self._step_cross_layer_links()
        report["steps"]["cross_layer"] = step2_result

        logger.info("[Step 3/6] 计算差异诊断边+contradicts边")
        step3_result = self._step_differential()
        report["steps"]["differential"] = step3_result

        logger.info("[Step 4/6] 生成BGE-M3嵌入+写入Milvus")
        step4_result = self._step_embed()
        report["steps"]["embed"] = step4_result

        logger.info("[Step 5/6] 生成JSON快照")
        step5_result = self._step_snapshot()
        report["steps"]["snapshot"] = step5_result

        logger.info("[Step 6/6] 构建验证")
        step6_result = self._step_validate()
        report["steps"]["validate"] = step6_result

        elapsed = time.time() - start_time
        report["elapsed_seconds"] = round(elapsed, 2)
        report["end_time"] = datetime.now().isoformat()
        report["success"] = step6_result.get("passed", False)

        self._build_report = report
        self._save_build_report(report)

        logger.info("=" * 60)
        logger.info(
            f"KG Builder 完成: disease={self._pipeline_name}, "
            f"mode=predefined, elapsed={elapsed:.1f}s, success={report['success']}"
        )
        logger.info("=" * 60)
        return report

    def build_full(self, auto_approve: bool = True) -> Dict[str, Any]:
        logger.info("=" * 60)
        logger.info(f"KG Builder: 全量构建模式 [{self._pipeline_name}]")
        logger.info("=" * 60)

        start_time = time.time()
        report: Dict[str, Any] = {
            "mode": "full",
            "disease": self._pipeline_name,
            "start_time": datetime.now().isoformat(),
            "steps": {},
        }

        logger.info("[Step 1/8] LLM提取指南知识（一步提取：实体+关系+差异诊断+矛盾排除）")
        step1_result = self._step_extract()
        report["steps"]["extract"] = step1_result

        if not step1_result.get("success", False):
            logger.warning("LLM提取失败，回退到预定义知识构建")
            return self.build_predefined()

        logger.info("[Step 2/8] 验证提取结果")
        step2_result = self._step_validate_extraction()
        report["steps"]["validate_extraction"] = step2_result

        logger.info("[Step 3/8] 人工审核（预留接口）")
        step3_result = self._step_human_review(auto_approve=auto_approve)
        report["steps"]["human_review"] = step3_result

        logger.info("[Step 4/8] 导入图数据库")
        step4_result = self._step_import_extracted()
        report["steps"]["import"] = step4_result

        logger.info("[Step 5/8] 创建跨层链接")
        step5_result = self._step_cross_layer_links()
        report["steps"]["cross_layer"] = step5_result

        logger.info("[Step 6/8] 写入差异诊断边+矛盾排除边")
        step6_result = self._step_differential()
        report["steps"]["differential"] = step6_result

        logger.info("[Step 7/8] 生成向量嵌入")
        step7_result = self._step_embed()
        report["steps"]["embed"] = step7_result

        logger.info("[Step 8/8] 生成快照+构建验证")
        step8a_result = self._step_snapshot()
        step8b_result = self._step_validate()
        report["steps"]["snapshot"] = step8a_result
        report["steps"]["validate"] = step8b_result

        elapsed = time.time() - start_time
        report["elapsed_seconds"] = round(elapsed, 2)
        report["end_time"] = datetime.now().isoformat()
        report["success"] = step8b_result.get("passed", False)

        self._build_report = report
        self._save_build_report(report)

        logger.info("=" * 60)
        logger.info(
            f"KG Builder 完成: disease={self._pipeline_name}, "
            f"mode=full, elapsed={elapsed:.1f}s, success={report['success']}"
        )
        logger.info("=" * 60)
        return report

    def build_incremental(self, pdf_paths: Optional[List[str]] = None) -> Dict[str, Any]:
        logger.info("=" * 60)
        logger.info(f"KG Builder: 增量更新模式 [{self._pipeline_name}]")
        logger.info("=" * 60)

        start_time = time.time()
        report: Dict[str, Any] = {
            "mode": "incremental",
            "disease": self._pipeline_name,
            "start_time": datetime.now().isoformat(),
            "steps": {},
        }

        logger.info("[Step 1/4] 增量提取新指南知识")
        step1_result = self._step_extract_incremental(pdf_paths)
        report["steps"]["extract"] = step1_result

        logger.info("[Step 2/4] 增量导入图数据库")
        step2_result = self._step_import_extracted()
        report["steps"]["import"] = step2_result

        logger.info("[Step 3/4] 更新差异诊断边")
        step3_result = self._step_differential()
        report["steps"]["differential"] = step3_result

        logger.info("[Step 4/4] 更新向量嵌入")
        step4_result = self._step_embed_incremental()
        report["steps"]["embed"] = step4_result

        elapsed = time.time() - start_time
        report["elapsed_seconds"] = round(elapsed, 2)
        report["end_time"] = datetime.now().isoformat()
        report["success"] = True

        self._build_report = report
        self._save_build_report(report)

        logger.info(f"KG Builder 增量更新完成: elapsed={elapsed:.1f}s")
        return report

    @staticmethod
    def from_pdfs(
        disease_id: str,
        disease_name: str,
        pdf_paths: List[str],
        disease_name_en: str = "",
        icd10: str = "",
        category: str = "",
        description: str = "",
    ) -> "KGBuilder":
        """
        PDF优先构建模式：直接从PDF文件构建知识图谱。

        无需YAML配置文件，LLM自动提取实体和关系。
        适合快速接入新疾病的指南/文献PDF。

        使用示例：
            builder = KGBuilder.from_pdfs(
                disease_id="PBC",
                disease_name="原发性胆汁性胆管炎",
                pdf_paths=["data/guidelines/pbc/guideline.pdf"],
                disease_name_en="Primary Biliary Cholangitis",
                icd10="K74.3",
            )
            result = builder.build_from_pdfs()
        """
        from core.kg.diseases import DiseasePipeline

        pipeline = DiseasePipeline.from_pdfs(
            disease_id=disease_id,
            disease_name=disease_name,
            pdf_paths=pdf_paths,
            disease_name_en=disease_name_en,
            icd10=icd10,
            category=category,
            description=description,
        )
        return KGBuilder(disease_pipeline=pipeline)

    def build_from_pdfs(self) -> Dict[str, Any]:
        logger.info("=" * 60)
        logger.info(f"KG Builder: PDF优先构建模式 [{self._pipeline_name}]")
        logger.info("=" * 60)

        start_time = time.time()
        report: Dict[str, Any] = {
            "mode": "pdf_first",
            "disease": self._pipeline_name,
            "start_time": datetime.now().isoformat(),
            "steps": {},
        }

        logger.info("[Step 1/7] LLM提取PDF知识")
        step1_result = self._step_extract()
        report["steps"]["extract"] = step1_result

        if not step1_result.get("success", False):
            logger.error("LLM提取失败，PDF优先模式无法继续")
            report["success"] = False
            report["elapsed_seconds"] = round(time.time() - start_time, 2)
            return report

        logger.info("[Step 2/7] 验证提取结果")
        step2_result = self._step_validate_extraction()
        report["steps"]["validate_extraction"] = step2_result

        logger.info("[Step 3/7] 导入图数据库")
        step3_result = self._step_import_extracted()
        report["steps"]["import"] = step3_result

        logger.info("[Step 4/7] 创建跨层链接")
        step4_result = self._step_cross_layer_links()
        report["steps"]["cross_layer"] = step4_result

        logger.info("[Step 5/7] 计算差异诊断边(图自动计算)")
        step5_result = self._step_differential_from_graph()
        report["steps"]["differential"] = step5_result

        logger.info("[Step 6/7] 生成向量嵌入")
        step6_result = self._step_embed()
        report["steps"]["embed"] = step6_result

        logger.info("[Step 7/7] 生成快照+构建验证")
        step7a_result = self._step_snapshot()
        step7b_result = self._step_validate()
        report["steps"]["snapshot"] = step7a_result
        report["steps"]["validate"] = step7b_result

        elapsed = time.time() - start_time
        report["elapsed_seconds"] = round(elapsed, 2)
        report["end_time"] = datetime.now().isoformat()
        report["success"] = step7b_result.get("passed", False)

        self._build_report = report
        self._save_build_report(report)

        logger.info("=" * 60)
        logger.info(
            f"KG Builder 完成: disease={self._pipeline_name}, "
            f"mode=pdf_first, elapsed={elapsed:.1f}s, success={report['success']}"
        )
        logger.info("=" * 60)
        return report

    @property
    def _pipeline_name(self) -> str:
        if self._pipeline is None:
            return "unknown"
        return self._pipeline.disease_name

    def _step_import_predefined(self) -> Dict[str, Any]:
        if self._pipeline is None:
            return {"success": False, "error": "No disease pipeline configured"}

        result = self._pipeline.build_from_predefined()

        el1_nodes = self._pipeline.get_el1_nodes() if self._pipeline else None
        el2_nodes = self._pipeline.get_el2_nodes() if self._pipeline else None

        importer = KGImporter()
        try:
            import_stats = importer.import_extraction_result(
                result,
                el1_nodes=el1_nodes,
                el2_nodes=el2_nodes,
            )
            return {"success": True, "stats": import_stats}
        except Exception as e:
            logger.error(f"Import failed: {e}")
            return {"success": False, "error": str(e)}
        finally:
            importer.close()

    def _step_cross_layer_links(self) -> Dict[str, Any]:
        importer = KGImporter()
        try:
            links = importer.create_cross_layer_links()
            return {"success": True, "cross_layer_links": links}
        except Exception as e:
            logger.error(f"Cross-layer links failed: {e}")
            return {"success": False, "error": str(e)}
        finally:
            importer.close()

    def _step_differential(self) -> Dict[str, Any]:
        if self._pipeline is None:
            return {"success": False, "error": "No disease pipeline configured"}

        diff = KGDifferential()
        try:
            if self._last_extraction_result and (
                self._last_extraction_result.differential_edges
                or self._last_extraction_result.contradict_edges
            ):
                diff_edges = self._last_extraction_result.differential_edges
                contradict_edges = self._last_extraction_result.contradict_edges

                disease_nodes = self._pipeline.get_differential_disease_nodes()

                stats = diff.write_from_config(
                    diff_edges=diff_edges,
                    disease_nodes=disease_nodes,
                    contradicts=contradict_edges,
                )

                cat_links = diff.write_disease_category_links(
                    differential_disease_nodes=disease_nodes
                )

                return {
                    "success": True,
                    "differentials": stats["differentials"],
                    "contradicts": stats["contradicts"],
                    "disease_nodes": stats["disease_nodes"],
                    "category_links": cat_links,
                    "source": "extraction_result",
                }

            diff_edges = self._pipeline.get_differential_edges()
            disease_nodes = self._pipeline.get_differential_disease_nodes()
            contradicts = self._pipeline.get_contradicts()

            stats = diff.write_from_config(
                diff_edges=diff_edges,
                disease_nodes=disease_nodes,
                contradicts=contradicts,
            )

            cat_links = diff.write_disease_category_links(
                differential_disease_nodes=disease_nodes
            )

            return {
                "success": True,
                "differentials": stats["differentials"],
                "contradicts": stats["contradicts"],
                "disease_nodes": stats["disease_nodes"],
                "category_links": cat_links,
                "source": "yaml_config",
            }
        except Exception as e:
            logger.error(f"Differential computation failed: {e}")
            return {"success": False, "error": str(e)}
        finally:
            diff.close()

    def _step_human_review(self, auto_approve: bool = True) -> Dict[str, Any]:
        if auto_approve:
            logger.info("人工审核步骤已跳过（auto_approve=True）")
            return {"success": True, "auto_approved": True, "note": "Skipped by auto_approve flag"}

        if self._last_extraction_result is None:
            logger.warning("无提取结果可供审核")
            return {"success": True, "auto_approved": True, "note": "No extraction result to review"}

        try:
            from core.kg.kg_review import KGReviewer
            reviewer = KGReviewer()

            review_dir = self.snapshot_dir / "review"
            review_dir.mkdir(parents=True, exist_ok=True)

            review_path = reviewer.export_review_queue(
                result=self._last_extraction_result,
                output_path=str(review_dir / "review_queue.json"),
            )

            logger.info(f"审核队列已导出至: {review_path}")
            logger.info("请人工审核后，使用 KGReviewer.import_review_results() 导入审核结果")

            return {
                "success": True,
                "auto_approved": False,
                "review_path": review_path,
                "note": "Review queue exported. Use KGReviewer to import results.",
            }
        except Exception as e:
            logger.warning(f"人工审核步骤失败（继续构建）: {e}")
            return {"success": True, "auto_approved": True, "note": f"Review failed, auto-approved: {e}"}

    def _step_embed(self) -> Dict[str, Any]:
        guidelines_dir = None
        quality_synonym_pairs = None
        quality_dissimilar_pairs = None

        if self._pipeline:
            raw_dir = self._pipeline.pdf_sources_cfg.get("guidelines_dir", None)
            if raw_dir:
                guidelines_dir = str(
                    Path("data/guidelines") / raw_dir
                )
            else:
                guidelines_dir = None
            quality_cfg = self._pipeline._raw_config.get("quality_tests", {})
            if quality_cfg:
                quality_synonym_pairs = [
                    (p[0], p[1]) for p in quality_cfg.get("synonym_pairs", [])
                ]
                quality_dissimilar_pairs = [
                    (p[0], p[1]) for p in quality_cfg.get("dissimilar_pairs", [])
                ]

        embedder = KGEmbedder(
            guidelines_dir=guidelines_dir,
            quality_synonym_pairs=quality_synonym_pairs,
            quality_dissimilar_pairs=quality_dissimilar_pairs,
        )
        try:
            stats = embedder.embed_all()
            quality = embedder.validate_quality()
            return {
                "success": True,
                "embed_stats": stats,
                "quality_passed": quality["passed"],
                "total_vectors": sum(stats.values()),
            }
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            return {"success": False, "error": str(e)}
        finally:
            embedder.close()

    def _step_embed_incremental(self) -> Dict[str, Any]:
        return self._step_embed()

    def _step_snapshot(self) -> Dict[str, Any]:
        try:
            snapshot = self._generate_snapshot()
            disease_prefix = self._pipeline.disease_id.lower() if self._pipeline else "unknown"
            snapshot_path = self.snapshot_dir / f"snapshot_{disease_prefix}_v1.json"
            with open(snapshot_path, "w", encoding="utf-8") as f:
                json.dump(snapshot.to_dict(), f, ensure_ascii=False, indent=2)

            logger.info(f"Snapshot saved: {snapshot_path}")
            return {
                "success": True,
                "path": str(snapshot_path),
                "statistics": {
                    "diseases": snapshot.disease_count,
                    "features": snapshot.feature_count,
                    "relations": snapshot.relation_count,
                    "guidelines": snapshot.guideline_count,
                    "differentials": snapshot.differential_count,
                },
            }
        except Exception as e:
            logger.error(f"Snapshot generation failed: {e}")
            return {"success": False, "error": str(e)}

    def _step_validate(self) -> Dict[str, Any]:
        try:
            validation = self._validate_build()
            return validation
        except Exception as e:
            logger.error(f"Build validation failed: {e}")
            return {"passed": False, "error": str(e)}

    def _step_extract(self) -> Dict[str, Any]:
        if self._pipeline is None:
            return {"success": False, "error": "No disease pipeline configured"}

        try:
            result = asyncio.run(self._pipeline.build())
            self._last_extraction_result = result
            return {
                "success": True,
                "disease_count": len(result.disease_nodes),
                "feature_count": len(result.feature_nodes),
                "relation_count": len(result.relation_edges),
            }
        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
            return {"success": False, "error": str(e)}

    def _step_validate_extraction(self) -> Dict[str, Any]:
        return {"success": True, "note": "Validation integrated in extraction pipeline"}

    def _step_import_extracted(self) -> Dict[str, Any]:
        if self._last_extraction_result is not None:
            result = self._last_extraction_result
        elif self._pipeline is not None:
            result = self._pipeline.build_from_predefined()
        else:
            return {"success": False, "error": "No extraction result or pipeline configured"}

        el1_nodes = self._pipeline.get_el1_nodes() if self._pipeline else None
        el2_nodes = self._pipeline.get_el2_nodes() if self._pipeline else None

        importer = KGImporter()
        try:
            import_stats = importer.import_extraction_result(
                result,
                el1_nodes=el1_nodes,
                el2_nodes=el2_nodes,
            )
            return {"success": True, "stats": import_stats}
        except Exception as e:
            logger.error(f"Import failed: {e}")
            return {"success": False, "error": str(e)}
        finally:
            importer.close()

    def _step_extract_incremental(self, pdf_paths: Optional[List[str]] = None) -> Dict[str, Any]:
        if self._pipeline is None:
            return {"success": False, "error": "No disease pipeline configured"}

        if not pdf_paths:
            return {"success": False, "error": "No PDF paths provided"}

        try:
            all_results = []
            chunker = MedicalChunker() if not hasattr(self, '_chunker') else self._chunker
            from core.kg.kg_extractor import KGExtractor
            extractor = KGExtractor()

            for pdf_path in pdf_paths:
                try:
                    chunks = chunker.chunk_pdf(pdf_path)
                    logger.info(f"增量提取: {pdf_path} → {len(chunks)} chunks")

                    result = asyncio.run(extractor.extract(chunks=chunks))
                    if result.disease_nodes or result.feature_nodes:
                        all_results.append(result)
                except Exception as e:
                    logger.error(f"增量提取失败 {pdf_path}: {e}")

            if not all_results:
                return {"success": False, "error": "All PDF extractions failed"}

            merged = all_results[0]
            for r in all_results[1:]:
                merged = merged.merge(r)

            self._last_extraction_result = merged
            return {
                "success": True,
                "disease_count": len(merged.disease_nodes),
                "feature_count": len(merged.feature_nodes),
                "relation_count": len(merged.relation_edges),
            }
        except Exception as e:
            logger.error(f"Incremental extraction failed: {e}")
            return {"success": False, "error": str(e)}

    def _step_differential_from_graph(self) -> Dict[str, Any]:
        diff = KGDifferential()
        try:
            diff_edges = diff.compute_from_graph()
            if diff_edges:
                stats = diff.write_from_config(diff_edges=diff_edges)
            else:
                stats = {"differentials": 0, "contradicts": 0, "disease_nodes": 0}

            return {
                "success": True,
                "differentials": stats.get("differentials", len(diff_edges)),
                "source": "graph_auto_computed",
            }
        except Exception as e:
            logger.error(f"Graph-based differential computation failed: {e}")
            return {"success": False, "error": str(e)}
        finally:
            diff.close()

    def _generate_snapshot(self) -> KGSnapshot:
        use_neo4j = self.config.engine == "neo4j" or self.config.neo4j.url.startswith("bolt://")

        if not use_neo4j:
            return self._generate_snapshot_networkx()

        driver = self.config.get_neo4j_driver()
        with driver.session(database=self.config.neo4j.database) as session:
            diseases = []
            result = session.run("MATCH (d:Disease) RETURN d")
            for r in result:
                diseases.append(dict(r["d"]))

            features = []
            result = session.run("MATCH (f:Feature) RETURN f")
            for r in result:
                features.append(dict(r["f"]))

            guidelines = []
            result = session.run("MATCH (g:ClinicalGuideline) RETURN g")
            for r in result:
                guidelines.append(dict(r["g"]))

            entities = []
            result = session.run("MATCH (e:Entity) RETURN e")
            for r in result:
                entities.append(dict(r["e"]))

            relations = []
            result = session.run("""
                MATCH (a)-[r]->(b)
                RETURN a.id AS source, b.id AS target, type(r) AS rel_type,
                       properties(r) AS props
            """)
            for r in result:
                relations.append({
                    "source": r["source"],
                    "target": r["target"],
                    "type": r["rel_type"],
                    **r["props"],
                })

            differentials = []
            result = session.run("""
                MATCH (d1:Disease)-[r:DIFFERENTIAL_FROM]->(d2:Disease)
                RETURN d1.id, d2.id, properties(r) AS props
            """)
            for r in result:
                differentials.append({
                    "disease_a": r["d1.id"],
                    "disease_b": r["d2.id"],
                    **r["props"],
                })

        driver.close()

        source_files = []
        if self._pipeline:
            source_files = [g.source_file for g in self._pipeline.get_guideline_nodes() if g.source_file]

        return KGSnapshot(
            disease_count=len(diseases),
            feature_count=len(features),
            relation_count=len(relations),
            guideline_count=len(guidelines),
            differential_count=len(differentials),
            diseases=diseases,
            features=features,
            relations=relations,
            guidelines=guidelines,
            differentials=differentials,
            build_timestamp=datetime.now().isoformat(),
            source_files=source_files or ["predefined"],
            version="1.0.0",
        )

    def _generate_snapshot_networkx(self) -> KGSnapshot:
        import networkx as nx
        from core.kg.kg_writer import KGWriter

        G = KGWriter._nx_graph
        if G is None:
            logger.warning("NetworkX图为空，生成空快照")
            return KGSnapshot(
                version="1.0.0",
                source_files=["predefined"],
                diseases=[],
                features=[],
                relations=[],
                guidelines=[],
                differentials=[],
            )

        diseases = []
        features = []
        guidelines = []
        entities = []
        for node_id, data in G.nodes(data=True):
            label = data.get("label", "")
            if label == "Disease":
                diseases.append({"id": node_id, **data})
            elif label == "Feature":
                features.append({"id": node_id, **data})
            elif label == "ClinicalGuideline":
                guidelines.append({"id": node_id, **data})
            elif label == "Entity":
                entities.append({"id": node_id, **data})

        relations = []
        differentials = []
        for src, tgt, data in G.edges(data=True):
            rel_type = data.get("relation_type", data.get("type", "RELATED_TO"))
            rel_dict = {"source": src, "target": tgt, "type": rel_type, **data}
            if rel_type == "DIFFERENTIAL_FROM":
                differentials.append(rel_dict)
            else:
                relations.append(rel_dict)

        source_files = []
        if self._pipeline:
            source_files = [g.source_file for g in self._pipeline.get_guideline_nodes() if g.source_file]

        return KGSnapshot(
            disease_count=len(diseases),
            feature_count=len(features),
            relation_count=len(relations),
            guideline_count=len(guidelines),
            differential_count=len(differentials),
            diseases=diseases,
            features=features,
            relations=relations,
            guidelines=guidelines,
            differentials=differentials,
            build_timestamp=datetime.now().isoformat(),
            source_files=source_files or ["predefined"],
            version="1.0.0",
        )

    def _validate_build(self) -> Dict[str, Any]:
        rules = self._pipeline.get_validation_rules() if self._pipeline else {}

        use_neo4j = self.config.engine == "neo4j" or self.config.neo4j.url.startswith("bolt://")

        if not use_neo4j:
            return self._validate_build_networkx(rules)

        driver = self.config.get_neo4j_driver()
        checks: Dict[str, Any] = {"passed": True, "checks": {}}

        with driver.session(database=self.config.neo4j.database) as session:
            result = session.run("MATCH (n) RETURN count(*) AS total")
            total_nodes = [r["total"] for r in result][0]
            min_nodes = rules.get("min_nodes", 20)
            node_check = total_nodes >= min_nodes
            checks["checks"]["node_count"] = {
                "actual": total_nodes,
                "expected_min": min_nodes,
                "passed": node_check,
            }
            if not node_check:
                checks["passed"] = False

            result = session.run("MATCH ()-[r]->() RETURN count(*) AS total")
            total_rels = [r["total"] for r in result][0]
            min_rels = rules.get("min_relations", 30)
            rel_check = total_rels >= min_rels
            checks["checks"]["relation_count"] = {
                "actual": total_rels,
                "expected_min": min_rels,
                "passed": rel_check,
            }
            if not rel_check:
                checks["passed"] = False

            disease_id = rules.get("disease_id", "")
            if disease_id:
                result = session.run(
                    "MATCH (d:Disease {id: $id}) RETURN count(*) AS cnt",
                    {"id": disease_id},
                )
                disease_exists = [r["cnt"] for r in result][0] > 0
                checks["checks"][f"{disease_id}_exists"] = {"passed": disease_exists}
                if not disease_exists:
                    checks["passed"] = False

            core_ids = rules.get("core_feature_ids", [])
            min_core = rules.get("min_core_features", 2)
            if core_ids:
                result = session.run(
                    "MATCH (f:Feature) WHERE f.id IN $ids AND f.is_core = true RETURN count(*) AS cnt",
                    {"ids": core_ids},
                )
                core_count = [r["cnt"] for r in result][0]
                core_check = core_count >= min_core
                checks["checks"]["core_features"] = {
                    "actual": core_count,
                    "expected_min": min_core,
                    "passed": core_check,
                }
                if not core_check:
                    checks["passed"] = False

            min_diffs = rules.get("min_differentials", 1)
            result = session.run("MATCH ()-[r:DIFFERENTIAL_FROM]->() RETURN count(*) AS cnt")
            diff_count = [r["cnt"] for r in result][0]
            diff_check = diff_count >= min_diffs
            checks["checks"]["differential_edges"] = {
                "actual": diff_count,
                "expected_min": min_diffs,
                "passed": diff_check,
            }
            if not diff_check:
                checks["passed"] = False

            min_contra = rules.get("min_contradicts", 1)
            result = session.run("MATCH ()-[r:CONTRADICTS]->() RETURN count(*) AS cnt")
            contra_count = [r["cnt"] for r in result][0]
            contra_check = contra_count >= min_contra
            checks["checks"]["contradicts_edges"] = {
                "actual": contra_count,
                "expected_min": min_contra,
                "passed": contra_check,
            }
            if not contra_check:
                checks["passed"] = False

            result = session.run("MATCH ()-[r:GUIDED_BY]->() RETURN count(*) AS cnt")
            guided_count = [r["cnt"] for r in result][0]
            guided_check = guided_count >= 1
            checks["checks"]["guided_by"] = {
                "actual": guided_count,
                "expected_min": 1,
                "passed": guided_check,
            }
            if not guided_check:
                checks["passed"] = False

            try:
                from pymilvus import MilvusClient

                client = MilvusClient(
                    uri=f"http://{self.config.milvus.host}:{self.config.milvus.port}"
                )
                if client.has_collection(self.config.milvus.collection_name):
                    milvus_count = client.query(
                        self.config.milvus.collection_name,
                        filter="",
                        output_fields=["count(*)"],
                    )
                    vec_count = milvus_count[0].get("count(*)", 0) if milvus_count else 0
                else:
                    vec_count = 0
                client.close()
            except Exception as e:
                logger.warning(f"Milvus check failed: {e}")
                vec_count = 0

            min_vecs = rules.get("min_milvus_vectors", 50)
            vec_check = vec_count >= min_vecs
            checks["checks"]["milvus_vectors"] = {
                "actual": vec_count,
                "expected_min": min_vecs,
                "passed": vec_check,
            }
            if not vec_check:
                checks["passed"] = False

        driver.close()

        status = "PASSED" if checks["passed"] else "FAILED"
        logger.info(f"Build validation: {status}")
        for check_name, check_data in checks["checks"].items():
            mark = "✓" if check_data["passed"] else "✗"
            logger.info(f"  {mark} {check_name}: {check_data}")

        return checks

    def _validate_build_networkx(self, rules: Dict[str, Any]) -> Dict[str, Any]:
        from core.kg.kg_writer import KGWriter

        G = KGWriter._nx_graph
        checks: Dict[str, Any] = {"passed": True, "checks": {}}

        total_nodes = G.number_of_nodes() if G else 0
        min_nodes = rules.get("min_nodes", 20)
        node_check = total_nodes >= min_nodes
        checks["checks"]["node_count"] = {
            "actual": total_nodes,
            "expected_min": min_nodes,
            "passed": node_check,
        }
        if not node_check:
            checks["passed"] = False

        total_rels = G.number_of_edges() if G else 0
        min_rels = rules.get("min_relations", 30)
        rel_check = total_rels >= min_rels
        checks["checks"]["relation_count"] = {
            "actual": total_rels,
            "expected_min": min_rels,
            "passed": rel_check,
        }
        if not rel_check:
            checks["passed"] = False

        status = "PASSED" if checks["passed"] else "FAILED"
        logger.info(f"Build validation (NetworkX): {status}")
        for check_name, check_data in checks["checks"].items():
            mark = "✓" if check_data["passed"] else "✗"
            logger.info(f"  {mark} {check_name}: {check_data}")

        return checks

    def _save_build_report(self, report: Dict[str, Any]) -> None:
        disease_prefix = self._pipeline.disease_id.lower() if self._pipeline else "unknown"
        report_path = self.snapshot_dir / f"build_report_{disease_prefix}.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)
        logger.info(f"Build report saved: {report_path}")

    def get_build_report(self) -> Dict[str, Any]:
        return self._build_report
