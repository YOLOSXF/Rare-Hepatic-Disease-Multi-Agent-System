"""
诊断接口 (L1-L5 对抗推理诊断)

使用新的MDT架构和医疗中间件进行诊断。
"""

from functools import lru_cache
from fastapi import APIRouter, HTTPException

from ..schemas import PatientInput, DiagnosisResponse
from ..dependencies import get_langgraph_orchestrator

router = APIRouter(prefix="/diagnose", tags=["diagnosis"])


@router.post("/", response_model=DiagnosisResponse, summary="完整对抗推理诊断")
async def diagnose(patient_input: PatientInput):
    """
    执行完整对抗推理诊断流程 (LangGraph v3 StateGraph + MDT架构)

    流程: L1预处理 → L2分诊 → L3 MDT对抗辩论 → L5报告生成
    """
    orchestrator = get_langgraph_orchestrator()

    patient_data = {
        'patient_id': patient_input.patient_id,
        'age': patient_input.age,
        'gender': patient_input.gender,
        'chief_complaint': patient_input.chief_complaint,
        'history': patient_input.medical_history or {},
        'symptoms': patient_input.symptoms or {},
        'eye_exam': patient_input.eye_exam or {},
        'labs': patient_input.lab_results or {},
        'ultrasound': patient_input.imaging_results or {},
    }

    config = {'thread_id': f"diag_{patient_input.patient_id}"}
    result = await orchestrator.run_full_pipeline(patient_data, config=config)

    if result.get('status') == 'interrupted':
        return DiagnosisResponse(
            success=True,
            patient_id=patient_input.patient_id,
            hitl_status='interrupted',
            hitl_session_id=config['thread_id'],
            hitl_questions=[
                {
                    'field': q.get('field', ''),
                    'question': q.get('question', ''),
                    'rationale': q.get('rationale', ''),
                    'priority': q.get('priority', 'medium'),
                }
                for q in result.get('hitl_questions', [])
            ],
            partial_diagnosis=result.get('partial_diagnosis', []),
            evidence_chain=[],
        )

    top_diag = result.get('diagnosis') or {}
    diff_diag = result.get('differential_diagnosis', [])
    referral = result.get('referral', {})
    has_dict_diag = diff_diag and isinstance(diff_diag[0], dict)

    # 从 final_report 中提取置信度（不同报告类型字段位置不同）
    confidence_score = result.get('confidence', 0) or (top_diag.get('confidence', 0) if top_diag else 0)

    # primary_diagnosis 兼容不同报告类型
    primary_diagnosis = top_diag if isinstance(top_diag, dict) and top_diag else result.get('diagnosis')

    # 诊断路径映射：报告中的 path 字段使用简写（common/rare/uncertain），
    # 前端需要根据完整路径名判断报告类型
    path_mapping = {
        'common': 'common_fast_path',
        'rare': 'rare_deep_path',
        'uncertain': 'uncertain_fallback',
        'insufficient_data': 'uncertain_fallback',
    }
    short_path = result.get('path', 'unknown')
    triage_path = path_mapping.get(short_path, short_path)

    # 如果 triage 子对象中有完整路径，优先使用
    triage_obj = result.get('triage_result', {})
    if isinstance(triage_obj, dict) and triage_obj.get('path'):
        triage_path = triage_obj['path']

    return DiagnosisResponse(
        success=True,
        patient_id=patient_input.patient_id,
        chief_complaint=patient_input.chief_complaint,
        primary_diagnosis=primary_diagnosis,
        differential_diagnosis=diff_diag[:5],
        confidence_score=confidence_score,
        evidence_chain=[
            f"{d.get('source', '')}: {', '.join(str(e) for e in (d.get('supporting_evidence') or [])[:2])}"
            for d in diff_diag[:3]
        ] if has_dict_diag else [str(d) for d in diff_diag[:3]],
        referral_recommendation=referral if referral else None,
        follow_up_plan=result.get('follow_up_plan') or {},
        # LLM 生成的分析字段（来自 L5 报告节点）
        metadata={
            'data_completeness': result.get('data_completeness_score', 0),
            'triage_path': triage_path,
            'mode': 'full_pipeline',
            'version': result.get('report_version', 'mdt_v1'),
            'is_rare_disease_alert': result.get('is_rare_disease_alert', False),
            'knowledge_graph': result.get('knowledge_graph', {}),
            'memory_context': result.get('memory_context'),
            'excluded_hypotheses': result.get('excluded_hypotheses', []),
            'report_type': result.get('report_type', 'FINAL_DIAGNOSIS'),
        },
        # MDT 诊断字段
        debate_process=result.get('debate_process'),
        falsification_log=result.get('falsification_log', []),
        guideline_check=result.get('guideline_check'),
        # 分诊/补检相关字段（来自 L5b 或 L5c 报告）
        triage=triage_obj,
        recommended_tests=result.get('recommended_tests', []),
        clinical_analysis=result.get('clinical_analysis'),
        clinical_summary=result.get('clinical_summary'),
        uncertainty_reason=result.get('uncertainty_reason'),
    )


