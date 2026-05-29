"""
肝病专科 Agent

专注于肝脏疾病的诊断与鉴别，具有肝病专科的认知视角和诊断偏误。
"""

from typing import Any, Dict, List
from agents.base_agent import BaseAgent, AgentConfig, AgentResponse


class HepatologistAgent(BaseAgent):
    """
    肝病专科 Agent
    
    认知视角：从肝脏病理生理角度出发，关注肝功能指标、影像学表现、肝病特异性标志物
    认知偏误：可能过度关注肝损伤指标，忽视肝外表现（如神经系统、风湿系统症状）
    """
    
    def __init__(self, config: AgentConfig = None):
        super().__init__(config or AgentConfig(name="Hepatologist"))
        self.specialty = "hepatology"
        self.bias_description = "倾向于从肝脏本身解释所有症状，可能忽视系统性疾病的肝外表现"
    
    @property
    def name(self) -> str:
        return "HepatologistAgent"
    
    async def execute(self, input_data: Dict[str, Any]) -> AgentResponse:
        """
        执行肝病专科分析
        
        Args:
            input_data: 包含 patient_data 和 context 的字典
            
        Returns:
            AgentResponse: 包含肝病专科诊断观点
        """
        patient_data = input_data.get('patient_data', {})
        
        # 提取肝病相关指标
        labs = patient_data.get('labs', {})
        symptoms = patient_data.get('symptoms', {})
        imaging = patient_data.get('ultrasound', {})
        
        # 肝病专科分析逻辑
        findings = []
        differential_diagnosis = []
        
        # 分析肝功能指标
        alt = labs.get('ALT', labs.get('Alt'))
        ast = labs.get('AST', labs.get('Ast'))
        tbil = labs.get('TBIL', labs.get('TBil'))
        dbil = labs.get('DBIL', labs.get('DBil'))
        albumin = labs.get('albumin', labs.get('Albumin'))
        
        if alt and alt > 40:
            findings.append(f"ALT升高 ({alt} U/L)，提示肝细胞损伤")
        if ast and ast > 40:
            findings.append(f"AST升高 ({ast} U/L)，提示肝细胞损伤或线粒体损伤")
        if tbil and tbil > 20.5:
            findings.append(f"总胆红素升高 ({tbil} μmol/L)，提示胆汁淤积或溶血")
        if albumin and albumin < 35:
            findings.append(f"白蛋白降低 ({albumin} g/L)，提示肝脏合成功能受损")
        
        # 分析肝病特异性指标
        ceruloplasmin = labs.get('ceruloplasmin', labs.get('Ceruloplasmin'))
        if ceruloplasmin is not None:
            if ceruloplasmin < 0.1:
                findings.append("铜蓝蛋白显著降低，高度提示Wilson病")
                differential_diagnosis.append({
                    "disease": "Wilson病",
                    "confidence": 0.85,
                    "supporting_evidence": ["铜蓝蛋白<0.1 g/L", "肝病表现"],
                    "opposing_evidence": [],
                    "guidelines": ["AASLD 2019 Wilson病诊疗指南"]
                })
        
        # 分析影像学
        imaging_findings = imaging.get('findings', '')
        if imaging_findings:
            findings.append(f"影像学表现: {imaging_findings}")
        
        # 生成肝病专科观点
        if not differential_diagnosis:
            differential_diagnosis.append({
                "disease": "待鉴别肝病",
                "confidence": 0.5,
                "supporting_evidence": findings[:3] if findings else ["需要进一步检查"],
                "opposing_evidence": [],
                "guidelines": []
            })
        
        return self._create_response(
            success=True,
            data={
                "specialty": self.specialty,
                "findings": findings,
                "differential_diagnosis": differential_diagnosis,
                "perspective": "肝病专科视角",
                "bias_warning": self.bias_description,
                "recommended_tests": [
                    "肝功能全套",
                    "凝血功能",
                    "肝脏弹性成像(FibroScan)",
                    "自身免疫性肝病抗体谱"
                ]
            },
            metadata={
                "agent_type": "specialist",
                "specialty": self.specialty,
                "bias": self.bias_description
            }
        )
