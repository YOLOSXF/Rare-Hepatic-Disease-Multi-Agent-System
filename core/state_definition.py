"""
LangGraph 状态定义 (v2.0 - 对抗推理架构)
定义多智能体协作的状态空间，支持辩论、证伪、HITL 等对抗推理机制
"""

from typing import Dict, List, Optional, Any, Annotated, Union
from typing_extensions import TypedDict
import operator


class PatientData(TypedDict, total=False):
    """患者数据结构"""
    patient_id: str
    age: Optional[int]
    gender: Optional[str]
    chief_complaint: str
    bmi: Optional[float]
    history: Dict[str, Any]
    symptoms: Dict[str, bool]
    labs: Dict[str, Any]
    ultrasound: Dict[str, Any]
    ct: Dict[str, Any]
    mri: Dict[str, Any]
    eye_exam: Dict[str, Any]


class Question(TypedDict, total=False):
    """追问问题"""
    field: str
    question: str
    rationale: str
    priority: str  # critical/high/medium/low
    related_disease: Optional[str]
    recommended_test: Optional[str]


class AgentResponse(TypedDict, total=False):
    """Agent 响应"""
    success: bool
    data: Dict[str, Any]
    error: Optional[str]
    questions: List[Question]
    findings: List[str]
    recommendations: List[str]


class DataAssessmentResult(TypedDict, total=False):
    """数据完整性评估结果（用于状态传递）"""
    score: float
    level: str
    can_triage: bool
    missing_critical: List[str]
    missing_recommended: List[str]
    recommended_actions: List[str]


class TriageResult(TypedDict, total=False):
    """分诊结果"""
    path: str  # common/rare/uncertain/insufficient_data
    diagnosis: Optional[str]
    confidence: float
    confidence_level: str
    is_rare_disease_alert: bool
    urgency: str
    recommended_tests: List[str]


class DiagnosticHypothesis(TypedDict, total=False):
    """诊断假设"""
    disease: str
    confidence: float
    supporting_evidence: List[str]
    opposing_evidence: List[str]
    source: str
    guidelines: List[str]


class ReflectionResult(TypedDict, total=False):
    """反思结果"""
    revised_hypotheses: List[DiagnosticHypothesis]
    confidence_score: float
    reflection_log: List[str]
    contradictions: List[str]


class DebateMessage(TypedDict, total=False):
    """辩论消息"""
    message_type: str  # propose/cfp/reject/accept/inform/query/agreement
    sender: str
    content: str
    evidence: List[str]


class DebateState(TypedDict, total=False):
    """辩论状态"""
    round_number: int
    messages: List[DebateMessage]
    consensus_points: List[str]
    disagreements: List[str]
    all_perspectives: List[Dict]


class FalsificationEntry(TypedDict, total=False):
    """证伪条目"""
    hypothesis: str
    falsified: bool
    contradiction_score: float
    contradicting_evidence: List[str]
    supporting_evidence: List[str]
    recommendation: str


class GuidelineCheckEntry(TypedDict, total=False):
    """指南校验条目"""
    diagnosis: str
    compliant: bool
    missing_criteria: List[str]
    met_criteria: List[str]
    recommendation: str


# ==================== 报告类型定义 ====================

class ReportBase(TypedDict, total=False):
    """报告公共字段（所有报告类型共享）"""
    report_type: str
    report_version: str
    status: str
    patient_id: str
    path: str
    diagnosis: Any
    confidence: float
    confidence_level: str
    is_rare_disease_alert: bool
    urgency: str
    triage: Dict[str, Any]
    data_completeness_score: float


class CommonDiagnosisReport(ReportBase):
    """常见病确诊报告（L5a）"""
    follow_up_plan: Optional[str]
    referral_recommendation: Optional[str]
    recommended_tests: List[str]
    matched_diseases: List[Any]
    clinical_reasoning: Optional[str]
    message: Optional[str]


class TriageRecommendationReport(ReportBase):
    """补检建议报告（L5b）"""
    uncertainty_reason: Optional[str]
    recommended_tests: List[str]
    missing_critical: List[str]
    missing_recommended: List[str]
    clinical_analysis: Optional[str]
    message: Optional[str]


