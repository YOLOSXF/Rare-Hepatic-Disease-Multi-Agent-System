"""
MDT Manager (多专科团队管理器)

负责动态组建 MDT 团队，协调专科 Agent 的并行分析。
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class MDTTeam:
    """MDT 团队"""
    members: List[Any] = field(default_factory=list)
    team_specialties: List[str] = field(default_factory=list)


class MDTManager:
    """
    MDT 团队管理器
    
    功能：
    1. 根据患者数据动态选择相关专科 Agent
    2. 组建 MDT 团队
    3. 协调团队并行分析
    """
    
    def __init__(self, agent_pool: Dict[str, Any]):
        self.agent_pool = agent_pool
    
    def assemble_team(self, patient_data: Dict[str, Any]) -> MDTTeam:
        """
        根据患者数据动态组建 MDT 团队
        
        策略：
        - 所有患者都包含肝病专科（因为是肝病诊断系统）
        - 有神经系统症状 → 加入神经专科
        - 有自身免疫指标异常 → 加入风湿专科
        - 有血液学异常 → 加入血液专科
        """
        team = MDTTeam()
        
        # 默认包含肝病专科
        if 'HepatologistAgent' in self.agent_pool:
            team.members.append(self.agent_pool['HepatologistAgent'])
            team.team_specialties.append('hepatology')
        
        symptoms = patient_data.get('symptoms', {})
        labs = patient_data.get('labs', {})
        
        # 神经系统症状 → 神经专科
        neuro_symptoms = ['tremor', 'dysarthria', 'ataxia', 'confusion']
        if any(symptoms.get(s) for s in neuro_symptoms):
            if 'NeurologyAgent' in self.agent_pool:
                team.members.append(self.agent_pool['NeurologyAgent'])
                team.team_specialties.append('neurology')
        
        # 自身免疫指标 → 风湿专科
        autoimmune_markers = ['ANA', 'AMA_M2', 'IgG4']
        if any(labs.get(m) for m in autoimmune_markers):
            if 'RheumatologyAgent' in self.agent_pool:
                team.members.append(self.agent_pool['RheumatologyAgent'])
                team.team_specialties.append('rheumatology')
        
        # 血液学异常 → 血液专科
        blood_abnormalities = ['Hb', 'PLT', 'Ferritin']
        if any(labs.get(m) for m in blood_abnormalities):
            if 'HematologyAgent' in self.agent_pool:
                team.members.append(self.agent_pool['HematologyAgent'])
                team.team_specialties.append('hematology')
        
        return team
    
    async def execute_team_analysis(
        self,
        team: MDTTeam,
        patient_data: Dict[str, Any]
    ) -> List[Dict]:
        """
        执行团队并行分析
        
        Args:
            team: MDT 团队
            patient_data: 患者数据
            
        Returns:
            List[Dict]: 各专科分析结果
        """
        import asyncio
        
        tasks = []
        for agent in team.members:
            input_data = {
                'patient_data': patient_data,
                'context': {},
            }
            tasks.append(agent.execute(input_data))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        output = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                continue
            if result and result.success:
                output.append({
                    'specialty': team.team_specialties[i],
                    'data': result.data,
                })
        
        return output
