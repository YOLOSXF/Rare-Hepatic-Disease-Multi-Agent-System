"""
指南守门员

强制比对 AASLD/EASL 指南必需条件，不符合临床规范的结论坚决打回重做。

KG集成:
- integration.guideline_verify=true: 使用 KG GUIDED_BY 关系 + Feature属性替代硬编码字典
- integration.guideline_verify=false: 回退到原有硬编码规则
- kg_interface=None: 回退到原有硬编码规则
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from loguru import logger


@dataclass
class GuidelineCheckResult:
    """指南校验结果"""
    diagnosis: str
    compliant: bool
    missing_criteria: List[str]
    met_criteria: List[str]
    recommendation: str


class GuidelineVerifier:
    """
    指南校验器
    
    功能：
    1. 检查诊断是否符合指南必需条件
    2. 识别缺失的诊断标准
    3. 提供合规性建议
    
    KG集成路径:
    - kg_interface + integration.guideline_verify → KG GUIDED_BY 关系
    - 降级路径 → 原有硬编码字典
    """
    
    def __init__(self, kg_interface: Optional[Any] = None):
        self.kg_interface = kg_interface
        self.guidelines = self._load_guidelines()
    
    def _load_guidelines(self) -> Dict:
        return {
            "肝豆状核变性": {
                "required": ["铜蓝蛋白降低", "肝病表现"],
                "supportive": ["K-F环", "神经系统症状", "尿铜升高"],
                "min_required": 2
            },
            "Wilson病": {
                "required": ["铜蓝蛋白降低", "肝病表现"],
                "supportive": ["K-F环", "神经系统症状", "尿铜升高"],
                "min_required": 2
            },
            "原发性胆汁性胆管炎": {
                "required": ["AMA-M2阳性", "ALP升高"],
                "supportive": ["IgM升高", "肝活检", "影像学"],
                "min_required": 2
            },
            "遗传性血色病": {
                "required": ["铁蛋白升高", "转铁蛋白饱和度升高"],
                "supportive": ["HFE基因突变", "肝活检", "关节病变"],
                "min_required": 2
            }
        }
    
    def verify_diagnosis(
        self,
        diagnosis: str,
        patient_data: Dict[str, Any]
    ) -> GuidelineCheckResult:
        """
        校验诊断是否符合指南（优先KG路径，降级到硬编码路径）
        """
        labs = patient_data.get('labs', {})
        symptoms_raw = patient_data.get('symptoms', {})
        symptoms = symptoms_raw if isinstance(symptoms_raw, dict) else {}
        
        kg_evaluated = False
        
        if self.kg_interface and self.kg_interface.is_enabled():
            try:
                kg_config = self.kg_interface.config
                if kg_config.integration.guideline_verify:
                    result = self._verify_via_kg(diagnosis, labs, symptoms)
                    if result is not None:
                        logger.info(f"KG指南路径: diagnosis={diagnosis}, compliant={result.compliant}")
                        return result
                    kg_evaluated = True
            except Exception as e:
                logger.warning(f"KG指南路径失败，降级到硬编码: {e}")
        
        return self._verify_via_hardcoded(diagnosis, labs, symptoms)
    
    def _verify_via_kg(
        self, diagnosis: str, labs: Dict, symptoms: Dict
    ) -> Optional[GuidelineCheckResult]:
        kg_context = self.kg_interface.get_guideline_context(diagnosis)
        guidelines = kg_context.get('guidelines', [])
        
        if not guidelines:
            return None
        
        required, supportive = self._get_criteria_from_kg(diagnosis)
        
        if not required and not supportive:
            return None
        
        met_criteria = []
        missing_criteria = []
        
        for criterion in required + supportive:
            if self._check_criterion_from_kg(criterion, labs, symptoms):
                met_criteria.append(criterion)
            else:
                missing_criteria.append(criterion)
        
        min_required = 2
        compliant = len(met_criteria) >= min_required
        
        recommendation = (
            "符合指南诊断标准" if compliant
            else f"缺少 {len(missing_criteria)} 项必需条件，建议补充检查"
        )
        
        return GuidelineCheckResult(
            diagnosis=diagnosis,
            compliant=compliant,
            missing_criteria=missing_criteria,
            met_criteria=met_criteria,
            recommendation=recommendation
        )
    
    def _get_criteria_from_kg(self, diagnosis: str) -> tuple:
        required = []
        supportive = []

        try:
            if self.kg_interface:
                results = self.kg_interface.query_criteria_for_diagnosis(diagnosis)
                for r in results:
                    name = r.get("name", "")
                    is_core = r.get("is_core", False)
                    if name:
                        if is_core:
                            required.append(name)
                        else:
                            supportive.append(name)
        except Exception as e:
            logger.warning(f"_get_criteria_from_kg failed: {e}")

        return required, supportive
    
    def _check_criterion_from_kg(
        self, criterion: str, labs: Dict, symptoms: Dict
    ) -> bool:
        lab_key_mapping = {
            '铜蓝蛋白': 'ceruloplasmin',
            'ceruloplasmin': 'ceruloplasmin',
            '角膜K-F环': 'kf_ring',
            'K-F环': 'kf_ring',
            'AMA-M2': 'AMA_M2',
            'AMA_M2': 'AMA_M2',
            '铁蛋白': 'ferritin',
            'ferritin': 'ferritin',
            '转铁蛋白饱和度': 'transferrin_saturation',
            'ALP': 'ALP',
            'ALT': 'ALT',
            'AST': 'AST',
        }
        
        for cn_key, en_key in lab_key_mapping.items():
            if cn_key in criterion or cn_key.lower() in criterion.lower():
                value = labs.get(en_key)
                if value is None:
                    value = symptoms.get(en_key)
                if value is None:
                    return False
                
                if '降低' in criterion or '减低' in criterion:
                    return isinstance(value, (int, float)) and value < 0.20 if en_key == 'ceruloplasmin' else True
                elif '升高' in criterion or '增高' in criterion:
                    thresholds = {
                        'ferritin': 1000, 'transferrin_saturation': 45,
                        'ALP': 120, 'ALT': 40, 'AST': 40,
                    }
                    threshold = thresholds.get(en_key, 0)
                    return isinstance(value, (int, float)) and value > threshold
                elif '阳性' in criterion:
                    return isinstance(value, (int, float)) and value > 0
                elif '阴性' in criterion:
                    return isinstance(value, (int, float)) and value <= 0
                elif isinstance(value, bool):
                    return value
                elif isinstance(value, (int, float)):
                    return True
                return False
        
        if '肝病' in criterion or '肝损' in criterion:
            alt = labs.get('ALT', 0)
            ast = labs.get('AST', 0)
            return alt > 40 or ast > 40
        
        if '神经系统' in criterion or '震颤' in criterion:
            tremor = symptoms.get('tremor', symptoms.get('震颤', False))
            neuro = symptoms.get('neurological_symptoms', False)
            return bool(tremor or neuro)
        
        return False
    
    def _verify_via_hardcoded(
        self, diagnosis: str, labs: Dict, symptoms: Dict
    ) -> GuidelineCheckResult:
        guideline = self.guidelines.get(diagnosis, {})
        if not guideline:
            return GuidelineCheckResult(
                diagnosis=diagnosis,
                compliant=True,
                missing_criteria=[],
                met_criteria=["无特定指南要求"],
                recommendation="继续观察"
            )
        
        required_criteria = guideline.get('required', [])
        min_required = guideline.get('min_required', 2)
        
        met_criteria = []
        missing_criteria = []
        
        for criterion in required_criteria:
            if self._check_criterion(criterion, labs, symptoms):
                met_criteria.append(criterion)
            else:
                missing_criteria.append(criterion)
        
        compliant = len(met_criteria) >= min_required
        
        recommendation = (
            "符合指南诊断标准" if compliant
            else f"缺少 {len(missing_criteria)} 项必需条件，建议补充检查"
        )
        
        return GuidelineCheckResult(
            diagnosis=diagnosis,
            compliant=compliant,
            missing_criteria=missing_criteria,
            met_criteria=met_criteria,
            recommendation=recommendation
        )
    
    def _check_criterion(self, criterion: str, labs: Dict, symptoms: Dict) -> bool:
        if "Ceruloplasmin降低" in criterion:
            return labs.get('ceruloplasmin', 1.0) < 0.20
        elif "AMA-M2阳性" in criterion:
            return labs.get('AMA_M2', 0) > 0
        elif "铁蛋白升高" in criterion:
            return labs.get('ferritin', 0) > 1000
        elif "转铁蛋白饱和度升高" in criterion:
            return labs.get('transferrin_saturation', 0) > 45
        elif "ALP升高" in criterion:
            return labs.get('ALP', 0) > 120
        elif "肝病表现" in criterion:
            return labs.get('ALT', 0) > 40 or labs.get('AST', 0) > 40
        return False