@router.post("/screen", response_model=DiagnosisResponse, summary="快速筛查")
async def quick_screen(patient_input: PatientInput):
    """
    快速筛查 — 使用 L1+L2 轻量级流程

    仅执行预处理、数据评估和分诊，不启动 MDT 辩论。
    适用于基层医院快速分诊场景。
    """
    from core.graph_orchestrator import LangGraphDiagnosticGraph
    from core.preprocessor import DataPreprocessor
    from core.data_assessor import DataCompletenessAssessor
    from core.triage import IntelligentTriage

    patient_data = {
        'patient_id': patient_input.patient_id,
        'age': patient_input.age,
        'gender': patient_input.gender,
        'chief_complaint': patient_input.chief_complaint,
        'history': patient_input.medical_history or {},
        'symptoms': patient_input.symptoms or {},
        'eye_exam': patient_input.eye_exam or {},
        'labs': patient_input.lab_results or {},
    }

    # L1: 预处理 + 评估
    preprocessor = DataPreprocessor()
    cleaned = preprocessor.preprocess(patient_data)

    assessor = DataCompletenessAssessor()
    assessment = assessor.assess(cleaned.standardized_data)

    # L2: 分诊
    triage = IntelligentTriage()
    triage_result = await triage.triage(patient_data)

    path = 'uncertain'
    triage_info = {}
    if triage_result and hasattr(triage_result, 'path'):
        path = triage_result.path
        triage_info = {
            'path': path,
            'diagnosis': getattr(triage_result, 'diagnosis', None),
            'confidence': getattr(triage_result, 'confidence', 0),
            'urgency': getattr(triage_result, 'urgency', 'routine'),
            'recommended_tests': getattr(triage_result, 'recommended_tests', []),
        }

    # 诊断路径映射 (对应 graph_orchestrator.py L198-200)
    path_mapping = {
        'common': 'common_fast_path',      # 常见病快速通道
        'rare': 'rare_deep_path',          # 罕见病预警
        'uncertain': 'uncertain_fallback', # 不确定/数据不足
        'insufficient_data': 'uncertain_fallback',
    }
    path_display = path_mapping.get(path, 'uncertain_fallback')

    return DiagnosisResponse(
        success=True,
        patient_id=patient_input.patient_id,
        chief_complaint=patient_input.chief_complaint,
        primary_diagnosis=triage_info.get('diagnosis'),
        differential_diagnosis=[triage_info.get('diagnosis')] if triage_info.get('diagnosis') else [],
        confidence_score=triage_info.get('confidence', 0),
        referral_recommendation={
            'needed': path == 'rare',
            'urgency': triage_info.get('urgency', 'routine'),
            'recommendation': f'分诊路径: {path_display}',
        },
        evidence_chain=[f'数据完整度: {assessment.score:.0%}'],
        metadata={
            'data_completeness': assessment.score,
            'triage_path': path_display,
            'mode': 'screening',
        },
    )
