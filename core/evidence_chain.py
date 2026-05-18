"""
可溯源证据生成器 (Traceable Evidence Generator)
借鉴 DeepRare 的可解释性机制，生成可溯源的诊断证据链
"""

from typing import Dict, List, Any, Optional
from pydantic import BaseModel
from datetime import datetime
from loguru import logger


class EvidenceChainConfig(BaseModel):
    """证据链配置"""
    enable_guideline_references: bool = True
    enable_literature_references: bool = True
    min_confidence: float = 0.3


class TraceableEvidenceGenerator:
    """
    可溯源证据生成器
    
    DeepRare 核心特性：每条诊断建议都附带明确的因果路径和证据出处
    """
    
    def __init__(self, config: Optional[EvidenceChainConfig] = None):
        self.config = config or EvidenceChainConfig()
        
        # 指南引用数据库
        self.guideline_references = {
            'Wilson_Disease': [
                {
                    'title': '中华医学会肝豆状核变性诊疗指南',
                    'year': 2022,
                    'organization': '中华医学会肝病学分会',
                    'url': 'http://www.cma.org.cn/'
                },
                {
                    'title': 'EASL Clinical Practice Guidelines: Wilson disease',
                    'year': 2012,
                    'organization': 'European Association for the Study of the Liver',
                    'url': 'https://www.journal-of-hepatology.eu/'
                }
            ],
            'Autoimmune_Hepatitis': [
                {
                    'title': '自身免疫性肝炎诊断和治疗指南',
                    'year': 2021,
                    'organization': '中华医学会肝病学分会',
                    'url': 'http://www.cma.org.cn/'
                },
                {
                    'title': 'AASLD Practice Guidance: Autoimmune Hepatitis',
                    'year': 2019,
                    'organization': 'American Association for the Study of Liver Diseases',
                    'url': 'https://www.aasld.org/'
                }
            ],
            'Hereditary_Hemochromatosis': [
                {
                    'title': '遗传性血色病诊断和治疗专家共识',
                    'year': 2020,
                    'organization': '中国医师协会',
                    'url': 'http://www.cmda.net/'
                },
                {
                    'title': 'EASL Clinical Practice Guidelines: Haemochromatosis',
                    'year': 2022,
                    'organization': 'European Association for the Study of the Liver',
                    'url': 'https://www.journal-of-hepatology.eu/'
                }
            ],
            'Primary_Biliary_Cholangitis': [
                {
                    'title': '原发性胆汁性胆管炎诊断和治疗指南',
                    'year': 2021,
                    'organization': '中华医学会肝病学分会',
                    'url': 'http://www.cma.org.cn/'
                },
                {
                    'title': 'EASL Clinical Practice Guidelines: PBC',
                    'year': 2017,
                    'organization': 'European Association for the Study of the Liver',
                    'url': 'https://www.journal-of-hepatology.eu/'
                }
            ]
        }
        
        # 诊断标准数据库
        self.diagnostic_criteria = {
            'Wilson_Disease': {
                'major_criteria': [
                    {'name': '铜蓝蛋白降低', 'field': 'ceruloplasmin', 'threshold': '<0.20 g/L'},
                    {'name': 'K-F 环阳性', 'field': 'kf_ring', 'threshold': '阳性'},
                    {'name': '24h 尿铜升高', 'field': 'urine_copper', 'threshold': '>100 μg/24h'}
                ],
                'minor_criteria': [
                    {'name': '神经精神症状', 'field': 'neurological_symptoms'},
                    {'name': '肝功能异常', 'field': 'liver_function_abnormal'},
                    {'name': '家族史', 'field': 'family_history'}
                ]
            },
            'Autoimmune_Hepatitis': {
                'major_criteria': [
                    {'name': '自身抗体阳性', 'field': 'autoantibodies', 'threshold': 'ANA/SMA/LKM-1 阳性'},
                    {'name': 'IgG 升高', 'field': 'IgG', 'threshold': '>1.1×ULN'},
                    {'name': '界面性肝炎', 'field': 'interface_hepatitis', 'threshold': '肝活检'}
                ]
            }
        }
    
    def generate_evidence_chain(
        self,
        diagnosis: str,
        patient_data: Dict,
        hypotheses: List[Dict]
    ) -> List[Dict]:
        """
        生成可溯源的诊断证据链
        
        Args:
            diagnosis: 主要诊断
            patient_data: 患者数据
            hypotheses: 鉴别诊断列表
        
        Returns:
            证据链列表
        """
        evidence_chain = []
        
        # 1. 初始假设生成
        evidence_chain.append({
            'step': 1,
            'action': '初始假设生成',
            'timestamp': datetime.now().isoformat(),
            'input': '患者症状 + 检验结果',
            'output': self._summarize_hypotheses(hypotheses),
            'evidence_sources': ['病史采集', '检验解读', '影像分析'],
            'reasoning': self._generate_initial_reasoning(hypotheses)
        })
        
        # 2. 假设验证
        evidence_chain.append({
            'step': 2,
            'action': '假设验证',
            'timestamp': datetime.now().isoformat(),
            'input': '初始假设列表',
            'output': self._summarize_verification(hypotheses),
            'evidence_sources': ['诊疗指南', '文献检索', '诊断标准'],
            'reasoning': self._generate_verification_reasoning(diagnosis, patient_data)
        })
        
        # 3. 诊断修正
        evidence_chain.append({
            'step': 3,
            'action': '诊断修正',
            'timestamp': datetime.now().isoformat(),
            'input': '验证后的假设',
            'output': self._summarize_revision(diagnosis, hypotheses),
            'evidence_sources': ['排除标准', '鉴别诊断', '专家共识'],
            'reasoning': self._generate_revision_reasoning(diagnosis, hypotheses)
        })
        
        # 4. 支持证据详情
        if self.config.enable_guideline_references:
            evidence_chain.append({
                'step': 4,
                'action': '指南和文献支持',
                'timestamp': datetime.now().isoformat(),
                'guideline_references': self.guideline_references.get(diagnosis, []),
                'diagnostic_criteria': self.diagnostic_criteria.get(diagnosis, {})
            })
        
        return evidence_chain
    
    def _summarize_hypotheses(self, hypotheses: List[Dict]) -> str:
        """总结假设列表"""
        if not hypotheses:
            return "无明确假设"
        
        summary_parts = []
        for i, h in enumerate(hypotheses[:3], 1):
            disease = h.get('disease', 'Unknown')
            confidence = h.get('confidence', 0)
            summary_parts.append(f"{i}. {disease} (置信度：{confidence:.2f})")
        
        return "; ".join(summary_parts)
    
    def _summarize_verification(self, hypotheses: List[Dict]) -> str:
        """总结验证结果"""
        if not hypotheses:
            return "无验证结果"
        
        top = hypotheses[0]
        verification = top.get('verification', {})
        criteria_met = verification.get('criteria_met', {})
        
        major = "主要标准满足" if criteria_met.get('major_criteria') else "主要标准未满足"
        minor = "次要标准满足" if criteria_met.get('minor_criteria') else "次要标准部分满足"
        
        return f"{major}; {minor}"
    
    def _summarize_revision(self, diagnosis: str, hypotheses: List[Dict]) -> str:
        """总结修正结果"""
        if not hypotheses:
            return "无明确诊断"
        
        top = hypotheses[0]
        confidence = top.get('confidence', 0)
        
        if confidence >= 0.8:
            return f"高度怀疑{diagnosis}，建议进一步确诊检查"
        elif confidence >= 0.5:
            return f"中度怀疑{diagnosis}，建议专科随访"
        else:
            return f"低度怀疑{diagnosis}，建议继续观察"
    
    def _generate_initial_reasoning(self, hypotheses: List[Dict]) -> str:
        """生成初始推理说明"""
        if not hypotheses:
            return "基于现有信息，无法生成明确假设"
        
        top = hypotheses[0]
        disease = top.get('disease', '未知疾病')
        supporting = top.get('supporting_evidence', [])
        
        reasoning = f"初步考虑{disease}，主要依据："
        
        # supporting 可能是字符串列表或字典列表
        if isinstance(supporting, list):
            # 取前 3 个证据
            for i, evidence in enumerate(supporting[:3], 1):
                if isinstance(evidence, str):
                    reasoning += f" ({i}){evidence};"
                elif isinstance(evidence, dict):
                    finding = evidence.get('finding', '未知发现')
                    reasoning += f" ({i}){finding};"
        else:
            reasoning += " 临床表现为依据;"
        
        return reasoning
    
    def _generate_verification_reasoning(self, diagnosis: str, patient_data: Dict) -> str:
        """生成验证推理说明"""
        reasoning = f"针对{diagnosis}进行验证："
        
        # 检查诊断标准
        criteria = self.diagnostic_criteria.get(diagnosis, {})
        major_criteria = criteria.get('major_criteria', [])
        
        if major_criteria:
            met_count = 0
            for criterion in major_criteria:
                field = criterion.get('field')
                if patient_data.get('labs', {}).get(field) or patient_data.get('history', {}).get(field):
                    met_count += 1
            
            reasoning += f" 满足{met_count}/{len(major_criteria)}项主要标准;"
        
        # 检查矛盾点
        contradictions = self._find_contradictions(diagnosis, patient_data)
        if contradictions:
            reasoning += f" 发现{len(contradictions)}个矛盾点:{contradictions[0]};"
        
        return reasoning
    
    def _generate_revision_reasoning(self, diagnosis: str, hypotheses: List[Dict]) -> str:
        """生成修正推理说明"""
        if not hypotheses:
            return "无修正推理"
        
        top = hypotheses[0]
        confidence = top.get('confidence', 0)
        
        reasoning = f"综合评估后，{diagnosis}的可能性为"
        
        if confidence >= 0.8:
            reasoning += "高度可疑"
        elif confidence >= 0.5:
            reasoning += "中度可疑"
        else:
            reasoning += "低度可疑"
        
        # 排除的假设
        excluded_count = len([h for h in hypotheses if h.get('status') == 'excluded'])
        if excluded_count > 0:
            reasoning += f"; 已排除{excluded_count}个其他假设"
        
        return reasoning
    
    def _find_contradictions(self, disease: str, patient_data: Dict) -> List[str]:
        """寻找矛盾点（简化版）"""
        contradictions = []
        
        if disease == 'Wilson_Disease':
            ceruloplasmin = patient_data.get('labs', {}).get('ceruloplasmin', 1.0)
            if ceruloplasmin > 0.60:
                contradictions.append('铜蓝蛋白正常或升高')
        
        return contradictions
    
    def generate_referral_evidence(self, referral_decision: Dict) -> List[Dict]:
        """生成转诊证据"""
        evidence = []
        
        urgency = referral_decision.get('urgency', 'routine')
        reasons = referral_decision.get('reasons', [])
        
        evidence.append({
            'type': 'referral_recommendation',
            'urgency': urgency,
            'reasons': reasons,
            'guideline_basis': '根据相关诊疗指南的转诊指征'
        })
        
        return evidence
