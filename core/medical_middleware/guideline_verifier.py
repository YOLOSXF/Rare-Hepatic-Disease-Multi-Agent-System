"""
指南守门员

强制比对 AASLD/EASL 指南必需条件，不符合临床规范的结论坚决打回重做。
"""

from typing import Any, Dict, List
from dataclasses import dataclass


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
    """
    
    def __init__(self):
        self.guidelines = self._load_guidelines()
    
    def _load_guidelines(self) -> Dict:
        """加载指南数据"""
        # 简化版指南规则
        return {
            "Wilson病": {
                "required": ["Ceruloplasmin降低", "肝病表现"],
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
        校验诊断是否符合指南
        
        Args:
            diagnosis: 诊断名称
            patient_data: 患者数据
            
        Returns:
            GuidelineCheckResult: 校验结果
        """
        labs = patient_data.get('labs', {})
        symptoms = patient_data.get('symptoms', {})
        
        guideline = self.guidelines.get(diagnosis, {})
        if not guideline:
            # 未知疾病，默认通过
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
        
        # 检查必需条件
        for criterion in required_criteria:
            if self._check_criterion(criterion, labs, symptoms):
                met_criteria.append(criterion)
            else:
                missing_criteria.append(criterion)
        
        # 判断是否合规
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
        """检查单个标准是否满足"""
        if "Ceruloplasmin降低" in criterion:
            return labs.get('Ceruloplasmin', 1.0) < 0.1
        elif "AMA-M2阳性" in criterion:
            return labs.get('AMA_M2', 0) > 0
        elif "铁蛋白升高" in criterion:
            return labs.get('Ferritin', 0) > 1000
        elif "转铁蛋白饱和度升高" in criterion:
            return labs.get('Transferrin_Saturation', 0) > 45
        elif "ALP升高" in criterion:
            return labs.get('ALP', 0) > 120
        elif "肝病表现" in criterion:
            return labs.get('ALT', 0) > 40 or labs.get('AST', 0) > 40
        return False
