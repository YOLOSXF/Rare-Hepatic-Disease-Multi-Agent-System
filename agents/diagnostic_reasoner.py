"""
诊断推理 Agent
负责整合多源信息，生成鉴别诊断列表
"""

from typing import Dict, List, Optional, Any
from loguru import logger

from .base_agent import BaseAgent, AgentConfig, AgentResponse


class DiagnosticReasonerConfig(AgentConfig):
    name: str = "diagnostic_reasoner"
    max_differential_diagnoses: int = 5
    confidence_threshold: float = 0.6


class DiagnosticReasonerAgent(BaseAgent):
    """
    诊断推理 Agent
    
    功能：
    1. 整合病史、检验、影像信息
    2. 生成鉴别诊断列表
    3. 评估各诊断的可能性
    """
    
    def __init__(self, config: Optional[DiagnosticReasonerConfig] = None):
        super().__init__(config or DiagnosticReasonerConfig())
        self.config: DiagnosticReasonerConfig = config or DiagnosticReasonerConfig()
    
    @property
    def name(self) -> str:
        return "diagnostic_reasoner"
    
    async def execute(self, input_data: Dict[str, Any]) -> AgentResponse:
        """执行诊断推理"""
        try:
            collected_data = input_data.get('collected_data', {})
            
            # 生成鉴别诊断
            differential_diagnosis = self._generate_differential_diagnosis(collected_data)
            
            # 排序
            differential_diagnosis.sort(key=lambda x: x.get('confidence', 0), reverse=True)
            
            # 截断
            differential_diagnosis = differential_diagnosis[:self.config.max_differential_diagnoses]
            
            result = {
                'differential_diagnosis': differential_diagnosis,
                'reasoning_process': self._document_reasoning(differential_diagnosis)
            }
            
            return self._create_response(success=True, data=result)
            
        except Exception as e:
            logger.error(f"Diagnostic reasoning failed: {e}")
            return self._create_response(success=False, error=str(e))
    
    def _generate_differential_diagnosis(self, collected_data: Dict) -> List[Dict]:
        """生成鉴别诊断列表"""
        diagnoses = []
        
        # 基于病史线索
        history = collected_data.get('history', {})
        if isinstance(history, dict):
            rare_flags = history.get('rare_disease_flags', [])
            if isinstance(rare_flags, list):
                for flag in rare_flags:
                    if isinstance(flag, dict):
                        diagnoses.append({
                            'disease': flag.get('disease', 'Unknown'),
                            'confidence': 0.6,
                            'supporting_evidence': flag.get('flags_found', []),
                            'source': 'history_flags'
                        })
        
        # 基于检验线索
        labs = collected_data.get('labs', {})
        if isinstance(labs, dict):
            rare_clues = labs.get('rare_disease_clues', [])
            if isinstance(rare_clues, list):
                for clue in rare_clues:
                    if isinstance(clue, dict):
                        disease = clue.get('disease', 'Unknown')
                        finding = clue.get('finding', 'Unknown finding')
                        existing = next((d for d in diagnoses if d['disease'] == disease), None)
                        if existing:
                            existing['confidence'] += 0.2
                            # supporting_evidence 应该是列表
                            if isinstance(existing['supporting_evidence'], list):
                                existing['supporting_evidence'].extend(clue.get('next_steps', []))
                        else:
                            diagnoses.append({
                                'disease': disease,
                                'confidence': 0.5,
                                'supporting_evidence': [finding] if isinstance(finding, str) else [],
                                'source': 'lab_clues'
                            })
        
        # 如果没有罕见病线索，基于常见症状生成诊断
        if not diagnoses:
            history_data = collected_data.get('history', {})
            if isinstance(history_data, dict):
                hpi = history_data.get('history_of_present_illness', {})
                if isinstance(hpi, dict) and hpi.get('jaundice'):
                    diagnoses.append({
                        'disease': 'Hepatitis',
                        'confidence': 0.4,
                        'supporting_evidence': ['黄疸'],
                        'source': 'symptom_pattern'
                    })
        
        return diagnoses
    
    def _document_reasoning(self, diagnoses: List[Dict]) -> str:
        """记录推理过程"""
        if not diagnoses:
            return "无明确诊断"
        
        top = diagnoses[0]
        return f"基于现有证据，最可能的诊断是{top['disease']}，置信度{top['confidence']:.2f}"
