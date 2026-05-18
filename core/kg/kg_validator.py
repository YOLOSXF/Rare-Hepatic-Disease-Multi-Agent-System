"""
阈值验证+人工审核辅助

职责：
1. 数值型阈值自动标记confidence(high/medium/low)
2. 生成审核清单供专家审核
3. 审核结果记录与导出
4. YAML交叉参考差异报告

使用示例：
    from core.kg.kg_validator import KGValidator
    validator = KGValidator()
    report = validator.validate(extraction_result)
    validator.export_audit_report(report, "audit_report.json")
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from core.kg.kg_schema import (
    DiseaseNode, FeatureNode, RelationEdge, ExtractionResult,
    RelationType,
)


@dataclass
class AuditEntry:
    entity_id: str
    entity_name: str
    entity_type: str
    field: str
    value: str
    confidence: str
    source: Optional[str] = None
    source_page: Optional[int] = None
    guideline_reference: Optional[str] = None
    audit_status: str = "pending"
    auditor_note: Optional[str] = None
    corrected_value: Optional[str] = None


@dataclass
class AuditReport:
    total_entries: int = 0
    high_confidence: int = 0
    medium_confidence: int = 0
    low_confidence: int = 0
    entries: List[AuditEntry] = field(default_factory=list)
    yaml_differences: List[Dict[str, Any]] = field(default_factory=list)
    validation_errors: List[str] = field(default_factory=list)
    timestamp: str = ""
    version: str = "1.0.0"


NUMERIC_PATTERN = re.compile(
    r'[<>≤≥＝=]\s*[\d.]+\s*(g/L|μg/L|ng/mL|mg/dL|U/L|μmol/L|mmol/L|%|μg/dL|μg/24h)?'
)

THRESHOLD_KEYWORDS = [
    "铜蓝蛋白", "ceruloplasmin", "尿铜", "urinary copper", "24小时尿铜",
    "转氨酶", "ALT", "AST", "ALP", "GGT", "胆红素", "bilirubin",
    "铁蛋白", "ferritin", "转铁蛋白饱和度", "transferrin saturation",
    "凝血", "INR", "白蛋白", "albumin", "血小板", "platelet",
    "游离铜", "free copper", "青霉胺", "penicillamine", "曲恩汀", "trientine",
]


class KGValidator:
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.known_thresholds = self._load_known_thresholds()

    def _load_known_thresholds(self) -> Dict[str, Any]:
        return {
            "ceruloplasmin_low": {"value": 0.20, "unit": "g/L", "source": "EASL-ERN 2025"},
            "urinary_copper_24h": {"value": 100, "unit": "μg/24h", "source": "EASL-ERN 2025"},
            "free_copper": {"value": 20, "unit": "μg/dL", "source": "EASL-ERN 2025"},
            "alt_elevated": {"value": 40, "unit": "U/L", "source": "通用标准"},
        }

    def validate(self, extraction_result: ExtractionResult) -> AuditReport:
        report = AuditReport(
            timestamp=datetime.now().isoformat(),
        )

        for disease in extraction_result.disease_nodes:
            self._validate_disease(disease, report)

        for feature in extraction_result.feature_nodes:
            self._validate_feature(feature, report)

        for edge in extraction_result.relation_edges:
            self._validate_relation(edge, report)

        report.total_entries = len(report.entries)
        report.high_confidence = sum(1 for e in report.entries if e.confidence == "high")
        report.medium_confidence = sum(1 for e in report.entries if e.confidence == "medium")
        report.low_confidence = sum(1 for e in report.entries if e.confidence == "low")
        report.validation_errors = extraction_result.validation_errors

        logger.info(
            f"Validation complete: {report.total_entries} entries, "
            f"high={report.high_confidence}, medium={report.medium_confidence}, "
            f"low={report.low_confidence}"
        )
        return report

    def _validate_disease(self, disease: DiseaseNode, report: AuditReport) -> None:
        confidence = "high"
        if not disease.icd10 and not disease.omim and not disease.orpha:
            confidence = "medium"
        if not disease.description:
            confidence = "low"

        report.entries.append(AuditEntry(
            entity_id=disease.disease_id,
            entity_name=disease.name,
            entity_type="Disease",
            field="disease_node",
            value=f"ICD10={disease.icd10}, OMIM={disease.omim}, ORPHA={disease.orpha}",
            confidence=confidence,
            source=disease.source,
            source_page=disease.source_page,
        ))

    def _validate_feature(self, feature: FeatureNode, report: AuditReport) -> None:
        desc = feature.description or ""
        has_numeric_threshold = bool(NUMERIC_PATTERN.search(desc))
        has_threshold_keyword = any(kw in desc.lower() for kw in THRESHOLD_KEYWORDS)

        if has_numeric_threshold and has_threshold_keyword:
            confidence = "high"
            if self._check_threshold_conflict(feature):
                confidence = "medium"
        elif has_threshold_keyword and not has_numeric_threshold:
            confidence = "medium"
        else:
            confidence = "low"

        report.entries.append(AuditEntry(
            entity_id=feature.feature_id,
            entity_name=feature.name,
            entity_type="Feature",
            field="feature_node",
            value=desc[:200],
            confidence=confidence,
            source=feature.source,
            source_page=feature.source_page,
            guideline_reference=feature.hpo_id or feature.loinc_id,
        ))

    def _validate_relation(self, edge: RelationEdge, report: AuditReport) -> None:
        confidence = "high" if edge.confidence >= 0.8 else "medium" if edge.confidence >= 0.5 else "low"

        if edge.relation_type == RelationType.CONTRADICTS and not edge.evidence:
            confidence = "low"

        report.entries.append(AuditEntry(
            entity_id=f"{edge.source_id}->{edge.target_id}",
            entity_name=f"{edge.source_id} → {edge.target_id}",
            entity_type="Relation",
            field=edge.relation_type.value,
            value=edge.evidence or "",
            confidence=confidence,
            source=edge.source,
            source_page=edge.source_page,
        ))

    def _check_threshold_conflict(self, feature: FeatureNode) -> bool:
        desc = feature.description or ""
        desc_lower = desc.lower()

        for key, threshold_info in self.known_thresholds.items():
            if any(kw in desc_lower for kw in key.split("_")):
                matches = re.findall(r'[\d.]+', desc)
                for match in matches:
                    try:
                        val = float(match)
                        expected = threshold_info["value"]
                        if abs(val - expected) / max(expected, 0.001) > 0.5:
                            return True
                    except ValueError:
                        continue
        return False

    def cross_reference_yaml(self, extraction_result: ExtractionResult) -> List[Dict[str, Any]]:
        differences: List[Dict[str, Any]] = []
        yaml_path = Path(__file__).parent.parent.parent / "rules" / "rare_diseases.yaml"

        if not yaml_path.exists():
            logger.warning(f"YAML rules file not found: {yaml_path}")
            return differences

        try:
            import yaml
            with open(yaml_path, "r", encoding="utf-8") as f:
                yaml_data = yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Failed to load YAML: {e}")
            return differences

        for disease_key, disease_data in yaml_data.items():
            if not isinstance(disease_data, dict):
                continue
            disease_name = disease_data.get("name", disease_key)

            matching_diseases = [
                d for d in extraction_result.disease_nodes
                if disease_name in d.name or d.name in disease_name
            ]

            if not matching_diseases:
                continue

            for rule in disease_data.get("core_rules", []) + disease_data.get("supporting_rules", []):
                rule_field = rule.get("field", "")
                rule_value = rule.get("value")
                rule_note = rule.get("note", "")

                for feature in extraction_result.feature_nodes:
                    if rule_field.replace("labs.", "").replace("symptoms.", "").upper() in feature.name.upper():
                        desc = feature.description or ""
                        if rule_value is not None and str(rule_value) not in desc:
                            differences.append({
                                "type": "threshold_mismatch",
                                "yaml_field": rule_field,
                                "yaml_value": rule_value,
                                "kg_feature": feature.name,
                                "kg_description": desc[:200],
                                "guideline_source": "指南PDF(权威)",
                                "yaml_note": rule_note,
                            })

        logger.info(f"YAML cross-reference: {len(differences)} differences found")
        return differences

    def export_audit_report(self, report: AuditReport, output_path: str) -> None:
        output = {
            "version": report.version,
            "timestamp": report.timestamp,
            "summary": {
                "total_entries": report.total_entries,
                "high_confidence": report.high_confidence,
                "medium_confidence": report.medium_confidence,
                "low_confidence": report.low_confidence,
            },
            "entries": [
                {
                    "entity_id": e.entity_id,
                    "entity_name": e.entity_name,
                    "entity_type": e.entity_type,
                    "field": e.field,
                    "value": e.value,
                    "confidence": e.confidence,
                    "source": e.source,
                    "source_page": e.source_page,
                    "guideline_reference": e.guideline_reference,
                    "audit_status": e.audit_status,
                    "auditor_note": e.auditor_note,
                    "corrected_value": e.corrected_value,
                }
                for e in report.entries
            ],
            "yaml_differences": report.yaml_differences,
            "validation_errors": report.validation_errors,
        }

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        logger.info(f"Audit report exported to {output_path}")

    def get_high_confidence_entries(self, report: AuditReport) -> List[AuditEntry]:
        return [e for e in report.entries if e.confidence == "high"]
