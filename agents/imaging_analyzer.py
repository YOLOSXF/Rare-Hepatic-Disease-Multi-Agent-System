"""
影像分析 Agent
负责解读肝脏影像学检查报告（超声、CT、MRI）
"""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel
from loguru import logger

from .base_agent import BaseAgent, AgentConfig, AgentResponse


class ImagingAnalyzerConfig(AgentConfig):
    name: str = "imaging_analyzer"
    supported_modalities: List[str] = ["ultrasound", "ct", "mri"]


class ImagingAnalyzerAgent(BaseAgent):
    """
    影像分析 Agent
    
    功能：
    1. 结构化解读影像报告
    2. 识别肝硬化、脂肪肝、占位等病变
    3. 罕见病影像特征提示
    """
    
    def __init__(self, config: Optional[ImagingAnalyzerConfig] = None):
        super().__init__(config or ImagingAnalyzerConfig())
        self.config: ImagingAnalyzerConfig = config or ImagingAnalyzerConfig()
    
    @property
    def name(self) -> str:
        return "imaging_analyzer"
    
    async def execute(self, input_data: Dict[str, Any]) -> AgentResponse:
        """执行影像分析"""
        try:
            imaging_results = input_data.get('imaging_results', {})
            
            # 解析影像发现
            findings = self._parse_findings(imaging_results)
            
            # 识别病变模式
            patterns = self._identify_patterns(findings)
            
            # 罕见病特征
            rare_features = self._identify_rare_features(findings)
            
            result = {
                'modality': imaging_results.get('modality', 'unknown'),
                'findings': findings,
                'patterns': patterns,
                'rare_features': rare_features,
                'impression': imaging_results.get('impression', ''),
                'recommendations': self._generate_recommendations(patterns, rare_features)
            }
            
            return self._create_response(success=True, data=result)
            
        except Exception as e:
            logger.error(f"Imaging analysis failed: {e}")
            return self._create_response(success=False, error=str(e))
    
    def _parse_findings(self, imaging_results: Dict) -> Dict:
        """解析影像发现"""
        return {
            'liver_size': imaging_results.get('liver_size', 'normal'),
            'liver_contour': imaging_results.get('liver_contour', 'smooth'),
            'echogenicity': imaging_results.get('echogenicity', 'normal'),
            'focal_lesions': imaging_results.get('focal_lesions', []),
            'biliary_duct': imaging_results.get('biliary_duct', 'normal'),
            'portal_vein': imaging_results.get('portal_vein', 'normal'),
            'spleen_size': imaging_results.get('spleen_size', 'normal'),
            'ascites': imaging_results.get('ascites', False)
        }
    
    def _identify_patterns(self, findings: Dict) -> List[Dict]:
        """识别病变模式"""
        patterns = []
        
        # 脂肪肝模式
        if findings.get('echogenicity') == 'increased':
            patterns.append({
                'pattern': 'fatty_liver',
                'confidence': 0.8,
                'features': ['肝回声增强']
            })
        
        # 肝硬化模式
        if findings.get('liver_contour') == 'nodular' and findings.get('ascites'):
            patterns.append({
                'pattern': 'cirrhosis',
                'confidence': 0.85,
                'features': ['肝脏结节状', '腹水']
            })
        
        return patterns
    
    def _identify_rare_features(self, findings: Dict) -> List[Dict]:
        """识别罕见病影像特征"""
        features = []
        
        # Wilson 病：基底节异常信号（MRI）
        # 血色病：肝脏铁沉积（MRI T2*降低）
        # 多囊肝：多发囊性病变
        
        return features
    
    def _generate_recommendations(self, patterns: List, rare_features: List) -> List[str]:
        """生成建议"""
        recommendations = []
        
        for pattern in patterns:
            if pattern['pattern'] == 'fatty_liver':
                recommendations.append('建议控制体重、改善生活方式')
            elif pattern['pattern'] == 'cirrhosis':
                recommendations.append('建议专科就诊，评估肝硬化并发症')
        
        return recommendations
