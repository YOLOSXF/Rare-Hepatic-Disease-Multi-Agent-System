"""
知识图谱数据类定义

定义知识图谱的核心数据结构，包括：
- EvidenceLevel: EL层级枚举(EL1/EL2/EL3/EL4d/EL4a)
- DiseaseNode: 疾病节点（EL3）
- FeatureNode: 临床特征节点（EL4d/EL4a）
- RelationEdge: 关系边（8种关系类型）
- GuidelineNode: 指南节点
- DifferentialEdge: 差异诊断边
- ExtractionResult: LLM抽取结果
- KGSnapshot: 图谱快照
- KGRetrievalResult: 检索结果（级联管道输出）
- ActivationResult: 激活分类结果

参考：KG_Implementation_Plan.md 3.1节(四层诊断KG) + 3.3节(KGRetrievalResult)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class EvidenceLevel(str, Enum):
    EL1 = "EL1"
    EL2 = "EL2"
    EL3 = "EL3"
    EL4D = "EL4d"
    EL4A = "EL4a"


class FeatureCategory(str, Enum):
    SYMPTOM = "symptom"
    LAB = "lab"
    IMAGING = "imaging"
    GENETIC = "genetic"
    PHYSICAL = "physical"
    HISTORY = "history"
    SPECIAL_TEST = "special_test"


class RelationType(str, Enum):
    IS_A = "is_a"
    HAS_MANIFESTATION = "has_manifestation"
    HAS_DIAGNOSTIC_KEY = "has_diagnostic_key"
    DIFFERENTIAL_FROM = "differential_from"
    CONTRADICTS = "contradicts"
    ASSOCIATED_GENE = "associated_gene"
    GUIDED_BY = "guided_by"
    SYNONYM_OF = "synonym_of"


class Severity(str, Enum):
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"
    CRITICAL = "critical"


@dataclass
class DiseaseNode:
    disease_id: str
    name: str
    layer: EvidenceLevel = EvidenceLevel.EL3
    name_en: Optional[str] = None
    icd10: Optional[str] = None
    omim: Optional[str] = None
    orpha: Optional[str] = None
    prevalence: Optional[str] = None
    inheritance: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[Severity] = None
    category: Optional[str] = None
    source: Optional[str] = None
    source_page: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_neo4j_dict(self) -> Dict[str, Any]:
        result = {
            "disease_id": self.disease_id,
            "name": self.name,
            "layer": self.layer.value,
        }
        if self.name_en:
            result["name_en"] = self.name_en
        if self.icd10:
            result["icd10"] = self.icd10
        if self.omim:
            result["omim"] = self.omim
        if self.orpha:
            result["orpha"] = self.orpha
        if self.prevalence:
            result["prevalence"] = self.prevalence
        if self.inheritance:
            result["inheritance"] = self.inheritance
        if self.description:
            result["description"] = self.description
        if self.severity:
            result["severity"] = self.severity.value
        if self.category:
            result["category"] = self.category
        if self.source:
            result["source"] = self.source
        if self.source_page is not None:
            result["source_page"] = self.source_page
        result.update(self.metadata)
        return result


@dataclass
class FeatureNode:
    feature_id: str
    name: str
    layer: EvidenceLevel = EvidenceLevel.EL4D
    name_en: Optional[str] = None
    category: FeatureCategory = FeatureCategory.SYMPTOM
    hpo_id: Optional[str] = None
    loinc_id: Optional[str] = None
    description: Optional[str] = None
    is_core: bool = False
    specificity: float = 0.5
    sensitivity: float = 0.5
    ic_value: Optional[float] = None
    normal_range: Optional[str] = None
    abnormal_direction: Optional[str] = None
    unit: Optional[str] = None
    source: Optional[str] = None
    source_page: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_neo4j_dict(self) -> Dict[str, Any]:
        result = {
            "feature_id": self.feature_id,
            "name": self.name,
            "layer": self.layer.value,
            "category": self.category.value,
            "is_core": self.is_core,
            "specificity": self.specificity,
            "sensitivity": self.sensitivity,
        }
        if self.name_en:
            result["name_en"] = self.name_en
        if self.hpo_id:
            result["hpo_id"] = self.hpo_id
        if self.loinc_id:
            result["loinc_id"] = self.loinc_id
        if self.description:
            result["description"] = self.description
        if self.ic_value is not None:
            result["ic_value"] = self.ic_value
        if self.normal_range:
            result["normal_range"] = self.normal_range
        if self.abnormal_direction:
            result["abnormal_direction"] = self.abnormal_direction
        if self.unit:
            result["unit"] = self.unit
        if self.source:
            result["source"] = self.source
        if self.source_page is not None:
            result["source_page"] = self.source_page
        result.update(self.metadata)
        return result


@dataclass
class RelationEdge:
    source_id: str
    target_id: str
    relation_type: RelationType
    confidence: float = 1.0
    weight: float = 1.0
    is_core: Optional[bool] = None
    strength: Optional[str] = None
    evidence: Optional[str] = None
    source: Optional[str] = None
    source_page: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_neo4j_dict(self) -> Dict[str, Any]:
        result = {
            "confidence": self.confidence,
            "weight": self.weight,
        }
        if self.is_core is not None:
            result["is_core"] = self.is_core
        if self.strength:
            result["strength"] = self.strength
        if self.evidence:
            result["evidence"] = self.evidence
        if self.source:
            result["source"] = self.source
        if self.source_page is not None:
            result["source_page"] = self.source_page
        result.update(self.metadata)
        return result


@dataclass
class GuidelineNode:
    guideline_id: str
    title: str
    year: Optional[int] = None
    organization: Optional[str] = None
    doi: Optional[str] = None
    description: Optional[str] = None
    source_file: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_neo4j_dict(self) -> Dict[str, Any]:
        result = {
            "guideline_id": self.guideline_id,
            "title": self.title,
        }
        if self.year:
            result["year"] = self.year
        if self.organization:
            result["organization"] = self.organization
        if self.doi:
            result["doi"] = self.doi
        if self.description:
            result["description"] = self.description
        if self.source_file:
            result["source_file"] = self.source_file
        result.update(self.metadata)
        return result


@dataclass
class DifferentialEdge:
    disease_a_id: str
    disease_b_id: str
    distinguishing_features: List[str] = field(default_factory=list)
    overlap_features: List[str] = field(default_factory=list)
    similarity_score: float = 0.0
    difficulty: Optional[str] = None
    evidence: Optional[str] = None
    source: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_neo4j_dict(self) -> Dict[str, Any]:
        result = {
            "distinguishing_features": self.distinguishing_features,
            "overlap_features": self.overlap_features,
            "similarity_score": self.similarity_score,
        }
        if self.difficulty:
            result["difficulty"] = self.difficulty
        if self.evidence:
            result["evidence"] = self.evidence
        if self.source:
            result["source"] = self.source
        result.update(self.metadata)
        return result


@dataclass
class ContradictEdge:
    feature_id: str
    disease_id: str
    contradict_condition: str = ""
    strength: str = "moderate"
    confidence: float = 0.8
    weight: float = 1.5
    evidence: Optional[str] = None
    source: Optional[str] = None
    source_page: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_neo4j_dict(self) -> Dict[str, Any]:
        result = {
            "contradict_condition": self.contradict_condition,
            "strength": self.strength,
            "confidence": self.confidence,
            "weight": self.weight,
        }
        if self.evidence:
            result["evidence"] = self.evidence
        if self.source:
            result["source"] = self.source
        if self.source_page is not None:
            result["source_page"] = self.source_page
        result.update(self.metadata)
        return result


@dataclass
class ExtractionResult:
    disease_nodes: List[DiseaseNode] = field(default_factory=list)
    feature_nodes: List[FeatureNode] = field(default_factory=list)
    relation_edges: List[RelationEdge] = field(default_factory=list)
    guideline_nodes: List[GuidelineNode] = field(default_factory=list)
    differential_edges: List[DifferentialEdge] = field(default_factory=list)
    contradict_edges: List[ContradictEdge] = field(default_factory=list)
    raw_text: Optional[str] = None
    chunk_id: Optional[str] = None
    source_file: Optional[str] = None
    page_number: Optional[int] = None
    extraction_model: Optional[str] = None
    validation_passed: bool = False
    validation_errors: List[str] = field(default_factory=list)

    def merge(self, other: "ExtractionResult") -> "ExtractionResult":
        return ExtractionResult(
            disease_nodes=self.disease_nodes + other.disease_nodes,
            feature_nodes=self.feature_nodes + other.feature_nodes,
            relation_edges=self.relation_edges + other.relation_edges,
            guideline_nodes=self.guideline_nodes + other.guideline_nodes,
            differential_edges=self.differential_edges + other.differential_edges,
            contradict_edges=self.contradict_edges + other.contradict_edges,
            raw_text=self.raw_text or other.raw_text,
            chunk_id=self.chunk_id or other.chunk_id,
            source_file=self.source_file or other.source_file,
            page_number=self.page_number or other.page_number,
            extraction_model=self.extraction_model or other.extraction_model,
            validation_passed=self.validation_passed and other.validation_passed,
            validation_errors=self.validation_errors + other.validation_errors,
        )


@dataclass
class KGSnapshot:
    disease_count: int = 0
    feature_count: int = 0
    relation_count: int = 0
    guideline_count: int = 0
    differential_count: int = 0
    diseases: List[Dict[str, Any]] = field(default_factory=list)
    features: List[Dict[str, Any]] = field(default_factory=list)
    relations: List[Dict[str, Any]] = field(default_factory=list)
    guidelines: List[Dict[str, Any]] = field(default_factory=list)
    differentials: List[Dict[str, Any]] = field(default_factory=list)
    build_timestamp: Optional[str] = None
    source_files: List[str] = field(default_factory=list)
    version: str = "1.0.0"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "build_timestamp": self.build_timestamp,
            "source_files": self.source_files,
            "statistics": {
                "disease_count": self.disease_count,
                "feature_count": self.feature_count,
                "relation_count": self.relation_count,
                "guideline_count": self.guideline_count,
                "differential_count": self.differential_count,
            },
            "diseases": self.diseases,
            "features": self.features,
            "relations": self.relations,
            "guidelines": self.guidelines,
            "differentials": self.differentials,
        }


@dataclass
class CandidateDisease:
    disease_id: str
    name: str
    score: float
    matched_features: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class DiagnosticDifference:
    disease_pair: str
    key_features: List[str] = field(default_factory=list)
    overlap_features: List[str] = field(default_factory=list)
    difficulty: Optional[str] = None


@dataclass
class RelevantEntity:
    name: str
    entity_type: str
    description: Optional[str] = None
    source: Optional[str] = None


@dataclass
class RelevantRelation:
    source: str
    target: str
    relation_type: str
    strength: float = 1.0


@dataclass
class SourceCitation:
    guideline: str
    section: Optional[str] = None
    original_text: Optional[str] = None
    evidence_text: Optional[str] = None


@dataclass
class KGRetrievalResult:
    candidate_diseases: List[CandidateDisease] = field(default_factory=list)
    diagnostic_differences: List[DiagnosticDifference] = field(default_factory=list)
    relevant_entities: List[RelevantEntity] = field(default_factory=list)
    relevant_relations: List[RelevantRelation] = field(default_factory=list)
    source_citations: List[SourceCitation] = field(default_factory=list)
    retrieval_latency_ms: float = 0.0
    degradation_level: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_diseases": [
                {"disease_id": d.disease_id, "name": d.name, "score": d.score, "matched_features": d.matched_features}
                for d in self.candidate_diseases
            ],
            "diagnostic_differences": [
                {"disease_pair": d.disease_pair, "key_features": d.key_features, "overlap_features": d.overlap_features}
                for d in self.diagnostic_differences
            ],
            "relevant_entities": [
                {"name": e.name, "entity_type": e.entity_type, "description": e.description}
                for e in self.relevant_entities
            ],
            "relevant_relations": [
                {"source": r.source, "target": r.target, "relation_type": r.relation_type, "strength": r.strength}
                for r in self.relevant_relations
            ],
            "source_citations": [
                {"guideline": c.guideline, "section": c.section, "original_text": c.original_text, "evidence_text": c.evidence_text}
                for c in self.source_citations
            ],
            "retrieval_latency_ms": self.retrieval_latency_ms,
            "degradation_level": self.degradation_level,
        }


@dataclass
class ActivationResult:
    disease_id: str
    disease_name: str
    activation_score: float
    matched_features: List[Dict[str, Any]] = field(default_factory=list)
    unmatched_features: List[str] = field(default_factory=list)
    evidence_path: List[Dict[str, Any]] = field(default_factory=list)
    source: str = "kg"
