"""
API 数据模型定义
"""

from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field
from datetime import datetime


class PatientInput(BaseModel):
    """患者输入数据"""
    patient_id: str = Field(..., description="患者 ID")
    chief_complaint: str = Field(..., description="主诉")
    age: Optional[int] = Field(None, description="年龄")
    gender: Optional[str] = Field(None, description="性别")
    lab_results: Optional[Dict[str, Any]] = Field(None, description="检验结果")
    imaging_results: Optional[Dict[str, Any]] = Field(None, description="影像结果")
    medical_history: Optional[Dict[str, Any]] = Field(None, description="既往史")
    family_history: Optional[List[str]] = Field(None, description="家族史")
    medication_history: Optional[List[str]] = Field(None, description="用药史")
    alcohol_intake: Optional[float] = Field(None, description="饮酒量 (g/天)")


class DiagnosisResponse(BaseModel):
    """诊断响应"""
    success: bool
    patient_id: str
    chief_complaint: Optional[str] = None
    primary_diagnosis: Optional[Any] = None  # 可以是字符串或字典
    differential_diagnosis: List[Any] = []  # 可以是字符串列表或字典列表
    confidence_score: float = 0.0
    referral_recommendation: Optional[Dict] = None
    evidence_chain: List[Any] = []  # 可以是字符串列表
    follow_up_plan: Union[Dict, str] = {}
    metadata: Optional[Dict] = None
    error: Optional[str] = None
    # MDT 诊断字段
    debate_process: Optional[Dict] = None
    falsification_log: List[Any] = []
    guideline_check: Optional[Dict] = None
    # 分诊/补检相关字段（来自 L5 报告节点）
    triage: Dict = {}
    recommended_tests: List[Any] = []  # 字符串或 {test, purpose} 对象
    clinical_analysis: Optional[str] = None
    clinical_summary: Optional[str] = None
    uncertainty_reason: Optional[str] = None
    # HITL 中断字段
    hitl_status: Optional[str] = None
    hitl_session_id: Optional[str] = None
    hitl_questions: List[Dict] = []
    partial_diagnosis: List[Any] = []


class HealthStatus(BaseModel):
    """健康状态"""
    status: str
    timestamp: datetime
    components: Dict[str, bool]


class ScreeningResult(BaseModel):
    """筛查结果（简化版）"""
    risk_level: str
    common_diseases: List[Dict]
    rare_disease_flags: List[Dict]
    recommended_actions: List[str]
    referral_needed: bool
