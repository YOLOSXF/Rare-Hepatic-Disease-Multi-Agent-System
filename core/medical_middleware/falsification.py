"""
证伪检索工厂

主动搜寻排他性反例，推翻错误假设，触发 LangGraph 回退边。

KG集成:
- integration.falsification=true: 使用 KG CONTRADICTS 关系替代硬编码 if-elif
- integration.falsification=false: 回退到原有硬编码规则
- kg_interface=None: 回退到原有硬编码规则
"""

import re
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from loguru import logger


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
    
    KG集成路径:
    - kg_interface + integration.falsification → KG CONTRADICTS 关系
    - 降级路径 → 原有硬编码 if-elif 规则
    """
    
    def __init__(
        self,
        contradiction_threshold: float = 0.6,
        kg_interface: Optional[Any] = None,
    ):
        self.contradiction_threshold = contradiction_threshold
        self.kg_interface = kg_interface
    
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
        """评估单个假设（优先KG路径，降级到硬编码路径）"""
        disease = hypothesis.get('disease', '')
        labs = patient_data.get('labs', {})
        symptoms_raw = patient_data.get('symptoms', {})
        symptoms = symptoms_raw if isinstance(symptoms_raw, dict) else {}
        
        contradicting_evidence = []
        supporting_evidence = hypothesis.get('supporting_evidence', [])
        
        kg_evaluated = False
        
        if self.kg_interface and self.kg_interface.is_enabled():
            try:
                kg_config = self.kg_interface.config
                if kg_config.integration.falsification:
                    kg_context = self.kg_interface.get_falsification_context([disease])
                    contradicts = kg_context.get('contradicts', [])
                    
                    for c in contradicts:
                        condition = c.get('condition', '')
                        feature = c.get('feature', '')
                        strength = c.get('strength', 'moderate')
                        
                        if condition and self._check_contradict_condition(condition, labs, symptoms):
                            contradicting_evidence.append(
                                f"{feature}矛盾: {condition} (强度={strength})"
                            )
                    
                    kg_evaluated = True
                    logger.info(f"KG证伪路径: disease={disease}, contradicts={len(contradicts)}, matched={len(contradicting_evidence)}")
            except Exception as e:
                logger.warning(f"KG证伪路径失败，降级到硬编码: {e}")
        
        if not kg_evaluated:
            contradicting_evidence = self._hardcoded_falsification(disease, labs, symptoms)
        
        contradiction_score = min(1.0, len(contradicting_evidence) * 0.3)
        is_falsified = contradiction_score >= self.contradiction_threshold
        
        return FalsificationResult(
            hypothesis=disease,
            falsified=is_falsified,
            contradiction_score=contradiction_score,
            contradicting_evidence=contradicting_evidence,
            supporting_evidence=supporting_evidence,
            recommendation="排除该诊断" if is_falsified else "继续验证"
        )
    
    def _check_contradict_condition(
        self, condition: str, labs: Dict, symptoms: Dict
    ) -> bool:
        patterns = [
            (r'铜蓝蛋白\s*[≥>=]\s*([\d.]+)', 'ceruloplasmin', lambda v, t: v >= t),
            (r'铜蓝蛋白\s*[≤<=]\s*([\d.]+)', 'ceruloplasmin', lambda v, t: v <= t),
            (r'铁蛋白\s*[≥>=]\s*([\d.]+)', 'ferritin', lambda v, t: v >= t),
            (r'铁蛋白\s*[≤<=]\s*([\d.]+)', 'ferritin', lambda v, t: v <= t),
            (r'AMA[-\s]?M2\s*阴性', 'AMA_M2', lambda v, t: v is not None and v <= 0),
            (r'AMA[-\s]?M2\s*阳性', 'AMA_M2', lambda v, t: v is not None and v > 0),
            (r'(\w+)\s*[≥>=]\s*([\d.]+)', None, None),
            (r'(\w+)\s*[≤<=]\s*([\d.]+)', None, None),
        ]
        
        for pattern, lab_key, comparator in patterns:
            match = re.search(pattern, condition)
            if match and lab_key and comparator:
                value = labs.get(lab_key)
                if value is not None:
                    try:
                        threshold = float(match.group(1))
                        return comparator(value, threshold)
                    except (ValueError, TypeError):
                        continue
        
        lab_keys = [k for k in labs if k.lower() in condition.lower()]
        for key in lab_keys:
            val = labs.get(key)
            if val is not None and isinstance(val, (int, float)):
                if '正常' in condition or '升高' in condition:
                    return True
                if '阴性' in condition:
                    return val <= 0
        
        symptom_keys = [k for k in symptoms if k.lower() in condition.lower()]
        if symptom_keys:
            for key in symptom_keys:
                val = symptoms.get(key)
                if val:
                    return '无' not in condition and '阴性' not in condition
        
        return False
    
    def _hardcoded_falsification(
        self, disease: str, labs: Dict, symptoms: Dict
    ) -> List[str]:
        contradicting_evidence = []
        
        if 'Wilson' in disease or 'wilson' in disease.lower():
            ceruloplasmin = labs.get('ceruloplasmin')
            if ceruloplasmin is not None and ceruloplasmin >= 0.2:
                contradicting_evidence.append(
                    f"铜蓝蛋白正常或升高 ({ceruloplasmin} g/L)，不支持Wilson病"
                )
        
        elif 'PBC' in disease or '胆汁性' in disease:
            ama_m2 = labs.get('AMA_M2')
            if ama_m2 is not None and ama_m2 <= 0:
                contradicting_evidence.append(
                    "AMA-M2阴性，不支持原发性胆汁性胆管炎"
                )
        
        elif '血色病' in disease or 'hemochromatosis' in disease.lower():
            ferritin = labs.get('ferritin')
            if ferritin is not None and ferritin < 300:
                contradicting_evidence.append(
                    f"铁蛋白正常 ({ferritin} ng/mL)，不支持血色病"
                )
        
        return contradicting_evidence
