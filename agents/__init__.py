"""
Medical-Agent 智能体模块

包含功能智能体和专科智能体：
功能智能体：
1. HistoryCollector - 病史采集
2. LabInterpreter - 检验解读
3. ImagingAnalyzer - 影像分析
4. KnowledgeRetriever - 知识检索
5. DiagnosticReasoner - 诊断推理
6. ReferralDecider - 转诊决策

专科智能体（MDT对抗辩论）：
7. AttendingAgent - 主治医师（MDT主持）
8. HepatologistAgent - 肝病专科
9. NeurologistAgent - 神经专科
10. RheumatologistAgent - 风湿专科
11. HematologistAgent - 血液专科

版本说明：
- HistoryCollectorAgent 默认使用 V2 版本（支持 LangGraph + LLM 动态追问）
- V1 版本（history_collector.py）保留作为降级选项（纯规则引擎，不依赖 LLM）
"""

from .base_agent import BaseAgent
from .lab_interpreter import LabInterpreterAgent
from .imaging_analyzer import ImagingAnalyzerAgent
from .knowledge_retriever import KnowledgeRetrieverAgent
from .diagnostic_reasoner import DiagnosticReasonerAgent
from .referral_decider import ReferralDeciderAgent

# 专科智能体（MDT对抗辩论）
from .attending_agent import AttendingAgent
from .specialist_agents import (
    HepatologistAgent,
    NeurologistAgent,
    RheumatologistAgent,
    HematologistAgent,
)

# 延迟导入 V2 版本，避免循环依赖
# V2 依赖 core.langgraph_state，而 core 又导入 agents，形成循环
def __getattr__(name):
    """延迟导入 HistoryCollectorAgent（V2 版本）"""
    if name == "HistoryCollectorAgent":
        from .history_collector_v2 import HistoryCollectorAgentV2
        return HistoryCollectorAgentV2
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "BaseAgent",
    "HistoryCollectorAgent",  # V2 (history_collector_v2.py) - lazy loaded
    "LabInterpreterAgent",
    "ImagingAnalyzerAgent",
    "KnowledgeRetrieverAgent",
    "DiagnosticReasonerAgent",
    "ReferralDeciderAgent",
    # 专科智能体
    "AttendingAgent",
    "HepatologistAgent",
    "NeurologistAgent",
    "RheumatologistAgent",
    "HematologistAgent",
]
