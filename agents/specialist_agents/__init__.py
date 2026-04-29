"""
专科 Agent 池

基于专科领域划分的智能体，每个 Agent 带有特定的认知视角和偏误属性，
通过对抗辩论机制提升诊断准确性。
"""

from .hepatologist import HepatologistAgent
from .neurologist import NeurologistAgent
from .rheumatologist import RheumatologistAgent
from .hematologist import HematologistAgent

__all__ = [
    "HepatologistAgent",
    "NeurologistAgent", 
    "RheumatologistAgent",
    "HematologistAgent",
]
