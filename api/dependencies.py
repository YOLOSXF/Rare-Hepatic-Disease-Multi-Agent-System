"""依赖注入

提供LangGraph编排器及相关组件的依赖注入，支持懒加载和缓存。
"""
from typing import AsyncGenerator
from functools import lru_cache

@lru_cache()
def get_diagnosis_config():
    """获取诊断配置（缓存）"""
    return {
        "max_debate_rounds": 3,
        "max_falsification_retries": 2,
        "confidence_threshold": 0.92,
    }


@lru_cache()
def get_specialist_agent_pool():
    """
    获取专科Agent池（缓存）
    
    返回按专科领域划分的Agent字典，用于MDT动态组队。
    """
    from agents.specialist_agents import (
        HepatologistAgent,
        NeurologistAgent,
        RheumatologistAgent,
        HematologistAgent,
    )
    
    return {
        'HepatologistAgent': HepatologistAgent(),
        'NeurologyAgent': NeurologistAgent(),
        'RheumatologyAgent': RheumatologistAgent(),
        'HematologyAgent': HematologistAgent(),
    }


@lru_cache()
def get_mdt_manager():
    """
    获取MDT管理器（缓存）
    
    负责根据患者数据动态组建MDT团队。
    """
    from core.mdt_manager import MDTManager
    
    agent_pool = get_specialist_agent_pool()
    return MDTManager(agent_pool=agent_pool)


@lru_cache()
def get_medical_middleware():
    """
    获取医疗中间件组件（缓存）
    
    返回所有医疗领域中间件组件的实例。
    """
    from core.medical_middleware import (
        MemoryRetriever,
        InformationGapAssessor,
        DebateMediator,
        FalsificationEngine,
        GuidelineVerifier,
        ReferenceVerifier,
    )
    
    return {
        'memory_retriever': MemoryRetriever(),
        'gap_assessor': InformationGapAssessor(),
        'debate_mediator': DebateMediator(max_rounds=3),
        'falsification_engine': FalsificationEngine(),
        'guideline_verifier': GuidelineVerifier(),
        'reference_verifier': ReferenceVerifier(),
    }


@lru_cache()
def get_langgraph_orchestrator():
    """
    获取LangGraph编排器（缓存）
    
    构建完整的五层诊断流程图，包含：
    - L1: 数据预处理与基线校验
    - L2: 智能分诊
    - L3: MDT对抗辩论、证伪、HITL
    - L4: 知识检索（通过中间件）
    - L5: 报告生成
    """
    from core.graph_orchestrator import LangGraphDiagnosticGraph
    
    agent_pool = get_specialist_agent_pool()
    mdt_manager = get_mdt_manager()
    middleware = get_medical_middleware()
    config = get_diagnosis_config()
    
    return LangGraphDiagnosticGraph(
        specialist_agents=agent_pool,
        mdt_manager=mdt_manager,
        debate_mediator=middleware['debate_mediator'],
        falsification_engine=middleware['falsification_engine'],
        gap_assessor=middleware['gap_assessor'],
        guideline_verifier=middleware['guideline_verifier'],
        reference_verifier=middleware['reference_verifier'],
        memory_retriever=middleware['memory_retriever'],
        max_debate_rounds=config['max_debate_rounds'],
        max_falsification_retries=config['max_falsification_retries'],
    )
