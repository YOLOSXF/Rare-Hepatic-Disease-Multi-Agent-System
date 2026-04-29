"""
API 路由定义
"""

from fastapi import APIRouter, HTTPException
from datetime import datetime

from .schemas import PatientInput, DiagnosisResponse, HealthStatus

router = APIRouter()


@router.get("/", summary="根路径")
async def root():
    """API 根路径"""
    return {
        "name": "Medical-Agent API",
        "version": "2.0.0",
        "status": "running",
        "architecture": "LangGraph",
        "docs": "/docs"
    }


@router.post("/diagnose", response_model=DiagnosisResponse, summary="完整诊断")
async def diagnose(patient_input: PatientInput):
    """
    执行完整诊断流程（LangGraph）
    
    包含：
    - L1 数据预处理
    - L2 智能分诊
    - L3 深度诊断（罕见病路径）
    - L5 报告生成
    """
    # 实际实现调用 LangGraphOrchestrator.run_diagnosis()
    return DiagnosisResponse(
        success=True,
        patient_id=patient_input.patient_id,
        chief_complaint=patient_input.chief_complaint,
        primary_diagnosis=None,
        differential_diagnosis=[],
        confidence_score=0.0,
        referral_recommendation=None,
        evidence_chain=[],
        follow_up_plan={}
    )


@router.post("/screen", response_model=DiagnosisResponse, summary="快速筛查")
async def quick_screen(patient_input: PatientInput):
    """
    快速筛查（简化版）
    
    适用于基层医院快速分诊
    禁用反思引擎，提高响应速度
    """
    return DiagnosisResponse(
        success=True,
        patient_id=patient_input.patient_id,
        chief_complaint=patient_input.chief_complaint,
        primary_diagnosis=None,
        differential_diagnosis=[],
        confidence_score=0.0,
        referral_recommendation=None,
        evidence_chain=[],
        follow_up_plan={}
    )


@router.get("/health", response_model=HealthStatus, summary="健康检查")
async def health_check():
    """系统健康检查"""
    return HealthStatus(
        status="healthy",
        timestamp=datetime.now(),
        components={}
    )
