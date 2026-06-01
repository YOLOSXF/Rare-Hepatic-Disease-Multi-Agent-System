"""
辩论协同与共识提取

基于 FIPA-ACL 精简协议实现多专科 Agent 的对抗辩论，提取共识诊断。
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum


class MessageType(Enum):
    """FIPA-ACL 消息类型"""
    PROPOSE = "propose"      # 提出诊断假设
    CFP = "cfp"             # 征集提案
    REJECT = "reject"       # 拒绝提案
    ACCEPT = "accept"       # 接受提案
    INFORM = "inform"       # 通知信息
    QUERY = "query"         # 查询信息
    AGREEMENT = "agreement" # 达成共识


@dataclass
class DebateMessage:
    """辩论消息"""
    message_type: MessageType
    sender: str
    content: str
    evidence: List[str] = field(default_factory=list)
    target_hypothesis: str = ""


@dataclass
class DebateRound:
    """辩论轮次"""
    round_number: int
    messages: List[DebateMessage]
    round_summary: str


@dataclass
class DebateResult:
    """辩论结果"""
    consensus_diagnosis: Optional[str]
    confidence: float
    consensus_points: List[str]
    disagreements: List[str]
    all_perspectives: List[Dict]
    debate_log: List[DebateRound]


class DebateMediator:
    """
    辩论协调器
    
    功能：
    1. 组织多轮对抗辩论
    2. 提取共识诊断
    3. 标记分歧点
    4. 记录完整辩论过程
    """
    
    def __init__(self, max_rounds: int = 3):
        self.max_rounds = max_rounds
    
    async def moderate_debate(
        self,
        specialist_results: List[Dict],
        patient_data: Dict[str, Any]
    ) -> DebateResult:
        """
        主持辩论
        
        Args:
            specialist_results: 各专科 Agent 的分析结果
            patient_data: 患者数据
            
        Returns:
            DebateResult: 辩论结果
        """
        debate_log = []
        all_perspectives = []
        
        # 第一轮：各专科提出初始观点
        round1_messages = []
        for result in specialist_results:
            if result.get('success') is False:
                continue
            
            data = result.get('data', {})
            specialty = data.get('specialty', 'unknown')
            diagnoses = data.get('differential_diagnosis', [])
            
            for diag in diagnoses[:2]:  # 每个专科最多提出2个假设
                msg = DebateMessage(
                    message_type=MessageType.PROPOSE,
                    sender=specialty,
                    content=f"提出诊断：{diag.get('disease', '')}",
                    evidence=diag.get('supporting_evidence', []),
                    target_hypothesis=diag.get('disease', '')
                )
                round1_messages.append(msg)
                
                all_perspectives.append({
                    "specialty": specialty,
                    "hypothesis": diag.get('disease', ''),
                    "confidence": diag.get('confidence', 0),
                    "evidence": diag.get('supporting_evidence', []),
                    "bias": data.get('bias_warning', '')
                })
        
        debate_log.append(DebateRound(
            round_number=1,
            messages=round1_messages,
            round_summary="各专科提出初始诊断假设"
        ))
        
        # 第二轮：交叉质证
        round2_messages = []
        hypotheses = list(set([p["hypothesis"] for p in all_perspectives]))
        
        for hypo in hypotheses:
            supporters = [p for p in all_perspectives if p["hypothesis"] == hypo]
            if len(supporters) >= 2:
                # 共识形成
                msg = DebateMessage(
                    message_type=MessageType.AGREEMENT,
                    sender="debate_mediator",
                    content=f"共识：{hypo} 获得多个专科支持",
                    evidence=[e for s in supporters for e in s["evidence"]],
                    target_hypothesis=hypo
                )
                round2_messages.append(msg)
            else:
                # 标记分歧
                msg = DebateMessage(
                    message_type=MessageType.QUERY,
                    sender="debate_mediator",
                    content=f"分歧：{hypo} 仅获得单个专科支持，需要更多证据",
                    evidence=supporters[0]["evidence"] if supporters else [],
                    target_hypothesis=hypo
                )
                round2_messages.append(msg)
        
        debate_log.append(DebateRound(
            round_number=2,
            messages=round2_messages,
            round_summary="交叉质证与共识识别"
        ))
        
        # 提取共识
        consensus_points = []
        disagreements = []
        
        for hypo in hypotheses:
            supporters = [p for p in all_perspectives if p["hypothesis"] == hypo]
            if len(supporters) >= 2:
                avg_conf = sum([s["confidence"] for s in supporters]) / len(supporters)
                consensus_points.append(f"{hypo} (置信度: {avg_conf:.2f})")
            else:
                disagreements.append(f"{hypo} (仅{supporters[0]['specialty']}支持)")
        
        # 确定最终共识诊断
        consensus_diagnosis = None
        confidence = 0.0
        
        if consensus_points:
            # 选择支持专科最多、平均置信度最高的
            best_hypo = max(hypotheses, key=lambda h: len(
                [p for p in all_perspectives if p["hypothesis"] == h]
            ))
            supporters = [p for p in all_perspectives if p["hypothesis"] == best_hypo]
            confidence = sum([s["confidence"] for s in supporters]) / len(supporters)
            consensus_diagnosis = best_hypo
        
        return DebateResult(
            consensus_diagnosis=consensus_diagnosis,
            confidence=confidence,
            consensus_points=consensus_points,
            disagreements=disagreements,
            all_perspectives=all_perspectives,
            debate_log=debate_log
        )
