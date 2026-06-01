"""
风湿专科 Agent

专注于自身免疫性疾病的诊断与鉴别，具有风湿专科的认知视角和诊断偏误。
"""

from typing import Any, Dict, List, Optional
from agents.base_agent import BaseAgent, AgentConfig, AgentResponse


class RheumatologistAgent(BaseAgent):
    """
    风湿专科 Agent
    
    认知视角：从自身免疫和炎症角度出发，关注自身抗体、炎症指标、多系统受累
    认知偏误：可能过度关注免疫指标，忽视感染、代谢等其他病因
    """
    
    def __init__(self, config: AgentConfig = None):
        super().__init__(config or AgentConfig(name="Rheumatologist"))
        self.specialty = "rheumatology"
        self.bias_description = "倾向于从自身免疫性疾病解释多系统受累，可能忽视代谢性或遗传性疾病"
    
    @property
    def name(self) -> str:
        return "RheumatologistAgent"
    
    async def execute(self, input_data: Dict[str, Any], kg_context: Optional[Dict] = None) -> AgentResponse:
        """执行风湿专科分析
        
        Args:
            input_data: 包含 patient_data 和 context 的字典
            kg_context: 知识图谱上下文 (candidates, matched_features, differentials)
        """
        patient_data = input_data.get('patient_data', {})
        context = input_data.get('context', {})
        if kg_context is None:
            kg_context = context.get('kg_context')
        
        labs = patient_data.get('labs', {})
        symptoms = patient_data.get('symptoms', {})
        history = patient_data.get('history', {})
        
        findings = []
        differential_diagnosis = []
        
        if kg_context and kg_context.get('candidates'):
            findings.append(f"KG候选疾病参考: {', '.join(kg_context['candidates'])}")
        if kg_context and kg_context.get('matched_features'):
            findings.append(f"KG匹配特征参考: {', '.join(kg_context['matched_features'])}")
        
        # 分析自身免疫指标
        ana = labs.get('ANA')
        ama_m2 = labs.get('AMA_M2')
        igg4 = labs.get('IgG4')
        
        if ama_m2 and ama_m2 > 0:
            findings.append("AMA-M2阳性，高度提示原发性胆汁性胆管炎(PBC)")
            differential_diagnosis.append({
                "disease": "原发性胆汁性胆管炎(PBC)",
                "confidence": 0.88,
                "supporting_evidence": ["AMA-M2阳性"],
                "opposing_evidence": [],
                "guidelines": ["EASL 2017 PBC诊疗指南"]
            })
        
        if igg4 and igg4 > 135:
            findings.append("IgG4升高，需鉴别IgG4相关疾病、自身免疫性胰腺炎")
            differential_diagnosis.append({
                "disease": "IgG4相关疾病",
                "confidence": 0.75,
                "supporting_evidence": [f"IgG4={igg4} mg/dL"],
                "opposing_evidence": [],
                "guidelines": []
            })
        
        # 分析关节症状
        joint_symptoms = symptoms.get('joint_pain', False) or symptoms.get('arthritis', False)
        if joint_symptoms:
            findings.append("关节症状提示系统性自身免疫病可能")
        
        # 分析皮肤症状
        skin_rash = symptoms.get('skin_rash', False)
        if skin_rash:
            findings.append("皮疹需鉴别自身免疫性皮肤病")
        
        # 生成风湿专科观点
        if not differential_diagnosis:
            differential_diagnosis.append({
                "disease": "自身免疫性疾病待鉴别",
                "confidence": 0.5,
                "supporting_evidence": findings[:3] if findings else ["需要自身抗体检测"],
                "opposing_evidence": [],
                "guidelines": []
            })
        
        return self._create_response(
            success=True,
            data={
                "specialty": self.specialty,
                "findings": findings,
                "differential_diagnosis": differential_diagnosis,
                "perspective": "风湿专科视角",
                "bias_warning": self.bias_description,
                "recommended_tests": [
                    "自身抗体全套(ANA, AMA, SMA, LKM)",
                    "免疫球蛋白(IgG, IgA, IgM, IgG4)",
                    "补体C3/C4",
                    "类风湿因子(RF)",
                    "抗CCP抗体"
                ]
            },
            metadata={
                "agent_type": "specialist",
                "specialty": self.specialty,
                "bias": self.bias_description
            }
        )
