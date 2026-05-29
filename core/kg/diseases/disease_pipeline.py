"""
通用疾病知识图谱构建管道

职责：
1. 从YAML配置文件加载疾病定义（预置知识、差异诊断、验证规则）
2. 串联PDF分块→LLM提取→验证→去重→快照的完整流程
3. 提供预置知识降级方案（LLM提取失败时使用）
4. 支持插件化扩展，新增疾病只需添加YAML配置文件

使用示例：
    from core.kg.diseases.disease_pipeline import DiseasePipeline
    pipeline = DiseasePipeline("data/disease_configs/wilson_disease.yaml")
    result = await pipeline.build()
"""

import asyncio
import json
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from loguru import logger

from core.kg.kg_cache import KGCache
from core.kg.kg_chunker import MedicalChunker
from core.kg.kg_extractor import KGExtractor
from core.kg.kg_schema import (
    DiseaseNode,
    DifferentialEdge,
    EvidenceLevel,
    ExtractionResult,
    FeatureCategory,
    FeatureNode,
    GuidelineNode,
    KGSnapshot,
    RelationEdge,
    RelationType,
)
from core.kg.kg_validator import KGValidator


class DiseasePipeline:
    """
    通用疾病知识图谱构建管道

    支持两种模式：
    1. YAML配置模式：从YAML文件加载预置知识，适合已有完整知识的疾病
    2. PDF优先模式：仅提供PDF和疾病基本信息，LLM自动提取，适合新疾病快速接入

    使用示例：
        # YAML配置模式
        pipeline = DiseasePipeline("data/disease_configs/wilson_disease.yaml")

        # PDF优先模式
        pipeline = DiseasePipeline.from_pdfs(
            disease_id="PBC",
            disease_name="原发性胆汁性胆管炎",
            pdf_paths=["data/guidelines/pbc/guideline.pdf"],
        )
    """

    def __init__(self, config_path: str, output_dir: Optional[str] = None):
        self.config_path = Path(config_path)
        if not self.config_path.exists():
            raise FileNotFoundError(f"疾病配置文件不存在: {config_path}")

        with open(self.config_path, "r", encoding="utf-8") as f:
            self._raw_config = yaml.safe_load(f)

        self.disease_cfg = self._raw_config["disease"]
        self.guidelines_cfg = self._raw_config.get("guidelines", [])
        self.pdf_sources_cfg = self._raw_config.get("pdf_sources", {})
        self.features_cfg = self._raw_config.get("predefined_features", [])
        self.relations_cfg = self._raw_config.get("predefined_relations", [])
        self.differentials_cfg = self._raw_config.get("differentials", [])
        self.contradicts_cfg = self._raw_config.get("contradicts", [])
        self.validation_cfg = self._raw_config.get("validation", {})
        self.extraction_cfg = self._raw_config.get("extraction", {})

        from core.kg.kg_config import load_domain_config
        domain = load_domain_config()
        disease_el1 = self._raw_config.get("el1_nodes", [])
        disease_el2 = self._raw_config.get("el2_nodes", [])
        merged = domain.merge_with_disease_config(disease_el1, disease_el2)
        self.el1_cfg = merged.el1_nodes
        self.el2_cfg = merged.el2_nodes

        if output_dir is None:
            project_root = Path(__file__).parent.parent.parent.parent
            output_dir = str(project_root / "data" / "kg_output")
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.disease_id = self.disease_cfg["disease_id"]
        self.disease_name = self.disease_cfg["name"]
        self.disease_name_en = self.disease_cfg["name_en"]

        self._cache = KGCache()
        self._chunker = MedicalChunker()
        self._extractor = KGExtractor(
            max_gleaning=self.extraction_cfg.get("max_gleaning", 1),
            max_concurrent=self.extraction_cfg.get("max_concurrent", 4),
        )
        self._validator = KGValidator()

    @classmethod
    def from_pdfs(
        cls,
        disease_id: str,
        disease_name: str,
        pdf_paths: List[str],
        disease_name_en: str = "",
        icd10: str = "",
        category: str = "",
        description: str = "",
        output_dir: Optional[str] = None,
    ) -> "DiseasePipeline":
        """
        PDF优先模式：仅提供PDF和疾病基本信息，LLM自动提取知识图谱。

        无需预先编写YAML配置文件，适合快速接入新疾病。
        预置特征、关系、差异诊断等全部由LLM从PDF中提取。
        """
        minimal_config = {
            "disease": {
                "disease_id": disease_id,
                "name": disease_name,
                "name_en": disease_name_en,
                "icd10": icd10,
                "category": category,
                "description": description or f"{disease_name}（{disease_name_en}）",
            },
            "guidelines": [],
            "pdf_sources": {
                "guidelines_dir": "",
                "files": [],
            },
            "predefined_features": [],
            "predefined_relations": [],
            "differentials": [],
            "contradicts": [],
            "validation": {
                "min_nodes": 5,
                "min_relations": 3,
                "min_core_features": 1,
                "min_differentials": 0,
                "min_contradicts": 0,
                "min_milvus_vectors": 10,
            },
            "extraction": {
                "max_gleaning": 1,
                "max_concurrent": 4,
            },
        }

        pipeline = cls.__new__(cls)
        pipeline.config_path = None
        pipeline._raw_config = minimal_config
        pipeline.disease_cfg = minimal_config["disease"]
        pipeline.guidelines_cfg = minimal_config["guidelines"]
        pipeline.pdf_sources_cfg = minimal_config["pdf_sources"]
        pipeline.el1_cfg = minimal_config["el1_nodes"]
        pipeline.el2_cfg = minimal_config["el2_nodes"]
        pipeline.features_cfg = minimal_config["predefined_features"]
        pipeline.relations_cfg = minimal_config["predefined_relations"]
        pipeline.differentials_cfg = minimal_config["differentials"]
        pipeline.contradicts_cfg = minimal_config["contradicts"]
        pipeline.validation_cfg = minimal_config["validation"]
        pipeline.extraction_cfg = minimal_config["extraction"]

        if output_dir is None:
            project_root = Path(__file__).parent.parent.parent.parent
            output_dir = str(project_root / "data" / "kg_output")
        pipeline.output_dir = Path(output_dir)
        pipeline.output_dir.mkdir(parents=True, exist_ok=True)

        pipeline.disease_id = disease_id
        pipeline.disease_name = disease_name
        pipeline.disease_name_en = disease_name_en

        pipeline._cache = KGCache()
        pipeline._chunker = MedicalChunker()
        pipeline._extractor = KGExtractor(
            max_gleaning=1,
            max_concurrent=4,
        )
        pipeline._validator = KGValidator()

        pipeline._pdf_paths = [Path(p) for p in pdf_paths]

        logger.info(
            f"PDF优先模式: {disease_name} ({disease_id}), "
            f"{len(pdf_paths)} 个PDF文件"
        )
        return pipeline

    def get_disease_node(self) -> DiseaseNode:
        return DiseaseNode(
            disease_id=self.disease_id,
            name=self.disease_name,
            name_en=self.disease_name_en,
            icd10=self.disease_cfg.get("icd10", ""),
            omim=self.disease_cfg.get("omim", ""),
            orpha=self.disease_cfg.get("orpha", ""),
            prevalence=self.disease_cfg.get("prevalence", ""),
            inheritance=self.disease_cfg.get("inheritance", ""),
            description=self.disease_cfg.get("description", ""),
            category=self.disease_cfg.get("category", ""),
            layer=EvidenceLevel.EL3,
        )

    def get_guideline_nodes(self) -> List[GuidelineNode]:
        nodes = []
        for g in self.guidelines_cfg:
            nodes.append(
                GuidelineNode(
                    guideline_id=g["guideline_id"],
                    title=g.get("title", ""),
                    year=g.get("year", 0),
                    organization=g.get("organization", ""),
                    doi=g.get("doi", ""),
                    description=g.get("description", ""),
                    source_file=g.get("source_file", ""),
                )
            )
        return nodes

    def get_el1_nodes(self) -> List[Dict[str, str]]:
        return [
            {"id": n["id"], "name": n["name"], "name_en": n.get("name_en", "")}
            for n in self.el1_cfg
        ]

    def get_el2_nodes(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": n["id"],
                "name": n["name"],
                "name_en": n.get("name_en", ""),
                "parent": n.get("parent", ""),
            }
            for n in self.el2_cfg
        ]

    def get_predefined_features(self) -> List[FeatureNode]:
        features = []
        for f in self.features_cfg:
            layer = EvidenceLevel.EL4D
            if f.get("layer") == "EL4a":
                layer = EvidenceLevel.EL4A

            category_str = f.get("category", "symptom")
            category = FeatureCategory.SYMPTOM
            for cat in FeatureCategory:
                if cat.value == category_str:
                    category = cat
                    break

            features.append(
                FeatureNode(
                    feature_id=f["feature_id"],
                    name=f["name"],
                    name_en=f.get("name_en", ""),
                    category=category,
                    is_core=f.get("is_core", False),
                    specificity=f.get("specificity", 0.5),
                    sensitivity=f.get("sensitivity", 0.5),
                    hpo_id=f.get("hpo_id", ""),
                    description=f.get("description", ""),
                    abnormal_direction=f.get("abnormal_direction", ""),
                    unit=f.get("unit", ""),
                    normal_range=f.get("normal_range", ""),
                    layer=layer,
                )
            )
        return features

    def get_predefined_relations(self) -> List[RelationEdge]:
        relations = []
        for r in self.relations_cfg:
            rel_type = RelationType.HAS_MANIFESTATION
            for rt in RelationType:
                if rt.value == r["type"]:
                    rel_type = rt
                    break

            relations.append(
                RelationEdge(
                    source_id=r["source"],
                    target_id=r["target"],
                    relation_type=rel_type,
                    confidence=r.get("confidence", 0.5),
                    weight=r.get("weight", 1.0),
                    is_core=r.get("is_core", False),
                    evidence=r.get("evidence", ""),
                )
            )
        return relations

    def get_differential_edges(self) -> List[DifferentialEdge]:
        edges = []
        for d in self.differentials_cfg:
            edges.append(
                DifferentialEdge(
                    disease_a_id=self.disease_id,
                    disease_b_id=d["disease_b_id"],
                    distinguishing_features=d.get("distinguishing_features", []),
                    overlap_features=d.get("overlap_features", []),
                    difficulty=d.get("difficulty", "moderate"),
                    evidence=d.get("evidence", ""),
                )
            )
        return edges

    def get_differential_disease_nodes(self) -> List[DiseaseNode]:
        nodes = []
        for d in self.differentials_cfg:
            nodes.append(
                DiseaseNode(
                    disease_id=d["disease_b_id"],
                    name=d["disease_b_name"],
                    name_en=d.get("disease_b_name_en", ""),
                    icd10=d.get("disease_b_icd10", ""),
                    description=d.get("disease_b_description", ""),
                    category=d.get("disease_b_category", ""),
                    layer=EvidenceLevel.EL3,
                )
            )
        return nodes

    def get_contradicts(self) -> List[Dict[str, Any]]:
        return self.contradicts_cfg

    def get_synonyms(self) -> List[str]:
        return self.disease_cfg.get("synonyms", [])

    def find_pdfs(self) -> List[Path]:
        if hasattr(self, "_pdf_paths") and self._pdf_paths:
            existing = [p for p in self._pdf_paths if p.exists()]
            if existing:
                logger.info(f"PDF优先模式: 找到 {len(existing)} 个PDF文件")
                return existing

        project_root = Path(__file__).parent.parent.parent.parent
        guidelines_dir = self.pdf_sources_cfg.get("guidelines_dir", "")
        search_dir = project_root / "data" / "guidelines" / guidelines_dir

        if not search_dir.exists():
            logger.warning(f"指南目录不存在: {search_dir}")
            return []

        pdf_files = list(search_dir.glob("*.pdf"))
        logger.info(f"在 {search_dir} 中找到 {len(pdf_files)} 个PDF文件")
        return pdf_files

    def _match_pdf_source(self, pdf_path: Path) -> Optional[str]:
        filename = pdf_path.stem
        for file_cfg in self.pdf_sources_cfg.get("files", []):
            for pattern in file_cfg.get("name_patterns", []):
                if pattern in filename:
                    return file_cfg["source_name"]
        return None

    def build_from_predefined(self) -> ExtractionResult:
        disease_node = self.get_disease_node()
        features = self.get_predefined_features()
        relations = self.get_predefined_relations()
        guidelines = self.get_guideline_nodes()

        logger.info(
            f"从预置配置构建 {self.disease_name} KG: "
            f"{len(features)} 特征, {len(relations)} 关系, {len(guidelines)} 指南"
        )

        return ExtractionResult(
            disease_nodes=[disease_node],
            feature_nodes=features,
            relation_edges=relations,
            guideline_nodes=guidelines,
            source_file="predefined",
        )

    async def build(self) -> ExtractionResult:
        predefined = self.build_from_predefined()

        pdf_files = self.find_pdfs()
        if not pdf_files:
            logger.warning(f"未找到 {self.disease_name} 的PDF指南，使用预置知识")
            return predefined

        all_results = []
        for pdf_path in pdf_files:
            source_name = self._match_pdf_source(pdf_path)
            if source_name is None:
                logger.warning(f"无法匹配PDF来源: {pdf_path.name}")
                source_name = pdf_path.stem

            try:
                chunks = self._chunker.chunk_pdf(str(pdf_path))
                logger.info(f"PDF {pdf_path.name} 分为 {len(chunks)} 个chunk")

                result = await self._extractor.extract(
                    chunks=chunks
                )
                if result.disease_nodes or result.feature_nodes:
                    all_results.append(result)
                    logger.info(
                        f"PDF {source_name} 提取: "
                        f"{len(result.disease_nodes)} 疾病, {len(result.feature_nodes)} 特征"
                    )
            except Exception as e:
                logger.error(f"PDF {pdf_path.name} 提取失败: {e}")

        if not all_results:
            logger.warning(f"所有PDF提取失败，使用预置知识")
            return predefined

        merged = self._merge_results(predefined, all_results)
        validated = self._validate_result(merged)
        deduplicated = self._deduplicate(validated)
        final = self._assign_evidence_levels(deduplicated)

        self._save_outputs(final)
        return final

    def _merge_results(
        self, predefined: ExtractionResult, pdf_results: List[ExtractionResult]
    ) -> ExtractionResult:
        all_diseases = list(predefined.disease_nodes)
        all_features = list(predefined.feature_nodes)
        all_relations = list(predefined.relation_edges)
        all_guidelines = list(predefined.guideline_nodes)
        all_differentials = list(predefined.differential_edges)
        all_contradicts = list(predefined.contradict_edges)

        seen_disease_ids = {d.disease_id for d in all_diseases}
        seen_feature_ids = {f.feature_id for f in all_features}
        seen_relation_keys = {
            (r.source_id, r.target_id, r.relation_type.value)
            for r in all_relations
        }
        seen_diff_keys = {(d.disease_a_id, d.disease_b_id) for d in all_differentials}
        seen_contra_keys = {(c.feature_id, c.disease_id) for c in all_contradicts}

        for result in pdf_results:
            for d in result.disease_nodes:
                if d.disease_id not in seen_disease_ids:
                    all_diseases.append(d)
                    seen_disease_ids.add(d.disease_id)

            for f in result.feature_nodes:
                if f.feature_id not in seen_feature_ids:
                    all_features.append(f)
                    seen_feature_ids.add(f.feature_id)

            for r in result.relation_edges:
                key = (r.source_id, r.target_id, r.relation_type.value)
                if key not in seen_relation_keys:
                    all_relations.append(r)
                    seen_relation_keys.add(key)

            for g in result.guideline_nodes:
                all_guidelines.append(g)

            for d in result.differential_edges:
                key = (d.disease_a_id, d.disease_b_id)
                if key not in seen_diff_keys:
                    all_differentials.append(d)
                    seen_diff_keys.add(key)

            for c in result.contradict_edges:
                key = (c.feature_id, c.disease_id)
                if key not in seen_contra_keys:
                    all_contradicts.append(c)
                    seen_contra_keys.add(key)

        return ExtractionResult(
            disease_nodes=all_diseases,
            feature_nodes=all_features,
            relation_edges=all_relations,
            guideline_nodes=all_guidelines,
            differential_edges=all_differentials,
            contradict_edges=all_contradicts,
            source_file="merged",
        )

    def _validate_result(self, result: ExtractionResult) -> ExtractionResult:
        try:
            audit = self._validator.validate(result)
            logger.info(
                f"验证完成: {audit.summary.get('high_confidence', 0)} high, "
                f"{audit.summary.get('medium_confidence', 0)} medium, "
                f"{audit.summary.get('low_confidence', 0)} low"
            )
        except Exception as e:
            logger.warning(f"验证失败，跳过: {e}")
        return result

    def _deduplicate(self, result: ExtractionResult) -> ExtractionResult:
        seen_features = {}
        for f in result.feature_nodes:
            key = f.name.upper().strip()
            if key not in seen_features:
                seen_features[key] = f
            else:
                existing = seen_features[key]
                if f.is_core and not existing.is_core:
                    seen_features[key] = f
                elif f.specificity > existing.specificity:
                    seen_features[key] = f

        seen_relations = {}
        for r in result.relation_edges:
            key = (r.source_id, r.target_id, r.relation_type.value)
            if key not in seen_relations:
                seen_relations[key] = r
            else:
                existing = seen_relations[key]
                if r.confidence > existing.confidence:
                    seen_relations[key] = r

        seen_diffs = {}
        for d in result.differential_edges:
            key = (d.disease_a_id, d.disease_b_id)
            if key not in seen_diffs:
                seen_diffs[key] = d

        seen_contras = {}
        for c in result.contradict_edges:
            key = (c.feature_id, c.disease_id)
            if key not in seen_contras:
                seen_contras[key] = c

        return ExtractionResult(
            disease_nodes=result.disease_nodes,
            feature_nodes=list(seen_features.values()),
            relation_edges=list(seen_relations.values()),
            guideline_nodes=result.guideline_nodes,
            differential_edges=list(seen_diffs.values()),
            contradict_edges=list(seen_contras.values()),
            source_file=result.source_file,
        )

    def _assign_evidence_levels(self, result: ExtractionResult) -> ExtractionResult:
        for f in result.feature_nodes:
            if f.layer == EvidenceLevel.EL4D or f.layer == EvidenceLevel.EL4A:
                continue
            if f.is_core:
                f.layer = EvidenceLevel.EL4D
            else:
                f.layer = EvidenceLevel.EL4A

        for d in result.disease_nodes:
            if d.layer != EvidenceLevel.EL3:
                d.layer = EvidenceLevel.EL3

        return result

    def _save_outputs(self, result: ExtractionResult) -> None:
        snapshot = KGSnapshot(
            version="1.0.0",
            source_files=[g.source_file for g in result.guideline_nodes if g.source_file]
            or ["predefined"],
            diseases=[d.to_dict() for d in result.disease_nodes],
            features=[f.to_dict() for f in result.feature_nodes],
            relations=[r.to_dict() for r in result.relation_edges],
            guidelines=[g.to_dict() for g in result.guideline_nodes],
            differentials=[],
        )

        disease_prefix = self.disease_id.lower()
        snapshot_path = self.output_dir / f"{disease_prefix}_verified.json"
        with open(snapshot_path, "w", encoding="utf-8") as f:
            json.dump(snapshot.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info(f"快照已保存: {snapshot_path}")

        try:
            audit = self._validator.validate(result)
            audit_path = self.output_dir / f"{disease_prefix}_audit_report.json"
            self._validator.export_audit_report(audit, str(audit_path))
            logger.info(f"审核报告已保存: {audit_path}")
        except Exception as e:
            logger.warning(f"审核报告生成失败: {e}")

    def get_validation_rules(self) -> Dict[str, Any]:
        return {
            "min_nodes": self.validation_cfg.get("min_nodes", 20),
            "min_relations": self.validation_cfg.get("min_relations", 30),
            "core_feature_ids": self.validation_cfg.get("core_feature_ids", []),
            "min_core_features": self.validation_cfg.get("min_core_features", 2),
            "min_differentials": self.validation_cfg.get("min_differentials", 1),
            "min_contradicts": self.validation_cfg.get("min_contradicts", 1),
            "min_milvus_vectors": self.validation_cfg.get("min_milvus_vectors", 50),
            "disease_id": self.disease_id,
        }
