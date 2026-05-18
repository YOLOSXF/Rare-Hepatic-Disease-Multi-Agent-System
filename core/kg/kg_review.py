"""
知识图谱人工审核接口

提供提取结果的导出、审核和修正功能：
1. export_review_queue: 导出审核队列（JSON/CSV格式）
2. import_review_results: 导入审核后的结果
3. apply_corrections: 应用审核修正

使用示例:
    from core.kg.kg_review import KGReviewer

    reviewer = KGReviewer()

    # 导出审核队列
    path = reviewer.export_review_queue(result, "review_queue.json")

    # 人工审核后导入
    reviewed = reviewer.import_review_results("review_queue_reviewed.json")

    # 应用修正
    corrected = reviewer.apply_corrections(original=result, reviewed=reviewed)
"""

import csv
import json
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from core.kg.kg_schema import (
    ContradictEdge, DifferentialEdge, DiseaseNode, ExtractionResult,
    FeatureNode, GuidelineNode, RelationEdge,
)


class KGReviewer:
    def export_review_queue(
        self,
        result: ExtractionResult,
        output_path: str,
        format: str = "json",
    ) -> str:
        review_id = str(uuid.uuid4())[:8]
        items: List[Dict[str, Any]] = []

        for d in result.disease_nodes:
            items.append({
                "type": "disease_node",
                "action": "approve",
                "original": _node_to_dict(d),
                "modified": None,
                "reviewer_note": "",
            })

        for f in result.feature_nodes:
            items.append({
                "type": "feature_node",
                "action": "approve",
                "original": _node_to_dict(f),
                "modified": None,
                "reviewer_note": "",
            })

        for g in result.guideline_nodes:
            items.append({
                "type": "guideline_node",
                "action": "approve",
                "original": _node_to_dict(g),
                "modified": None,
                "reviewer_note": "",
            })

        for r in result.relation_edges:
            items.append({
                "type": "relation_edge",
                "action": "approve",
                "original": _node_to_dict(r),
                "modified": None,
                "reviewer_note": "",
            })

        for d in result.differential_edges:
            items.append({
                "type": "differential_edge",
                "action": "approve",
                "original": _node_to_dict(d),
                "modified": None,
                "reviewer_note": "",
            })

        for c in result.contradict_edges:
            items.append({
                "type": "contradict_edge",
                "action": "approve",
                "original": _node_to_dict(c),
                "modified": None,
                "reviewer_note": "",
            })

        review_queue = {
            "review_id": review_id,
            "created_at": datetime.now().isoformat(),
            "source": "kg_extractor",
            "total_items": len(items),
            "items": items,
        }

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        if format.lower() == "csv":
            csv_path = output.with_suffix(".csv")
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=[
                    "type", "action", "original", "modified", "reviewer_note",
                ])
                writer.writeheader()
                for item in items:
                    writer.writerow({
                        "type": item["type"],
                        "action": item["action"],
                        "original": json.dumps(item["original"], ensure_ascii=False),
                        "modified": json.dumps(item["modified"], ensure_ascii=False) if item["modified"] else "",
                        "reviewer_note": item["reviewer_note"],
                    })
            logger.info(f"Review queue exported (CSV): {csv_path} ({len(items)} items)")
            return str(csv_path)
        else:
            with open(output, "w", encoding="utf-8") as f:
                json.dump(review_queue, f, ensure_ascii=False, indent=2)
            logger.info(f"Review queue exported (JSON): {output} ({len(items)} items)")
            return str(output)

    def import_review_results(self, review_path: str) -> ExtractionResult:
        path = Path(review_path)

        if not path.exists():
            raise FileNotFoundError(f"Review file not found: {review_path}")

        if path.suffix.lower() == ".csv":
            return self._import_csv(review_path)

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        items = data.get("items", [])
        logger.info(f"Importing review results: {len(items)} items from {review_path}")

        return self._build_result_from_items(items)

    def apply_corrections(
        self,
        original: ExtractionResult,
        reviewed: ExtractionResult,
    ) -> ExtractionResult:
        disease_map = {d.disease_id: d for d in original.disease_nodes}
        for d in reviewed.disease_nodes:
            disease_map[d.disease_id] = d

        feature_map = {f.feature_id: f for f in original.feature_nodes}
        for f in reviewed.feature_nodes:
            feature_map[f.feature_id] = f

        guideline_map = {g.guideline_id: g for g in original.guideline_nodes}
        for g in reviewed.guideline_nodes:
            guideline_map[g.guideline_id] = g

        relation_set = set()
        all_relations = list(original.relation_edges)
        for r in all_relations:
            relation_set.add((r.source_id, r.target_id, r.relation_type.value))
        for r in reviewed.relation_edges:
            key = (r.source_id, r.target_id, r.relation_type.value)
            if key not in relation_set:
                all_relations.append(r)
                relation_set.add(key)

        diff_set = set()
        all_diffs = list(original.differential_edges)
        for d in all_diffs:
            diff_set.add((d.disease_a_id, d.disease_b_id))
        for d in reviewed.differential_edges:
            key = (d.disease_a_id, d.disease_b_id)
            if key not in diff_set:
                all_diffs.append(d)
                diff_set.add(key)

        contra_set = set()
        all_contras = list(original.contradict_edges)
        for c in all_contras:
            contra_set.add((c.feature_id, c.disease_id))
        for c in reviewed.contradict_edges:
            key = (c.feature_id, c.disease_id)
            if key not in contra_set:
                all_contras.append(c)
                contra_set.add(key)

        corrected = ExtractionResult(
            disease_nodes=list(disease_map.values()),
            feature_nodes=list(feature_map.values()),
            relation_edges=all_relations,
            guideline_nodes=list(guideline_map.values()),
            differential_edges=all_diffs,
            contradict_edges=all_contras,
            raw_text=original.raw_text,
            chunk_id=original.chunk_id,
            source_file=original.source_file,
            page_number=original.page_number,
            extraction_model=original.extraction_model,
            validation_passed=original.validation_passed,
            validation_errors=original.validation_errors,
        )

        logger.info(
            f"Corrections applied: diseases={len(corrected.disease_nodes)}, "
            f"features={len(corrected.feature_nodes)}, "
            f"relations={len(corrected.relation_edges)}, "
            f"differentials={len(corrected.differential_edges)}, "
            f"contradicts={len(corrected.contradict_edges)}"
        )
        return corrected

    def _import_csv(self, review_path: str) -> ExtractionResult:
        items: List[Dict[str, Any]] = []
        with open(review_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                original = json.loads(row.get("original", "{}")) if row.get("original") else {}
                modified = json.loads(row.get("modified", "{}")) if row.get("modified") else None
                items.append({
                    "type": row.get("type", ""),
                    "action": row.get("action", "approve"),
                    "original": original,
                    "modified": modified,
                    "reviewer_note": row.get("reviewer_note", ""),
                })
        return self._build_result_from_items(items)

    def _build_result_from_items(self, items: List[Dict[str, Any]]) -> ExtractionResult:
        disease_nodes: List[DiseaseNode] = []
        feature_nodes: List[FeatureNode] = []
        guideline_nodes: List[GuidelineNode] = []
        relation_edges: List[RelationEdge] = []
        differential_edges: List[DifferentialEdge] = []
        contradict_edges: List[ContradictEdge] = []

        for item in items:
            action = item.get("action", "approve")
            if action == "reject":
                continue

            data = item.get("modified") or item.get("original", {})
            item_type = item.get("type", "")

            try:
                if item_type == "disease_node":
                    disease_nodes.append(_dict_to_disease_node(data))
                elif item_type == "feature_node":
                    feature_nodes.append(_dict_to_feature_node(data))
                elif item_type == "guideline_node":
                    guideline_nodes.append(_dict_to_guideline_node(data))
                elif item_type == "relation_edge":
                    relation_edges.append(_dict_to_relation_edge(data))
                elif item_type == "differential_edge":
                    differential_edges.append(_dict_to_differential_edge(data))
                elif item_type == "contradict_edge":
                    contradict_edges.append(_dict_to_contradict_edge(data))
            except Exception as e:
                logger.warning(f"Failed to parse review item ({item_type}): {e}")

        return ExtractionResult(
            disease_nodes=disease_nodes,
            feature_nodes=feature_nodes,
            relation_edges=relation_edges,
            guideline_nodes=guideline_nodes,
            differential_edges=differential_edges,
            contradict_edges=contradict_edges,
        )


def _node_to_dict(node: Any) -> Dict[str, Any]:
    if hasattr(node, 'to_neo4j_dict'):
        return node.to_neo4j_dict()
    try:
        return asdict(node)
    except Exception:
        return {"str": str(node)}


def _dict_to_disease_node(data: Dict[str, Any]) -> DiseaseNode:
    return DiseaseNode(
        disease_id=data.get("disease_id", data.get("id", "")),
        name=data.get("name", ""),
        name_en=data.get("name_en", ""),
        icd10=data.get("icd10", ""),
        omim=data.get("omim", ""),
        orpha=data.get("orpha", ""),
        prevalence=data.get("prevalence", ""),
        inheritance=data.get("inheritance", ""),
        description=data.get("description", ""),
        severity=data.get("severity", ""),
        category=data.get("category", ""),
        source=data.get("source"),
        source_page=data.get("source_page"),
    )


def _dict_to_feature_node(data: Dict[str, Any]) -> FeatureNode:
    return FeatureNode(
        feature_id=data.get("feature_id", data.get("id", "")),
        name=data.get("name", ""),
        name_en=data.get("name_en", ""),
        category=data.get("category", "symptom"),
        hpo_id=data.get("hpo_id", ""),
        loinc_id=data.get("loinc_id", ""),
        description=data.get("description", ""),
        is_core=data.get("is_core", False),
        specificity=data.get("specificity", 0.5),
        sensitivity=data.get("sensitivity", 0.5),
        ic_value=data.get("ic_value"),
        normal_range=data.get("normal_range", ""),
        abnormal_direction=data.get("abnormal_direction", ""),
        unit=data.get("unit", ""),
        source=data.get("source"),
        source_page=data.get("source_page"),
    )


def _dict_to_guideline_node(data: Dict[str, Any]) -> GuidelineNode:
    return GuidelineNode(
        guideline_id=data.get("guideline_id", data.get("id", "")),
        title=data.get("title", ""),
        year=data.get("year"),
        organization=data.get("organization", ""),
        doi=data.get("doi", ""),
        description=data.get("description", ""),
        source_file=data.get("source_file"),
    )


def _dict_to_relation_edge(data: Dict[str, Any]) -> RelationEdge:
    from core.kg.kg_schema import RelationType
    rel_type_str = data.get("relation_type", "has_manifestation")
    try:
        rel_type = RelationType(rel_type_str)
    except ValueError:
        rel_type = RelationType.HAS_MANIFESTATION
    return RelationEdge(
        source_id=data.get("source_id", data.get("source", "")),
        target_id=data.get("target_id", data.get("target", "")),
        relation_type=rel_type,
        confidence=data.get("confidence", 1.0),
        weight=data.get("weight", 1.0),
        is_core=data.get("is_core", False),
        strength=data.get("strength", ""),
        evidence=data.get("evidence"),
        source=data.get("source"),
        source_page=data.get("source_page"),
    )


def _dict_to_differential_edge(data: Dict[str, Any]) -> DifferentialEdge:
    distinguishing = data.get("distinguishing_features", [])
    if isinstance(distinguishing, str):
        distinguishing = [f.strip() for f in distinguishing.split(";") if f.strip()]
    overlap = data.get("overlap_features", [])
    if isinstance(overlap, str):
        overlap = [f.strip() for f in overlap.split(";") if f.strip()]
    return DifferentialEdge(
        disease_a_id=data.get("disease_a_id", data.get("disease_a", "")),
        disease_b_id=data.get("disease_b_id", data.get("disease_b", "")),
        distinguishing_features=distinguishing,
        overlap_features=overlap,
        similarity_score=data.get("similarity_score"),
        difficulty=data.get("difficulty", "moderate"),
        evidence=data.get("evidence"),
        source=data.get("source"),
    )


def _dict_to_contradict_edge(data: Dict[str, Any]) -> ContradictEdge:
    return ContradictEdge(
        feature_id=data.get("feature_id", ""),
        disease_id=data.get("disease_id", ""),
        contradict_condition=data.get("contradict_condition", ""),
        strength=data.get("strength", "moderate"),
        confidence=data.get("confidence", 0.8),
        weight=data.get("weight", 1.5),
        evidence=data.get("evidence"),
        source=data.get("source"),
        source_page=data.get("source_page"),
    )