class MDTFinalReport(ReportBase):
    """MDT 终局诊断报告（L5c）"""
    differential_diagnosis: List[Any]
    referral: Dict[str, Any]
    debate_process: Optional[Dict]
    falsification_log: List[Any]
    kg_retrieval_result: Optional[Dict[str, Any]]
    memory_context: Optional[Dict]
    guideline_check: Optional[Any]
    hitl_questions: List[Any]
    hitl_status: str
    excluded_hypotheses: List[str]
    clinical_summary: Optional[str]


# 联合类型：三种报告类型的并集
FinalReport = Union[CommonDiagnosisReport, TriageRecommendationReport, MDTFinalReport]


# ==================== 状态更新函数 ====================

def merge_patient_data(
    left: PatientData,
    right: Dict[str, Any]
) -> PatientData:
    """合并患者数据"""
    if not left:
        left = {}
    if not right:
        return left
        
    merged = dict(left)
    
    for key, value in right.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key].update(value)
        else:
            merged[key] = value
    
    return merged


# ==================== LangGraph State v2.0 ====================

class DiagnosticState(TypedDict):
    """
    诊断状态（LangGraph State v2.0 - 对抗推理架构）
    
    贯穿整个诊断流程的状态空间，支持：
    - 五层分层架构
    - MDT 多专科对抗辩论
    - 证伪反思闭环
    - HITL 精准追问与挂起恢复
    - 指南守门与引用去幻
    """
    # ===== 患者数据 =====
    patient_data: Annotated[PatientData, merge_patient_data]
    
    # ===== 收集的数据 =====
    collected_history: Annotated[Dict[str, Any], operator.ior]
    collected_labs: Annotated[Dict[str, Any], operator.ior]
    collected_imaging: Annotated[Dict[str, Any], operator.ior]
    
    # ===== 追问历史 =====
    asked_questions: Annotated[List[Question], operator.add]
    patient_answers: Annotated[Dict[str, Any], operator.ior]
    
    # ===== 数据评估结果 =====
    data_assessment_result: Optional[DataAssessmentResult]

    # ===== 分诊结果 =====
    triage_result: Optional[TriageResult]
    
    # ===== 诊断假设 =====
    hypotheses: Annotated[List[DiagnosticHypothesis], operator.add]
    
    # ===== 反思结果 =====
    reflection_result: Optional[ReflectionResult]
    
    # ===== 对抗推理新增字段 =====
    
    # 辩论状态
    debate_state: Optional[DebateState]
    
    # 证伪日志
    falsification_log: Annotated[List[FalsificationEntry], operator.add]
    
    # HITL 状态: normal/interrupted/resumed
    hitl_status: str
    
    # HITL 挂起时的问题列表
    hitl_questions: List[Question]
    
    # 被证伪排除的假设
    excluded_hypotheses: Annotated[List[str], operator.add]
    
    # 记忆上下文
    memory_context: Dict[str, Any]
    
    # 指南校验结果
    guideline_check_result: Optional[GuidelineCheckEntry]
    
    # ===== 转诊与输出 =====
    referral_decision: Dict[str, Any]
    final_report: Optional[FinalReport]
    
    # ===== 知识图谱集成 =====
    kg_retrieval_result: Optional[Dict[str, Any]]
    kg_degradation_level: int
    kg_rare_disease_signal: Optional[float]
    
    # ===== 流程控制 =====
    current_phase: str
    retry_count: int
    debate_round: int
    errors: Annotated[List[str], operator.add]


class InformationCollectionState(TypedDict):
    """
    信息收集状态（用于病史采集子图）
    """
    patient_data: PatientData
    existing_history: Dict[str, Any]
    current_questions: List[Question]
    asked_questions: List[Question]
    collected_answers: Dict[str, Any]
    structured_history: Dict[str, Any]
    rare_disease_flags: List[Dict]
    completeness_score: float
    missing_critical_info: List[str]
    round_count: int
    max_rounds: int
    should_continue: bool
