"""
转诊决策 Agent
负责生成转诊建议和分诊决策
"""

from typing import Dict, List, Optional, Any
from loguru import logger

from .base_agent import BaseAgent, AgentConfig, AgentResponse


class ReferralDeciderConfig(AgentConfig):
    name: str = "referral_decider"
    referral_thresholds: Dict[str, float] = {
        'emergency': 0.95,
        'urgent': 0.8,
        'routine': 0.5
    }


class ReferralDeciderAgent(BaseAgent):
    """
    转诊决策 Agent
    
    功能：
    1. 评估转诊必要性
    2. 确定转诊紧急程度
    3. 生成转诊建议
    """
    
    def __init__(self, config: Optional[ReferralDeciderConfig] = None):
        super().__init__(config or ReferralDeciderConfig())
        self.config: ReferralDeciderConfig = config or ReferralDeciderConfig()
    
    @property
    def name(self) -> str:
        return "referral_decider"
    
    async def execute(self, input_data: Dict[str, Any]) -> AgentResponse:
        """执行转诊决策"""
        try:
            hypotheses = input_data.get('hypotheses', [])
            confidence = input_data.get('confidence', 0)
            missing_info = input_data.get('missing_info', [])
            
            # 确定紧急程度
            urgency = self._determine_urgency(confidence, hypotheses)
            
            # 生成转诊原因
            reasons = self._generate_reasons(hypotheses, missing_info)
            
            # 是否需要转诊
            needed = urgency != 'none'
            
            result = {
                'needed': needed,
                'urgency': urgency,
                'reasons': reasons,
                'recommended_department': self._recommend_department(hypotheses),
                'recommended_tests': self._recommend_tests(hypotheses, missing_info)
            }
            
            return self._create_response(success=True, data=result)
            
        except Exception as e:
            logger.error(f"Referral decision failed: {e}")
            return self._create_response(success=False, error=str(e))
    
    def _determine_urgency(self, confidence: float, hypotheses: List[Dict]) -> str:
        """确定紧急程度"""
        if confidence >= self.config.referral_thresholds['emergency']:
            return 'emergency'
        elif confidence >= self.config.referral_thresholds['urgent']:
            return 'urgent'
        elif confidence >= self.config.referral_thresholds['routine']:
            return 'routine'
        else:
            return 'none'
    
    def _generate_reasons(self, hypotheses: List[Dict], missing_info: List[str]) -> List[str]:
        """生成转诊原因"""
        reasons = []
        
        if hypotheses:
            top = hypotheses[0]
            reasons.append(f"可疑{top.get('disease', '肝病')}")
        
        if missing_info:
            reasons.append(f"需要进一步检查：{', '.join(missing_info[:3])}")
        
        return reasons
    
    def _recommend_department(self, hypotheses: List[Dict]) -> str:
        """推荐科室"""
        if not hypotheses:
            return '消化内科'
        
        disease = hypotheses[0].get('disease', '')
        
        if 'Wilson' in disease:
            return '肝病科 + 神经内科'
        elif 'Autoimmune' in disease:
            return '肝病科 + 风湿免疫科'
        elif 'Hemochromatosis' in disease:
            return '肝病科 + 血液科'
        else:
            return '肝病科'
    
    def _recommend_tests(self, hypotheses: List[Dict], missing_info: List[str]) -> List[str]:
        """推荐检查"""
        tests = []
        
        for hypothesis in hypotheses[:2]:
            disease = hypothesis.get('disease')
            if disease == 'Wilson_Disease':
                tests.extend(['铜蓝蛋白', '24 小时尿铜', '裂隙灯检查'])
            elif disease == 'Autoimmune_Hepatitis':
                tests.extend(['自身抗体谱', 'IgG', '肝活检'])
        
        return list(set(tests))
