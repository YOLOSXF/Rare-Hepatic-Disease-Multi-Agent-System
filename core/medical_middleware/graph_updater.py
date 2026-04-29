"""
确定性图权重更新 (EWAS)

基于辩论结果，使用确定性算法更新知识图谱的节点和边权重。
"""

from typing import Any, Dict, List
from dataclasses import dataclass


@dataclass
class GraphUpdateResult:
    """图更新结果"""
    updated_weights: Dict[str, float]
    activated_paths: List[str]
    suppressed_nodes: List[str]


class GraphUpdater:
    """
    知识图谱权重更新器 (EWAS算法)
    
    功能：
    1. 基于辩论结果更新节点权重
    2. 基于共识程度调整边权重
    3. 激活高置信度诊断路径
    4. 抑制被证伪的节点
    """
    
    def __init__(self, initial_weights: Dict[str, float] = None):
        self.weights = initial_weights or {}
        self.learning_rate = 0.1
        self.consensus_boost = 0.2
        self.falsification_penalty = 0.3
    
    def update_from_debate_result(
        self,
        debate_result: Any,
        patient_data: Dict[str, Any]
    ) -> Dict[str, float]:
        """
        基于辩论结果更新图谱权重
        
        Args:
            debate_result: 辩论结果
            patient_data: 患者数据
            
        Returns:
            Dict[str, float]: 更新后的权重
        """
        new_weights = dict(self.weights)
        
        # 提取辩论结果信息
        consensus = getattr(debate_result, 'consensus_diagnosis', None)
        confidence = getattr(debate_result, 'confidence', 0.0)
        perspectives = getattr(debate_result, 'all_perspectives', [])
        
        # 更新共识诊断的权重
        if consensus:
            current_weight = new_weights.get(consensus, 0.5)
            # 共识提升权重
            boost = self.consensus_boost * confidence
            new_weights[consensus] = min(1.0, current_weight + boost)
        
        # 基于各专科观点更新权重
        for perspective in perspectives:
            hypothesis = perspective.get('hypothesis', '')
            specialty = perspective.get('specialty', '')
            conf = perspective.get('confidence', 0.0)
            
            if hypothesis:
                current_weight = new_weights.get(hypothesis, 0.5)
                # 根据专科置信度调整
                adjustment = self.learning_rate * (conf - 0.5)
                new_weights[hypothesis] = max(0.0, min(1.0, current_weight + adjustment))
        
        self.weights = new_weights
        return new_weights
    
    def suppress_disease(self, disease: str):
        """
        抑制被证伪的疾病节点
        
        Args:
            disease: 疾病名称
        """
        if disease in self.weights:
            self.weights[disease] = max(0.0, self.weights[disease] - self.falsification_penalty)
    
    def get_activated_paths(self, threshold: float = 0.7) -> List[str]:
        """
        获取激活的诊断路径
        
        Args:
            threshold: 激活阈值
            
        Returns:
            List[str]: 激活的疾病列表
        """
        return [disease for disease, weight in self.weights.items() if weight >= threshold]
