"""
证伪检索工厂

主动搜寻排他性反例，推翻错误假设，触发 LangGraph 回退边。
"""

from typing import Any, Dict, List
from dataclasses import dataclass


@dataclass
class FalsificationResult:
    """证伪结果"""
    hypothesis: str
    falsified: bool
    contradiction_score: float
    contradicting_evidence: List[str]
    supporting_evidence: List[str]
    recommendation: str


class FalsificationEngine:
    """
    证伪引擎
    
    功能：
    1. 基于当前假设检索排他性证据
    2. 验证假设与证据的逻辑矛盾
    3. 生成证伪报告
    """
    
    def __init__(self, contradiction_threshold: float = 0.6):
        self.contradiction_threshold = contradiction_threshold
    
    def evaluate_hypotheses(
        self,
        hypotheses: List[Dict[str, Any]],
        patient_data: Dict[str, Any]
    ) -> List[FalsificationResult]:
        """
        评估假设的证伪可能性
        
        Args:
            hypotheses: 诊断假设列表
            patient_data: 患者数据
            
        Returns:
            List[FalsificationResult]: 证伪结果列表
        """
        results = []
        
        for hypothesis in hypotheses:
            result = self._evaluate_single_hypothesis(hypothesis, patient_data)
            results.append(result)
        
        return results
    
    def _evaluate_single_hypothesis(
        self,
        hypothesis: Dict[str, Any],
        patient_data: Dict[str, Any]
    ) -> FalsificationResult:
        """评估单个假设"""
        disease = hypothesis.get('disease', '')
        labs = patient_data.get('labs', {})
        symptoms = patient_data.get('symptoms', {})
        
        contradicting_evidence = []
        supporting_evidence = hypothesis.get('supporting_evidence', [])
        
        # 基于疾病特异性规则进行证伪
        if 'Wilson' in disease or 'wilson' in disease.lower():
            # Wilson病的证伪：铜蓝蛋白正常或升高
            ceruloplasmin = labs.get('Ceruloplasmin')
            if ceruloplasmin is not None and ceruloplasmin >= 0.2:
                contradicting_evidence.append(
                    f"铜蓝蛋白正常或升高 ({ceruloplasmin} g/L)，不支持Wilson病"
                )
        
        elif 'PBC' in disease or '胆汁性' in disease:
            # PBC的证伪：AMA-M2阴性
            ama_m2 = labs.get('AMA_M2')
            if ama_m2 is not None and ama_m2 <= 0:
                contradicting_evidence.append(
                    "AMA-M2阴性，不支持原发性胆汁性胆管炎"
                )
        
        elif '血色病' in disease or 'hemochromatosis' in disease.lower():
            # 血色病的证伪：铁蛋白正常
            ferritin = labs.get('Ferritin')
            if ferritin is not None and ferritin < 300:
                contradicting_evidence.append(
                    f"铁蛋白正常 ({ferritin} ng/mL)，不支持血色病"
                )
        
        # 计算矛盾分数
        contradiction_score = len(contradicting_evidence) * 0.3
        contradiction_score = min(1.0, contradiction_score)
        
        # 判断是否被证伪
        is_falsified = contradiction_score >= self.contradiction_threshold
        
        return FalsificationResult(
            hypothesis=disease,
            falsified=is_falsified,
            contradiction_score=contradiction_score,
            contradicting_evidence=contradicting_evidence,
            supporting_evidence=supporting_evidence,
            recommendation="排除该诊断" if is_falsified else "继续验证"
        )
