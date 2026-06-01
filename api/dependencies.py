"""依赖注入

提供LangGraph编排器及相关组件的依赖注入，支持懒加载和缓存。
KG集成通过config.yaml的knowledge_graph.enabled总开关控制。
"""
from typing import AsyncGenerator
from functools import lru_cache
from loguru import logger


@lru_cache()
def get_diagnosis_config():
    """获取诊断配置（缓存）"""
    return {
        "max_debate_rounds": 3,
        "max_falsification_retries": 2,
        "confidence_threshold": 0.92,
    }


@lru_cache()
def get_kg_interface():
    """
    获取知识图谱接口（缓存）

    根据 config.yaml 中 knowledge_graph.enabled 决定是否激活。
    enabled=false 时返回 None，系统回退到硬编码路径。
    """
    from core.kg.kg_config import KGConfig
    from core.kg.kg_interface import KGInterface

    config = KGConfig.from_yaml()
    if not config.enabled:
        logger.info("KG功能总开关关闭 (knowledge_graph.enabled=false)，使用硬编码回退路径")
        return None

    try:
        interface = KGInterface(config=config)
        logger.info(
            f"KG已激活 | 引擎={config.engine} | "
            f"integration: falsification={config.integration.falsification}, "
            f"guideline_verify={config.integration.guideline_verify}, "
            f"info_gap={config.integration.info_gap}, "
            f"debate_context={config.integration.debate_context}"
        )
        return interface
    except Exception as e:
        logger.warning(f"KG初始化失败，回退到硬编码路径: {e}")
        return None


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

    KG启用时，将kg_interface注入到支持KG的中间件中：
    - FalsificationEngine: KG CONTRADICTS关系替代硬编码证伪规则
    - GuidelineVerifier: KG GUIDED_BY关系替代硬编码指南验证
    - InformationGapAssessor: KG IC值/度中心性驱动追问优先级
    """
    from core.medical_middleware import (
        MemoryRetriever,
        InformationGapAssessor,
        DebateMediator,
        FalsificationEngine,
        GuidelineVerifier,
        ReferenceVerifier,
    )

    kg_interface = get_kg_interface()

    return {
        'memory_retriever': MemoryRetriever(),
        'gap_assessor': InformationGapAssessor(kg_interface=kg_interface),
        'debate_mediator': DebateMediator(max_rounds=3),
        'falsification_engine': FalsificationEngine(kg_interface=kg_interface),
        'guideline_verifier': GuidelineVerifier(kg_interface=kg_interface),
        'reference_verifier': ReferenceVerifier(),
    }


@lru_cache()
def get_langgraph_orchestrator():
    """
    获取LangGraph编排器（缓存）

    构建完整的五层诊断流程图，包含：
    - L1: 数据预处理与基线校验
    - L2: 智能分诊
    - L3: MDT对抗辩论、证伪、HITL + KG知识检索
    - L4: 知识检索（通过中间件/KG）
    - L5: 报告生成
    """
    from core.graph_orchestrator import LangGraphDiagnosticGraph

    agent_pool = get_specialist_agent_pool()
    mdt_manager = get_mdt_manager()
    middleware = get_medical_middleware()
    config = get_diagnosis_config()
    kg_interface = get_kg_interface()

    return LangGraphDiagnosticGraph(
        specialist_agents=agent_pool,
        mdt_manager=mdt_manager,
        debate_mediator=middleware['debate_mediator'],
        falsification_engine=middleware['falsification_engine'],
        gap_assessor=middleware['gap_assessor'],
        guideline_verifier=middleware['guideline_verifier'],
        reference_verifier=middleware['reference_verifier'],
        memory_retriever=middleware['memory_retriever'],
        kg_interface=kg_interface,
        max_debate_rounds=config['max_debate_rounds'],
        max_falsification_retries=config['max_falsification_retries'],
    )
