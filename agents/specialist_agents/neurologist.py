"""
神经专科 Agent

专注于神经系统疾病的诊断与鉴别，具有神经专科的认知视角和诊断偏误。
"""

from typing import Any, Dict, List, Optional
from agents.base_agent import BaseAgent, AgentConfig, AgentResponse


class NeurologistAgent(BaseAgent):
    """
    神经专科 Agent
    
    认知视角：从神经系统病理生理角度出发，关注神经症状、体征、神经影像学
    认知偏误：可能过度关注神经系统表现，忽视肝脏等内脏器官的原发性病变
    """
    
    def __init__(self, config: AgentConfig = None):
        super().__init__(config or AgentConfig(name="Neurologist"))
        self.specialty = "neurology"
        self.bias_description = "倾向于从神经系统疾病解释症状，可能忽视代谢性/中毒性肝病的神经表现"
    
    @property
    def name(self) -> str:
        return "NeurologistAgent"
    
    async def execute(self, input_data: Dict[str, Any], kg_context: Optional[Dict] = None) -> AgentResponse:
        """执行神经专科分析
        
        Args:
            input_data: 包含 patient_data 和 context 的字典
            kg_context: 知识图谱上下文 (candidates, matched_features, differentials)
        """
        patient_data = input_data.get('patient_data', {})
        context = input_data.get('context', {})
        if kg_context is None:
            kg_context = context.get('kg_context')
        
        symptoms = patient_data.get('symptoms', {})
        chief_complaint = patient_data.get('chief_complaint', '')
        history = patient_data.get('history', {})
        
        findings = []
        differential_diagnosis = []
        
        if kg_context and kg_context.get('candidates'):
            findings.append(f"KG候选疾病参考: {', '.join(kg_context['candidates'])}")
        if kg_context and kg_context.get('matched_features'):
            findings.append(f"KG匹配特征参考: {', '.join(kg_context['matched_features'])}")
        
        # 分析神经系统症状
        neurological_symptoms = []
        if symptoms.get('tremor') or '震颤' in chief_complaint:
            neurological_symptoms.append('震颤')
            findings.append("存在震颤症状，需鉴别：Wilson病、肝性脑病、帕金森综合征")
        if symptoms.get('dysarthria') or '构音障碍' in chief_complaint:
            neurological_symptoms.append('构音障碍')
            findings.append("构音障碍提示锥体外系或小脑受累")
        if symptoms.get('ataxia') or '共济失调' in chief_complaint:
            neurological_symptoms.append('共济失调')
            findings.append("共济失调提示小脑或前庭系统病变")
        if symptoms.get('confusion') or '意识模糊' in chief_complaint:
            neurological_symptoms.append('意识障碍')
            findings.append("意识障碍需排除代谢性脑病（肝性脑病）")
        
        # 分析眼部症状（Kayser-Fleischer环）
        eye_exam = patient_data.get('eye_exam', {})
        if eye_exam.get('kf_ring') or symptoms.get('kf_ring'):
            findings.append("Kayser-Fleischer环阳性，高度提示Wilson病")
            differential_diagnosis.append({
                "disease": "Wilson病",
                "confidence": 0.9,
                "supporting_evidence": ["K-F环阳性", "神经系统症状"] + neurological_symptoms,
                "opposing_evidence": [],
                "guidelines": ["AASLD 2019 Wilson病诊疗指南", "EFNS 2012 肝豆状核变性指南"]
            })
        
        # 分析认知功能
        cognitive_changes = history.get('cognitive_changes', False)
        if cognitive_changes:
            findings.append("认知功能改变，需鉴别代谢性脑病、神经退行性疾病")
        
        # 生成神经专科观点
        if not differential_diagnosis and neurological_symptoms:
            differential_diagnosis.append({
                "disease": "神经系统疾病待鉴别",
                "confidence": 0.6,
                "supporting_evidence": neurological_symptoms,
                "opposing_evidence": [],
                "guidelines": []
            })
        
        return self._create_response(
            success=True,
            data={
                "specialty": self.specialty,
                "findings": findings,
                "differential_diagnosis": differential_diagnosis,
                "perspective": "神经专科视角",
                "bias_warning": self.bias_description,
                "recommended_tests": [
                    "神经系统查体",
                    "头颅MRI",
                    "脑电图",
                    "血清铜蓝蛋白+24h尿铜",
                    "眼科裂隙灯检查(K-F环)"
                ]
            },
            metadata={
                "agent_type": "specialist",
                "specialty": self.specialty,
                "bias": self.bias_description
            }
        )
