"""
血液专科 Agent

专注于血液系统疾病的诊断与鉴别，具有血液专科的认知视角和诊断偏误。
"""

from typing import Any, Dict, List, Optional
from agents.base_agent import BaseAgent, AgentConfig, AgentResponse


class HematologistAgent(BaseAgent):
    """
    血液专科 Agent
    
    认知视角：从血液系统病理生理角度出发，关注血常规、凝血功能、骨髓检查
    认知偏误：可能过度关注血液学异常，忽视肝脏等实体器官的病变
    """
    
    def __init__(self, config: AgentConfig = None):
        super().__init__(config or AgentConfig(name="Hematologist"))
        self.specialty = "hematology"
        self.bias_description = "倾向于从血液系统疾病解释异常，可能忽视肝病导致的继发性血液学改变"
    
    @property
    def name(self) -> str:
        return "HematologistAgent"
    
    async def execute(self, input_data: Dict[str, Any], kg_context: Optional[Dict] = None) -> AgentResponse:
        """执行血液专科分析
        
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
        
        findings = []
        differential_diagnosis = []
        
        if kg_context and kg_context.get('candidates'):
            findings.append(f"KG候选疾病参考: {', '.join(kg_context['candidates'])}")
        if kg_context and kg_context.get('matched_features'):
            findings.append(f"KG匹配特征参考: {', '.join(kg_context['matched_features'])}")
        
        # 分析血常规指标
        hemoglobin = labs.get('Hb')
        platelet = labs.get('PLT')
        wbc = labs.get('WBC')
        
        if hemoglobin and hemoglobin < 120:
            findings.append(f"血红蛋白降低 ({hemoglobin} g/L)，提示贫血")
        if platelet and platelet < 100:
            findings.append(f"血小板减少 ({platelet} ×10^9/L)，需鉴别脾功能亢进、血液系统疾病")
        if wbc and wbc < 4.0:
            findings.append(f"白细胞减少 ({wbc} ×10^9/L)")
        
        # 分析凝血功能
        pt = labs.get('PT')
        inr = labs.get('INR')
        if pt and pt > 14:
            findings.append(f"凝血酶原时间延长 ({pt} s)，提示肝脏合成功能受损或凝血因子缺乏")
        if inr and inr > 1.2:
            findings.append(f"INR升高 ({inr})，提示凝血功能障碍")
        
        # 分析铁代谢指标
        ferritin = labs.get('Ferritin')
        iron = labs.get('Iron')
        tibc = labs.get('TIBC')
        
        if ferritin is not None:
            if ferritin > 1000:
                findings.append(f"铁蛋白显著升高 ({ferritin} ng/mL)，高度提示血色病")
                differential_diagnosis.append({
                    "disease": "遗传性血色病",
                    "confidence": 0.82,
                    "supporting_evidence": [f"铁蛋白>{ferritin} ng/mL", "肝病表现"],
                    "opposing_evidence": [],
                    "guidelines": ["AASLD 2019 血色病诊疗指南"]
                })
            elif ferritin < 30:
                findings.append(f"铁蛋白降低 ({ferritin} ng/mL)，提示缺铁性贫血")
        
        # 分析溶血指标
        ldh = labs.get('LDH')
        haptoglobin = labs.get('Haptoglobin')
        if ldh and ldh > 250:
            findings.append("LDH升高，提示溶血或组织损伤")
        if haptoglobin and haptoglobin < 0.3:
            findings.append("结合珠蛋白降低，提示溶血")
        
        # 生成血液专科观点
        if not differential_diagnosis:
            differential_diagnosis.append({
                "disease": "血液系统疾病待鉴别",
                "confidence": 0.5,
                "supporting_evidence": findings[:3] if findings else ["需要血液学检查"],
                "opposing_evidence": [],
                "guidelines": []
            })
        
        return self._create_response(
            success=True,
            data={
                "specialty": self.specialty,
                "findings": findings,
                "differential_diagnosis": differential_diagnosis,
                "perspective": "血液专科视角",
                "bias_warning": self.bias_description,
                "recommended_tests": [
                    "血常规+网织红细胞",
                    "凝血功能全套",
                    "铁代谢全套(血清铁、铁蛋白、总铁结合力、转铁蛋白饱和度)",
                    "溶血全套(LDH、结合珠蛋白、游离血红蛋白)",
                    "骨髓穿刺(必要时)"
                ]
            },
            metadata={
                "agent_type": "specialist",
                "specialty": self.specialty,
                "bias": self.bias_description
            }
        )
