"""
HITL 人机交互接口 (断点恢复)

处理诊断流程中的中断和恢复，支持医生补充信息后断点恢复。
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional

router = APIRouter(prefix="/hitl", tags=["hitl"])


class HITLResumeRequest(BaseModel):
    """HITL 恢复请求"""
    session_id: str
    patient_id: str
    answers: Dict[str, Any]  # 医生回答的问题


class HITLResumeResponse(BaseModel):
    """HITL 恢复响应"""
    success: bool
    session_id: str
    status: str  # resumed / completed / failed
    diagnosis: Optional[Dict[str, Any]] = None
    message: str


# 模拟 HITL 会话存储（实际应使用 Redis 或数据库）
hitl_sessions: Dict[str, Dict] = {}


@router.post("/resume", response_model=HITLResumeResponse, summary="HITL 断点恢复")
async def resume_diagnosis(request: HITLResumeRequest):
    """
    恢复被挂起的诊断流程
    
    流程：
    1. 验证会话ID
    2. 合并医生补充信息
    3. 从断点恢复 LangGraph 流程
    4. 返回诊断结果
    """
    session_id = request.session_id
    
    # 检查会话是否存在
    if session_id not in hitl_sessions:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")
    
    session = hitl_sessions[session_id]
    
    # 合并医生回答
    if 'patient_answers' not in session:
        session['patient_answers'] = {}
    session['patient_answers'].update(request.answers)
    
    # 更新会话状态
    session['hitl_status'] = 'resumed'
    
    # 从断点恢复诊断流程
    try:
        from core.graph_orchestrator import LangGraphDiagnosticGraph
        from core.medical_middleware import (
            MDTManager, DebateMediator, FalsificationEngine,
            InformationGapAssessor, GuidelineVerifier, MemoryRetriever
        )
        from agents.specialist_agents import (
            HepatologistAgent, NeurologistAgent,
            RheumatologistAgent, HematologistAgent
        )
        
        # 重建编排器
        agent_pool = {
            'HepatologistAgent': HepatologistAgent(),
            'NeurologyAgent': NeurologistAgent(),
            'RheumatologyAgent': RheumatologistAgent(),
            'HematologyAgent': HematologistAgent(),
        }
        
        orchestrator = LangGraphDiagnosticGraph(
            specialist_agents=agent_pool,
            mdt_manager=MDTManager(agent_pool=agent_pool),
            debate_mediator=DebateMediator(max_rounds=3),
            falsification_engine=FalsificationEngine(),
            gap_assessor=InformationGapAssessor(),
            guideline_verifier=GuidelineVerifier(),
            memory_retriever=MemoryRetriever(),
        )
        
        # 恢复患者数据
        patient_data = session.get('patient_data', {})
        
        # 合并补充信息到患者数据
        for key, value in request.answers.items():
            if key in ['labs', 'symptoms', 'history']:
                if key not in patient_data:
                    patient_data[key] = {}
                patient_data[key].update(value)
            else:
                patient_data[key] = value
        
        # 从断点恢复诊断流程（使用 resume_from_hitl 而非 run_full_pipeline）
        result = await orchestrator.resume_from_hitl(
            thread_id=session_id,
            patient_answers=request.answers,
        )
        
        # 清理会话
        del hitl_sessions[session_id]
        
        return HITLResumeResponse(
            success=True,
            session_id=session_id,
            status='completed',
            diagnosis=result.get('diagnosis'),
            message="诊断流程已恢复并完成"
        )
        
    except Exception as e:
        return HITLResumeResponse(
            success=False,
            session_id=session_id,
            status='failed',
            message=f"恢复诊断流程失败: {str(e)}"
        )


@router.get("/status/{session_id}", summary="查询 HITL 会话状态")
async def get_hitl_status(session_id: str):
    """查询 HITL 会话状态"""
    if session_id not in hitl_sessions:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")
    
    session = hitl_sessions[session_id]
    return {
        "session_id": session_id,
        "status": session.get('hitl_status', 'unknown'),
        "patient_id": session.get('patient_id'),
        "pending_questions": session.get('hitl_questions', []),
        "created_at": session.get('created_at')
    }


def store_hitl_session(session_id: str, session_data: Dict):
    """存储 HITL 会话（供诊断接口调用）"""
    from datetime import datetime
    session_data['created_at'] = datetime.now().isoformat()
    hitl_sessions[session_id] = session_data
