"""
主治医师 Agent (MDT 主持)

负责协调多专科 Agent 的对抗辩论，整合各专科观点，形成统一诊断结论。
作为 MDT 会议的主持人，确保辩论过程有序进行，促进共识达成。
"""

from typing import Any, Dict, List, Optional
from agents.base_agent import BaseAgent, AgentConfig, AgentResponse


class AttendingAgent(BaseAgent):
    """
    主治医师 Agent (MDT 主持)
    
    职责：
    1. 组织 MDT 会议，协调各专科 Agent
    2. 整合各专科观点，识别共识与分歧
    3. 引导辩论方向，确保覆盖关键鉴别点
    4. 最终诊断决策（在共识基础上）
    
    特点：
    - 不带有特定专科偏误
    - 保持中立，客观评估各方证据
    - 关注患者整体状况
    """
    
    def __init__(self, config: AgentConfig = None):
        super().__init__(config or AgentConfig(name="Attending"))
        self.role = "mdt_chair"
        self.responsibilities = [
            "组织MDT会议",
            "整合专科观点",
            "识别诊断共识",
            "标记关键分歧",
            "制定诊疗计划"
        ]
    
    @property
    def name(self) -> str:
        return "AttendingAgent"
    
    async def execute(self, input_data: Dict[str, Any]) -> AgentResponse:
        """
        执行 MDT 主持任务
        
        Args:
            input_data: 包含 specialist_responses 和 patient_data 的字典
            
        Returns:
            AgentResponse: 包含整合后的 MDT 结论
        """
        specialist_responses = input_data.get('specialist_responses', [])
        patient_data = input_data.get('patient_data', {})
        
        # 整合各专科观点
        integrated_findings = []
        all_diagnoses = []
        consensus_points = []
        disagreements = []
        
        # 收集各专科发现
        for response in specialist_responses:
            if not response.get('success'):
                continue
                
            data = response.get('data', {})
            specialty = data.get('specialty', 'unknown')
            findings = data.get('findings', [])
            diagnoses = data.get('differential_diagnosis', [])
            
            integrated_findings.append({
                "specialty": specialty,
                "findings": findings,
                "perspective": data.get('perspective', '')
            })
            
            for diag in diagnoses:
                all_diagnoses.append({
                    **diag,
                    "source_specialty": specialty
                })
        
        # 识别共识（多个专科都支持的诊断）
        diagnosis_votes = {}
        for diag in all_diagnoses:
            disease = diag.get('disease', '')
            if disease not in diagnosis_votes:
                diagnosis_votes[disease] = {
                    "count": 0,
                    "specialties": [],
                    "confidences": [],
                    "evidence": []
                }
            diagnosis_votes[disease]["count"] += 1
            diagnosis_votes[disease]["specialties"].append(diag.get('source_specialty', ''))
            diagnosis_votes[disease]["confidences"].append(diag.get('confidence', 0))
            diagnosis_votes[disease]["evidence"].extend(diag.get('supporting_evidence', []))
        
        # 找出共识诊断（≥2个专科支持）
        for disease, votes in diagnosis_votes.items():
            if votes["count"] >= 2:
                avg_confidence = sum(votes["confidences"]) / len(votes["confidences"])
                consensus_points.append({
                    "disease": disease,
                    "supporting_specialties": votes["specialties"],
                    "avg_confidence": avg_confidence,
                    "evidence": list(set(votes["evidence"]))
                })
        
        # 识别分歧（只有一个专科支持的诊断）
        for disease, votes in diagnosis_votes.items():
            if votes["count"] == 1:
                disagreements.append({
                    "disease": disease,
                    "supporting_specialty": votes["specialties"][0],
                    "confidence": votes["confidences"][0],
                    "evidence": votes["evidence"]
                })
        
        # 按置信度排序
        consensus_points.sort(key=lambda x: x["avg_confidence"], reverse=True)
        disagreements.sort(key=lambda x: x["confidence"], reverse=True)
        
        # 生成 MDT 结论
        mdt_conclusion = {
            "consensus_diagnosis": consensus_points[0] if consensus_points else None,
            "consensus_points": consensus_points,
            "disagreements": disagreements,
            "integrated_findings": integrated_findings,
            "recommendation": self._generate_recommendation(consensus_points, disagreements)
        }
        
        return self._create_response(
            success=True,
            data=mdt_conclusion,
            metadata={
                "agent_type": "attending",
                "role": self.role,
                "specialist_count": len(specialist_responses)
            }
        )
    
    def _generate_recommendation(
        self,
        consensus_points: List[Dict],
        disagreements: List[Dict]
    ) -> str:
        """生成 MDT 建议"""
        if consensus_points:
            top = consensus_points[0]
            return (
                f"MDT共识诊断：{top['disease']} "
                f"(置信度：{top['avg_confidence']:.2f}, "
                f"支持专科：{', '.join(top['supporting_specialties'])})"
            )
        elif disagreements:
            return (
                "MDT未达成共识，主要分歧：" + 
                "; ".join([d['disease'] for d in disagreements[:3]])
            )
        else:
            return "MDT未能形成明确诊断，建议进一步检查"
