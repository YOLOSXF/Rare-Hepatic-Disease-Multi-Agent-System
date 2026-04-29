"""
Medical-Agent 核心引擎模块

注：CentralCoordinator 已在 v2.0 版本移除，请使用 LangGraphOrchestrator 替代。
"""

from .reflection_engine import SelfReflectionEngine
from .evidence_chain import TraceableEvidenceGenerator

__all__ = [
    "SelfReflectionEngine",
    "TraceableEvidenceGenerator",
]
