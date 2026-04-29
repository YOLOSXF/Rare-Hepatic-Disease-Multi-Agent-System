"""
LangGraph 对抗推理编排器 (v3.0 - 原生 StateGraph 实现)

利用 LangGraph 原生特性：
- StateGraph 状态图构建
- MemorySaver checkpoint 持久化
- Conditional edges 条件边实现证伪回退 / HITL 挂起 / 指南守门打回
- Send API 实现专科 Agent 并行执行
- interrupt 实现真正的人机交互挂起

架构对应：
- L1: preprocessing → data_assessment
- L2: triage → [条件分支]
- L3: memory_retrieval → mdt_team_assemble → mdt_debate → graph_update → falsification → hitl_gap_assess → guideline_verify
- L4: 通过 tools/ 和 knowledge_base/ 提供外部知识
- L5: 报告生成
"""

from typing import Dict, Any, Optional, List, Callable
from loguru import logger

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt

from .state_definition import (
    DiagnosticState, Question, FalsificationEntry, GuidelineCheckEntry,
    FinalReport, CommonDiagnosisReport, TriageRecommendationReport, MDTFinalReport,
)
from .mdt_manager import MDTManager


class LangGraphDiagnosticGraph:
    """
    LangGraph 对抗推理编排器 (v3.0)
    
    完整五层分层诊断图，利用 LangGraph 原生特性：
    
    L1: preprocessing → data_assessment
    L2: triage → [条件分支]
        ├─ common_fast_path → common_disease_report（常见病确诊报告）
        ├─ rare_deep_path → L3 → mdt_final_report（MDT深度诊断报告）
        └─ uncertain_fallback → triage_examination_report（补检开单建议）
    L3: memory_retrieval → mdt_team_assemble → [SEND并行] mdt_debate
       → graph_update → falsification → [条件边: 证伪回退 mdt_debate]
       → hitl_gap_assess → [条件边: 缺证 interrupt]
       → guideline_verify → [条件边: 不合规打回 mdt_debate]
       → referral_decision → mdt_final_report
    L5: 三个专属报告节点，职责分离
        - common_disease_report: L2 常见病确诊报告
        - triage_examination_report: L2 补检开单建议
        - mdt_final_report: L3 MDT 终局深度诊断报告
    """
    
    def __init__(
        self,
        specialist_agents: Optional[Dict[str, Any]] = None,
        mdt_manager: Optional[Any] = None,
        debate_mediator: Optional[Any] = None,
        falsification_engine: Optional[Any] = None,
        gap_assessor: Optional[Any] = None,
        guideline_verifier: Optional[Any] = None,
        reference_verifier: Optional[Any] = None,
        graph_updater: Optional[Any] = None,
        memory_retriever: Optional[Any] = None,
        max_debate_rounds: int = 3,
        max_falsification_retries: int = 2,
        enable_llm_report: bool = True,
        llm_config_path: str = "config.yaml",
    ):
        self.specialist_agents = specialist_agents or {}
        self.mdt_manager = mdt_manager
        self.debate_mediator = debate_mediator
        self.falsification_engine = falsification_engine
        self.gap_assessor = gap_assessor
        self.guideline_verifier = guideline_verifier
        self.reference_verifier = reference_verifier
        self.graph_updater = graph_updater
        self.memory_retriever = memory_retriever
        
        self.max_debate_rounds = max_debate_rounds
        self.max_falsification_retries = max_falsification_retries
        
        # LLM 报告增强开关（Neuro-Symbolic AI：规则引擎定乾坤，大模型写医嘱）
        self.enable_llm_report = enable_llm_report
        self.llm_config_path = llm_config_path
        
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """构建 LangGraph StateGraph"""
        
        workflow = StateGraph(DiagnosticState)
        
        workflow.add_node("preprocessing", self._node_preprocessing)
        workflow.add_node("data_assessment", self._node_data_assessment)
        workflow.add_node("triage", self._node_triage)
        workflow.add_node("common_fast_path", self._node_common_fast_path)
        workflow.add_node("memory_retrieval", self._node_memory_retrieval)
        workflow.add_node("mdt_team_assemble", self._node_mdt_team_assemble)
        workflow.add_node("mdt_debate", self._node_mdt_debate)
        workflow.add_node("graph_update", self._node_graph_update)
        workflow.add_node("falsification", self._node_falsification)
        workflow.add_node("hitl_gap_assess", self._node_hitl_gap_assess)
        workflow.add_node("guideline_verify", self._node_guideline_verify)
        workflow.add_node("referral_decision", self._node_referral_decision)
        workflow.add_node("common_disease_report", self._node_common_disease_report)
        workflow.add_node("triage_examination_report", self._node_triage_examination_report)
        workflow.add_node("mdt_final_report", self._node_mdt_final_report)
        
        workflow.set_entry_point("preprocessing")
        
        workflow.add_edge("preprocessing", "data_assessment")

        # 统一路由：无论数据评估结果如何，都送入 Triage 接受"门诊检阅"
        # Triage 内部有闪电拦截机制，数据不足时会快速返回，不会执行重型引擎
        workflow.add_edge("data_assessment", "triage")

        # Triage 后的条件路由（三条路径，各走各的）
        workflow.add_conditional_edges(
            "triage",
            self._route_after_triage,
            {
                "common_fast_path": "common_fast_path",
                "rare_deep_path": "memory_retrieval",
                "uncertain_fallback": "triage_examination_report",  # 数据不足/不确定 → 补检开单
            },
        )
        
        workflow.add_edge("common_fast_path", "common_disease_report")
        workflow.add_edge("memory_retrieval", "mdt_team_assemble")
        workflow.add_edge("mdt_team_assemble", "mdt_debate")
        workflow.add_edge("mdt_debate", "graph_update")
        workflow.add_edge("graph_update", "falsification")
        
        workflow.add_conditional_edges(
            "falsification",
            self._route_after_falsification,
            {
                "mdt_debate": "mdt_debate",
                "hitl_gap_assess": "hitl_gap_assess",
            },
        )
        
        workflow.add_conditional_edges(
            "hitl_gap_assess",
            self._route_after_hitl,
            {
                "interrupted": END,
                "guideline_verify": "guideline_verify",
            },
        )
        
        workflow.add_conditional_edges(
            "guideline_verify",
            self._route_after_guideline,
            {
                "mdt_debate": "mdt_debate",
                "referral_decision": "referral_decision",
            },
        )
        
        workflow.add_edge("referral_decision", "mdt_final_report")
        workflow.add_edge("common_disease_report", END)
        workflow.add_edge("triage_examination_report", END)
        workflow.add_edge("mdt_final_report", END)
        
        return workflow
    
    # 注：_route_after_data_assessment 方法已弃用
    # 现在采用统一路由设计：无论数据评估结果如何，都送入 Triage
    # Triage 内部有闪电拦截机制处理数据不足的情况
    # 保留此方法代码仅供参考，如需恢复条件路由可取消注释
    """
    def _route_after_data_assessment(self, state: DiagnosticState) -> str:
        # 数据评估后路由决策（已弃用）
        from .data_assessor import DataCompletenessAssessor
        
        completeness_score = state.get('data_completeness_score', 0)
        patient_data = state.get('patient_data', {})
        SUFFICIENT_THRESHOLD = 0.6
        
        assessor = DataCompletenessAssessor()
        has_rare_clue, rare_clues = assessor.check_rare_disease_clue(patient_data)
        
        if completeness_score >= SUFFICIENT_THRESHOLD:
            return "sufficient"
        if has_rare_clue:
            return "insufficient_with_rare_clue"
        return "insufficient_no_clue"
    """

    def _route_after_triage(self, state: DiagnosticState) -> str:
        """
        分诊后路由

        根据 Triage 结果决定下一步（三条专属路径）：
        - common_fast_path: 常见病快速通道 → common_disease_report（确诊报告）
        - rare_deep_path: 罕见病预警 → 进入 L3 深度诊断 → mdt_final_report
        - uncertain_fallback: 不确定/数据不足 → triage_examination_report（补检开单）
        """
        triage = state.get('triage_result', {})
        path = triage.get('path', 'uncertain')
        confidence_level = triage.get('confidence_level', 'low')

        if path == 'common_fast_path':
            logger.info(f"分诊结果：常见病快速通道 (confidence={confidence_level})")
            return "common_fast_path"

        elif path == 'rare_deep_path':
            logger.warning(f"分诊结果：罕见病预警，进入L3深度诊断 (confidence={confidence_level})")
            return "rare_deep_path"

        elif path in ['uncertain', 'insufficient_data']:
            # 包括：闪电拦截、数据不足、LLM兜底不确定
            reason = triage.get('uncertainty_reason', '未知原因')
            logger.info(f"分诊结果：不确定/数据不足，生成补检建议。原因：{reason}")
            return "uncertain_fallback"

        # 默认情况
        logger.warning(f"分诊结果未知 (path={path})，默认走补检建议")
        return "uncertain_fallback"
    
    def _route_after_falsification(self, state: DiagnosticState) -> str:
        """证伪后路由：被证伪则回退重辩论"""
        retry_count = state.get('retry_count', 0)
        if retry_count >= self.max_falsification_retries:
            return "hitl_gap_assess"
        
        falsified_count = 0
        for e in state.get('falsification_log', []):
            is_falsified = getattr(e, 'falsified', False) if hasattr(e, 'falsified') else e.get('falsified', False)
            if is_falsified:
                falsified_count += 1
        
        if falsified_count > 0:
            return "mdt_debate"
        return "hitl_gap_assess"
    
    def _route_after_hitl(self, state: DiagnosticState) -> str:
        """HITL 后路由：缺证则 interrupt，否则继续"""
        hitl_status = state.get('hitl_status', 'normal')
        if hitl_status == 'interrupted':
            return "interrupted"
        return "guideline_verify"
    
    def _route_after_guideline(self, state: DiagnosticState) -> str:
        """指南守门后路由：不合规则打回重辩论"""
        check = state.get('guideline_check_result')
        if check is None:
            return "referral_decision"
        
        compliant = getattr(check, 'compliant', True) if hasattr(check, 'compliant') else check.get('compliant', True)
        if not compliant:
            return "mdt_debate"
        return "referral_decision"
    
    # ===== LLM 报告生成辅助方法 =====
    
    async def _call_llm_report(
        self,
        system_prompt: str,
        user_prompt: str,
        timeout: float = 30.0,
    ) -> Optional[Dict[str, Any]]:
        """
        调用 LLM 生成报告（带超时、JSON 解析、降级容灾）
        
        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            timeout: 超时时间（秒）
        
        Returns:
            LLM 解析后的 JSON 字典，失败返回 None
        """
        import asyncio
        import json
        import re
        
        try:
            from .llm_client import get_llm_client
            
            # 获取 LLM 客户端（temperature=0.1 保证严谨性，不需要创造力）
            client = get_llm_client(temperature=0.1, max_tokens=4000, config_path=self.llm_config_path)
            
            from langchain_core.messages import SystemMessage, HumanMessage
            
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]
            
            async def _invoke_llm():
                response = await client.ainvoke(messages)
                return response.content
            
            response_text = await asyncio.wait_for(_invoke_llm(), timeout=timeout)
            
            # 解析 JSON（可能包含在 markdown 代码块中）
            json_match = re.search(r'```(?:json)?\s*({.*?})\s*```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = response_text
            
            try:
                parsed = json.loads(json_str)
                logger.info("LLM 报告生成成功")
                return parsed
            except json.JSONDecodeError as e:
                logger.warning(f"LLM JSON 解析失败：{e}，响应内容：{json_str[:200]}...")
                return None
                
        except asyncio.TimeoutError:
            logger.warning("LLM 响应超时，降级为规则报告")
            return None
        except Exception as e:
            logger.error(f"LLM 调用失败：{e}，降级为规则报告")
            return None
    
    # ===== LangGraph Node Implementations =====
    
    async def _node_preprocessing(self, state: DiagnosticState) -> Dict[str, Any]:
        """L1: 数据预处理"""
        logger.info("=== L1: Preprocessing ===")
        
        from .preprocessor import DataPreprocessor
        preprocessor = DataPreprocessor()
        result = preprocessor.preprocess(state['patient_data'])
        
        return {'patient_data': result.standardized_data, 'current_phase': 'preprocessing'}
    
    async def _node_data_assessment(self, state: DiagnosticState) -> Dict[str, Any]:
        """L1: 数据完备性评估"""
        logger.info("=== L1: Data Assessment ===")

        from .data_assessor import DataCompletenessAssessor
        assessor = DataCompletenessAssessor()
        assessment = assessor.assess(state['patient_data'])

        return {
            'data_assessment_result': {
                'score': assessment.score,
                'level': assessment.level,
                'can_triage': assessment.can_triage,
                'missing_critical': assessment.missing_critical,
                'missing_recommended': assessment.missing_recommended,
                'recommended_actions': assessment.recommended_actions,
                'has_rare_clue': assessment.has_rare_clue,
                'rare_clues': assessment.rare_clues,
            },
            'current_phase': 'data_assessment',
        }
    
    async def _node_triage(self, state: DiagnosticState) -> Dict[str, Any]:
        """L2: 分诊（支持数据评估短路拦截）"""
        logger.info("=== L2: Triage ===")

        # 提取数据评估结果，打包传递给 Triage 引擎
        assessment = state.get('data_assessment_result', {})
        data_assessment = {
            'can_triage': assessment.get('can_triage', False),
            'has_rare_clue': assessment.get('has_rare_clue', False),
            'assessment_recommendations': assessment.get('recommended_actions', []),
        }

        logger.info(f"数据评估: can_triage={data_assessment['can_triage']}, "
                   f"has_rare_clue={data_assessment['has_rare_clue']}")

        from .triage import IntelligentTriage
        triage = IntelligentTriage()

        # 传递数据评估结果，支持内部短路拦截
        triage_result = await triage.triage(
            state['patient_data'],
            data_assessment=data_assessment
        )

        if triage_result and hasattr(triage_result, 'path'):
            path_map = {
                'common': 'common_fast_path',
                'rare': 'rare_deep_path',
                'insufficient_data': 'uncertain',  # 数据不足时跳转到 uncertain
                'uncertain': 'uncertain',
            }
            return {
                'triage_result': {
                    'path': path_map.get(triage_result.path, 'uncertain'),
                    'diagnosis': getattr(triage_result, 'diagnosis', None),
                    'confidence': getattr(triage_result, 'confidence', 0.3),
                    'confidence_level': getattr(triage_result, 'confidence_level', 'low'),
                    'is_rare_disease_alert': getattr(triage_result, 'is_rare_disease_alert', False),
                    'urgency': getattr(triage_result, 'urgency', 'routine'),
                    'recommended_tests': getattr(triage_result, 'recommended_tests', []),
                    'uncertainty_reason': getattr(triage_result, 'uncertainty_reason', None),
                },
                'current_phase': 'triage',
            }

        return {
            'triage_result': {
                'path': 'uncertain',
                'diagnosis': None,
                'confidence': 0.3,
                'confidence_level': 'low',
                'is_rare_disease_alert': False,
                'urgency': 'routine',
                'recommended_tests': [],
                'uncertainty_reason': None,
            },
            'current_phase': 'triage',
        }
    
    async def _node_common_fast_path(self, state: DiagnosticState) -> Dict[str, Any]:
        """常见病快速路径"""
        logger.info("=== Common Fast Path ===")
        return {'current_phase': 'common_fast_path'}
    
    async def _node_memory_retrieval(self, state: DiagnosticState) -> Dict[str, Any]:
        """L3: 长时记忆检索"""
        logger.info("=== L3: Memory Retrieval ===")
        
        if self.memory_retriever:
            memory_ctx = await self.memory_retriever.retrieve(state['patient_data'])
            return {
                'memory_context': {
                    'longitudinal_summary': memory_ctx.longitudinal_summary,
                    'similar_cases': memory_ctx.similar_cases,
                    'historical_trends': memory_ctx.historical_trends,
                    'last_visit_summary': memory_ctx.last_visit_summary,
                },
                'current_phase': 'memory_retrieval',
            }
        
        return {'memory_context': {'similar_cases': [], 'historical_trends': {}}, 'current_phase': 'memory_retrieval'}
    
    async def _node_mdt_team_assemble(self, state: DiagnosticState) -> Dict[str, Any]:
        """L3: MDT 团队组建"""
        logger.info("=== L3: MDT Team Assembly ===")
        
        team_size = 1
        team_specialties = []
        
        if self.mdt_manager:
            team = self.mdt_manager.assemble_team(state['patient_data'])
            team_size = len(team.members)
            team_specialties = team.team_specialties
            logger.info(f"MDT团队组建完成: {team_specialties} ({team_size}个专科)")
        else:
            # 如果没有MDT管理器，使用所有可用的专科Agent
            team_size = len(self.specialist_agents)
            team_specialties = list(self.specialist_agents.keys())
        
        return {
            'knowledge_graph_weights': {
                'mdt_team_size': float(team_size),
                'team_specialties': team_specialties,
            },
            'current_phase': 'mdt_team_assemble',
        }
    
    async def _node_mdt_debate(self, state: DiagnosticState) -> Dict[str, Any]:
        """L3: 多专科对抗辩论 (支持并行)"""
        logger.info("=== L3: MDT Debate ===")
        
        # 使用新的MDT架构运行专科分析
        specialist_results = await self._run_specialist_analyses(state)
        
        updates: Dict[str, Any] = {
            'current_phase': 'mdt_debate', 
            'retry_count': state.get('retry_count', 0) + 1
        }
        
        # 使用辩论协调器进行对抗辩论
        if self.debate_mediator and len(specialist_results) >= 2:
            logger.info(f"启动对抗辩论: {len(specialist_results)}个专科参与")
            debate_result = await self.debate_mediator.moderate_debate(
                specialist_results, state['patient_data']
            )
            
            updates['debate_state'] = {
                'round_number': debate_result.debate_log[-1].round_number if debate_result.debate_log else 0,
                'messages': [
                    {
                        'message_type': msg.message_type.value,
                        'sender': msg.sender,
                        'content': msg.content,
                        'evidence': msg.evidence or [],
                    }
                    for rd in debate_result.debate_log
                    for msg in rd.messages
                ],
                'consensus_points': debate_result.consensus_points,
                'disagreements': debate_result.disagreements,
                'all_perspectives': debate_result.all_perspectives,
            }
            
            updates['knowledge_graph_weights'] = {
                **state.get('knowledge_graph_weights', {}),
                'debate_consensus': debate_result.confidence,
            }
            
            if debate_result.consensus_diagnosis:
                updates['hypotheses'] = [{
                    'disease': debate_result.consensus_diagnosis,
                    'confidence': debate_result.confidence,
                    'supporting_evidence': debate_result.consensus_points,
                    'opposing_evidence': debate_result.disagreements,
                    'source': 'mdt_debate_consensus',
                    'guidelines': [],
                }]
                logger.info(f"MDT达成共识: {debate_result.consensus_diagnosis} (置信度: {debate_result.confidence:.2f})")
            else:
                logger.warning("MDT未达成共识，保留所有假设")
                # 未达成共识时，保留所有专科假设
                hyps = []
                for sr in specialist_results:
                    diagnoses = sr.get('data', {}).get('differential_diagnosis', [])
                    for diag in diagnoses[:2]:
                        hyps.append({
                            'disease': diag.get('disease', 'unknown'),
                            'confidence': diag.get('confidence', 0),
                            'supporting_evidence': diag.get('supporting_evidence', []),
                            'opposing_evidence': diag.get('opposing_evidence', []),
                            'source': sr.get('specialty', 'unknown'),
                            'guidelines': diag.get('guidelines', []),
                        })
                updates['hypotheses'] = hyps
        else:
            logger.info("辩论协调器未配置或专科数量不足，直接汇总假设")
            hyps = []
            for sr in specialist_results:
                diagnoses = sr.get('data', {}).get('differential_diagnosis', [])
                for diag in diagnoses[:2]:
                    hyps.append({
                        'disease': diag.get('disease', 'unknown'),
                        'confidence': diag.get('confidence', 0),
                        'supporting_evidence': diag.get('supporting_evidence', []),
                        'opposing_evidence': diag.get('opposing_evidence', []),
                        'source': sr.get('specialty', 'unknown'),
                        'guidelines': diag.get('guidelines', []),
                    })
            updates['hypotheses'] = hyps
        
        return updates
    
    async def _node_graph_update(self, state: DiagnosticState) -> Dict[str, Any]:
        """L3-EWAS: 图谱权重更新"""
        logger.info("=== L3: Graph Update (EWAS) ===")
        
        if self.graph_updater and state.get('debate_state'):
            class FakeDebateResult:
                pass
            fake_result = FakeDebateResult()
            debate_state = state['debate_state']
            fake_result.consensus_diagnosis = None
            fake_result.confidence = 0.8 if debate_state.get('consensus_points') else 0.0
            fake_result.all_perspectives = debate_state.get('all_perspectives', [])
            fake_result.debate_log = []
            
            new_weights = self.graph_updater.update_from_debate_result(fake_result, state['patient_data'])
            return {'knowledge_graph_weights': new_weights, 'current_phase': 'graph_update'}
        
        return {'current_phase': 'graph_update'}
    
    async def _node_falsification(self, state: DiagnosticState) -> Dict[str, Any]:
        """L3: 证伪反思"""
        logger.info("=== L3: Falsification ===")
        
        updates: Dict[str, Any] = {'current_phase': 'falsification'}
        
        if self.falsification_engine and state.get('hypotheses'):
            falsification_results = self.falsification_engine.evaluate_hypotheses(
                state['hypotheses'], state['patient_data']
            )
            
            falsification_log = []
            excluded = []
            for fr in falsification_results:
                entry = FalsificationEntry(
                    hypothesis=fr.hypothesis,
                    falsified=fr.falsified,
                    contradiction_score=fr.contradiction_score,
                    contradicting_evidence=fr.contradicting_evidence,
                    supporting_evidence=fr.supporting_evidence,
                    recommendation=fr.recommendation,
                )
                falsification_log.append(entry)
                
                if fr.falsified:
                    excluded.append(fr.hypothesis)
                    if self.graph_updater:
                        self.graph_updater.suppress_disease(fr.hypothesis)
            
            updates['falsification_log'] = falsification_log
            updates['excluded_hypotheses'] = excluded
        
        return updates
    
    async def _node_hitl_gap_assess(self, state: DiagnosticState) -> Dict[str, Any]:
        """L3: HITL 信息缺口评估 (支持 interrupt)"""
        logger.info("=== L3: HITL Gap Assessment ===")
        
        updates: Dict[str, Any] = {'current_phase': 'hitl_gap_assess'}
        
        if self.gap_assessor and state.get('hypotheses'):
            gap_result = self.gap_assessor.assess(
                state['hypotheses'], state['patient_data']
            )
            
            questions_list = [
                Question(
                    field=q.field,
                    question=q.question,
                    rationale=q.rationale,
                    priority=q.priority.value,
                    related_disease=q.related_disease,
                    recommended_test=q.expected_test,
                )
                for q in gap_result.questions
            ]
            
            if self.gap_assessor.should_interrupt(gap_result) and questions_list:
                updates['hitl_status'] = 'interrupted'
                updates['hitl_questions'] = questions_list
                
                try:
                    interrupt({
                        'hitl_questions': [
                            {
                                'field': q.field,
                                'question': q.question,
                                'rationale': q.rationale,
                                'priority': q.priority,
                                'related_disease': q.related_disease,
                                'recommended_test': q.recommended_test,
                            }
                            for q in questions_list
                        ],
                        'message': '需要补充关键检查数据以完成鉴别诊断',
                    })
                    updates['hitl_status'] = 'resumed'
                except Exception:
                    pass
            
            else:
                updates['hitl_status'] = 'normal'
                updates['hitl_questions'] = questions_list
        else:
            updates['hitl_status'] = 'normal'
        
        return updates
    
    async def _node_guideline_verify(self, state: DiagnosticState) -> Dict[str, Any]:
        """L3: 指南守门"""
        logger.info("=== L3: Guideline Verification ===")
        
        if self.guideline_verifier and state.get('hypotheses'):
            sorted_hyp = sorted(state['hypotheses'], key=lambda x: x.get('confidence', 0), reverse=True)
            if sorted_hyp:
                top = sorted_hyp[0]
                check_result = self.guideline_verifier.verify_diagnosis(
                    top['disease'], state['patient_data']
                )
                
                return {
                    'guideline_check_result': GuidelineCheckEntry(
                        diagnosis=check_result.diagnosis,
                        compliant=check_result.compliant,
                        missing_criteria=check_result.missing_criteria,
                        met_criteria=check_result.met_criteria,
                        recommendation=check_result.recommendation,
                    ),
                    'current_phase': 'guideline_verify',
                }
        
        return {'guideline_check_result': None, 'current_phase': 'guideline_verify'}
    
    async def _node_referral_decision(self, state: DiagnosticState) -> Dict[str, Any]:
        """L5: 转诊决策"""
        logger.info("=== L5: Referral Decision ===")
        
        from agents.referral_decider import ReferralDeciderAgent
        referral_agent = ReferralDeciderAgent()
        
        referral_input = {
            'patient_data': state['patient_data'],
            'triage_result': state.get('triage_result', {}),
            'hypotheses': state.get('hypotheses', []),
            'debate_state': state.get('debate_state'),
            'completeness': state.get('data_completeness_score', 0),
        }
        
        referral_result = await referral_agent.execute(referral_input)
        
        if referral_result.success:
            return {'referral_decision': referral_result.data, 'current_phase': 'referral_decision'}
        return {'referral_decision': {'referral': False, 'message': referral_result.error}, 'current_phase': 'referral_decision'}
    
    async def _node_common_disease_report(self, state: DiagnosticState) -> Dict[str, Any]:
        """L5a: 常见病确诊报告（L2 快速通道专属出口，支持 LLM 临床语言润色）"""
        logger.info("=== L5a: 生成常见病确诊报告 ===")

        triage_result = state.get('triage_result', {})
        assessment_result = state.get('data_assessment_result', {})
        patient_data = state['patient_data']

        # 规则引擎确定的硬性事实（LLM 不可篡改）
        diagnosis = triage_result.get('diagnosis', '未知')
        confidence = triage_result.get('confidence', 0)
        confidence_level = triage_result.get('confidence_level', 'low')
        referral = triage_result.get('referral_recommendation')
        followup = triage_result.get('follow_up_plan')
        recommended_tests = triage_result.get('recommended_tests', [])
        score = assessment_result.get('score', 0)

        if self.enable_llm_report:
            llm_report = await self._generate_common_diagnosis_llm(
                patient_data, triage_result, diagnosis
            )
            logger.info(f"LLM 生成的报告: {llm_report}")
            if llm_report:
                report: CommonDiagnosisReport = CommonDiagnosisReport(
                    report_type='COMMON_DIAGNOSIS',
                    report_version='llm_enhanced_v1',
                    status='CONCLUSIVE',
                    path='common',
                    patient_id=patient_data.get('patient_id', 'UNKNOWN'),
                    diagnosis=diagnosis,
                    confidence=confidence,
                    confidence_level=confidence_level,
                    is_rare_disease_alert=False,
                    urgency=triage_result.get('urgency', 'routine'),
                    triage=triage_result,
                    referral_recommendation=llm_report.get('referral_recommendation', referral),
                    follow_up_plan=llm_report.get('follow_up_plan', followup),
                    recommended_tests=llm_report.get('recommended_tests', recommended_tests),
                    data_completeness_score=score,
                    matched_diseases=triage_result.get('matched_diseases', []),
                    clinical_reasoning=llm_report.get('clinical_reasoning'),
                    message=llm_report.get('message', f"根据规则引擎匹配，患者可能患有：{diagnosis}。"),
                )
                return {'final_report': report, 'current_phase': 'common_disease_report'}

        report: CommonDiagnosisReport = CommonDiagnosisReport(
            report_type='COMMON_DIAGNOSIS',
            report_version='rule_based_v1',
            status='CONCLUSIVE',
            path='common',
            patient_id=patient_data.get('patient_id', 'UNKNOWN'),
            diagnosis=diagnosis,
            confidence=confidence,
            confidence_level=confidence_level,
            is_rare_disease_alert=False,
            urgency=triage_result.get('urgency', 'routine'),
            triage=triage_result,
            referral_recommendation=referral,
            follow_up_plan=followup,
            recommended_tests=recommended_tests,
            data_completeness_score=score,
            matched_diseases=triage_result.get('matched_diseases', []),
            message=f"根据规则引擎匹配，患者可能患有：{diagnosis}。",
        )

        return {'final_report': report, 'current_phase': 'common_disease_report'}
    
    async def _generate_common_diagnosis_llm(
        self,
        patient_data: Dict,
        triage_result: Dict,
        diagnosis: str,
    ) -> Optional[Dict[str, Any]]:
        """
        使用 LLM 生成常见病确诊报告的临床推理部分
        LLM 仅作为"临床语言翻译官"，无权改变诊断结论
        """
        system_prompt = """你是一名三甲医院的主治医师。我们的后台规则引擎已经根据严格的临床金标准确诊了该患者患有常见肝病，你需要根据患者数据和规则匹配结果，撰写一份结构化、专业的【确诊与随访建议报告】。

【写作要求】：
1. 语言风格必须是严谨的客观医学术语，不要用类似"您好"的废话。
2. 明确指出患者的哪些异常指标和病史支持了该诊断（结合下方提供的规则匹配细节）。
3. 给出具体的门诊随访与生活干预建议。
4. 不要提及规则引擎未匹配到的疾病诊断，不要自行添加新的诊断方向。
5. 必须严格以 JSON 格式输出。

输出格式示例：
{
    "report_type": "COMMON_DIAGNOSIS",
    "status": "CONCLUSIVE",
    "clinical_reasoning": "患者中年男性，BMI 28提示超重。超声检查明确提示脂肪肝回声，且近期无长期大量饮酒史，排除酒精性肝炎。肝功能仅见轻度异常... 故综合判定为MASLD。",
    "follow_up_plan": "1. 建议减重... 2. 3个月后复查肝功能...",
    "recommended_tests": ["复查项目1", "复查项目2"]
}"""

        # 提取患者关键信息（脱敏+精简，防止 Prompt 注入）
        age = patient_data.get('age', '未知')
        gender = patient_data.get('gender', '未知')
        bmi = patient_data.get('bmi', '未知')
        chief_complaint = patient_data.get('chief_complaint', '无')
        labs = patient_data.get('labs', {})
        ultrasound = patient_data.get('ultrasound', {})
        history = patient_data.get('history', {})

        # 构建精简的患者摘要（限制长度，防止注入）
        patient_summary = (
            f"年龄：{age}岁，性别：{gender}"
            f"{f'，BMI：{bmi}' if bmi != '未知' else ''}"
            f"，主诉：{str(chief_complaint)[:100]}"
        )

        # 提取异常指标
        abnormal_labs = []
        for k, v in labs.items():
            if v is not None and isinstance(v, (int, float)):
                abnormal_labs.append(f"{k}={v}")
            elif v is not None and isinstance(v, str):
                abnormal_labs.append(f"{k}={v}")
        labs_str = "，".join(abnormal_labs[:10]) if abnormal_labs else "无显著异常"

        # 超声结果
        us_findings = ""
        if isinstance(ultrasound, dict):
            us_findings = str(ultrasound.get('findings', '无'))
        elif isinstance(ultrasound, str):
            us_findings = ultrasound[:150]

        # 饮酒史
        alcohol = history.get('alcohol_intake_weekly', history.get('alcohol_intake', '无'))

        user_prompt = f"""患者摘要：{patient_summary}
检验结果：{labs_str}
超声检查：{us_findings}
饮酒史：每周{alcohol}g 酒精
规则引擎匹配结论：{diagnosis}
置信度评分：{triage_result.get('confidence', 0)}
置信度等级：{triage_result.get('confidence_level', 'low')}"""

        return await self._call_llm_report(system_prompt, user_prompt)

    async def _node_triage_examination_report(self, state: DiagnosticState) -> Dict[str, Any]:
        """L5b: 初诊/分诊补检建议报告（支持 LLM 临床语言润色）"""
        logger.info("=== L5b: 生成初诊补检建议 ===")

        triage_result = state.get('triage_result', {})
        assessment_result = state.get('data_assessment_result', {})
        patient_data = state['patient_data']
        missing_critical = assessment_result.get('missing_critical', [])
        missing_recommended = assessment_result.get('missing_recommended', [])

        recommended_tests = triage_result.get('recommended_tests', [])
        if not recommended_tests:
            recommended_tests = assessment_result.get('recommended_actions', [])
        uncertainty_reason = triage_result.get('uncertainty_reason', '')

        if self.enable_llm_report:
            llm_report = await self._generate_triage_recommendation_llm(
                patient_data, triage_result, recommended_tests, uncertainty_reason
            )
            logger.info(f"LLM -b生成的报告: {llm_report}")
            if llm_report:
                report: TriageRecommendationReport = TriageRecommendationReport(
                    report_type='TRIAGE_RECOMMENDATION',
                    report_version='llm_enhanced_v1',
                    status='INCONCLUSIVE',
                    path=triage_result.get('path', 'uncertain'),
                    patient_id=patient_data.get('patient_id', 'UNKNOWN'),
                    diagnosis=triage_result.get('diagnosis'),
                    confidence=triage_result.get('confidence', 0),
                    confidence_level=triage_result.get('confidence_level', 'low'),
                    is_rare_disease_alert=triage_result.get('is_rare_disease_alert', False),
                    urgency=triage_result.get('urgency', 'routine'),
                    triage=triage_result,
                    recommended_tests=llm_report.get('recommended_tests', recommended_tests),
                    missing_critical=missing_critical,
                    missing_recommended=missing_recommended,
                    data_completeness_score=assessment_result.get('score', 0),
                    uncertainty_reason=uncertainty_reason,
                    matched_diseases=triage_result.get('matched_diseases', []),
                    clinical_analysis=llm_report.get('clinical_analysis'),
                    message=llm_report.get('message', '患者基础数据不足以完成安全诊断，请参考以下建议开具检验单。'),
                )
                return {'final_report': report, 'current_phase': 'triage_examination_report'}

        report: TriageRecommendationReport = TriageRecommendationReport(
            report_type='TRIAGE_RECOMMENDATION',
            report_version='rule_based_v1',
            status='INCONCLUSIVE',
            path=triage_result.get('path', 'uncertain'),
            patient_id=patient_data.get('patient_id', 'UNKNOWN'),
            diagnosis=triage_result.get('diagnosis'),
            confidence=triage_result.get('confidence', 0),
            confidence_level=triage_result.get('confidence_level', 'low'),
            is_rare_disease_alert=triage_result.get('is_rare_disease_alert', False),
            urgency=triage_result.get('urgency', 'routine'),
            triage=triage_result,
            message='患者基础数据不足以完成安全诊断，请参考以下建议开具检验单。',
            uncertainty_reason=uncertainty_reason,
            recommended_tests=recommended_tests,
            missing_critical=missing_critical,
            missing_recommended=missing_recommended,
            data_completeness_score=assessment_result.get('score', 0),
            matched_diseases=triage_result.get('matched_diseases', []),
        )

        return {'final_report': report, 'current_phase': 'triage_examination_report'}
    
    async def _generate_triage_recommendation_llm(
        self,
        patient_data: Dict,
        triage_result: Dict,
        recommended_tests: list,
        uncertainty_reason: str,
    ) -> Optional[Dict[str, Any]]:
        """
        使用 LLM 生成补检建议报告的临床分析部分
        LLM 仅作为"临床语言翻译官"，无权改变补检清单
        """
        system_prompt = """你是一名经验丰富的肝病科专家，目前正在指导基层医生看诊。当前患者的病历信息残缺，无法进行安全的明确诊断。系统底层规则已经生成了初步的【补检清单】。你需要撰写一份专业的【检查指导报告】，帮助基层医生理解"为什么需要开这些检查"。

【写作要求】：
1. 提取患者现有的异常表现（如已经很高的 ALT，或特定的症状）。
2. 分析当前异常可能指向的潜在风险（如需要警惕病毒性肝炎、或不能排除 Wilson 病等），让医生意识到补检的必要性。
3. 整合系统给出的补检清单，说明每个检查项的目的（例如："查 ANA 是为了排除自身免疫性肝炎"）。
4. 不要自行添加系统未建议的检查项目。
5. 必须严格以 JSON 格式输出。

输出格式示例：
{
    "report_type": "TRIAGE_RECOMMENDATION",
    "status": "INCONCLUSIVE",
    "clinical_analysis": "患者呈现显著的转氨酶升高（ALT 150），提示急性肝细胞损伤。但由于缺乏乙肝五项及腹部彩超等核心基线数据，目前无法安全排除病毒感染或器质性占位病变。若盲目用药可能延误病情。",
    "recommended_tests": [
        {"test": "乙肝两对半", "purpose": "排查导致肝损的最常见病毒感染源"},
        {"test": "自身抗体谱", "purpose": "由于患者为年轻女性，需警惕自身免疫性肝炎可能"}
    ]
}"""

        # 提取患者关键信息
        age = patient_data.get('age', '未知')
        gender = patient_data.get('gender', '未知')
        chief_complaint = patient_data.get('chief_complaint', '无')
        labs = patient_data.get('labs', {})
        symptoms = patient_data.get('symptoms', {})

        patient_summary = f"年龄：{age}岁，性别：{gender}，主诉：{str(chief_complaint)[:100]}"

        # 现有检验结果
        abnormal_labs = []
        for k, v in labs.items():
            if v is not None and isinstance(v, (int, float)):
                abnormal_labs.append(f"{k}={v}")
            elif v is not None and isinstance(v, str):
                abnormal_labs.append(f"{k}={v}")
        labs_str = "，".join(abnormal_labs[:10]) if abnormal_labs else "无"

        # 现有症状
        present_symptoms = [k for k, v in symptoms.items() if v]
        symptoms_str = "，".join(present_symptoms[:8]) if present_symptoms else "无"

        # 补检清单
        tests_str = "，".join(recommended_tests[:10]) if recommended_tests else "无"

        user_prompt = f"""患者摘要：{patient_summary}
现有检验结果：{labs_str}
现有症状：{symptoms_str}
系统底层补检清单：{tests_str}
规则拦截原因：{uncertainty_reason}"""

        return await self._call_llm_report(system_prompt, user_prompt)

    async def _node_mdt_final_report(self, state: DiagnosticState) -> Dict[str, Any]:
        """L5c: MDT 终局深度诊断报告（历经 L3 多智能体辩论后的终局输出）"""
        logger.info("=== L5c: 生成 MDT 深度诊断报告 ===")

        sorted_hyp = sorted(state.get('hypotheses', []), key=lambda x: x.get('confidence', 0), reverse=True)

        falsification_log = state.get('falsification_log', [])
        falsification_entries = []
        for e in falsification_log:
            falsification_entries.append({
                'hypothesis': getattr(e, 'hypothesis', e.get('hypothesis', '')),
                'falsified': getattr(e, 'falsified', e.get('falsified', False)),
                'contradiction_score': getattr(e, 'contradiction_score', e.get('contradiction_score', 0)),
                'evidence': getattr(e, 'contradicting_evidence', e.get('contradicting_evidence', [])),
                'recommendation': getattr(e, 'recommendation', e.get('recommendation', '')),
            })

        triage_result = state.get('triage_result', {})

        report: MDTFinalReport = MDTFinalReport(
            report_type='FINAL_DIAGNOSIS',
            status='CONCLUSIVE',
            patient_id=state['patient_data'].get('patient_id', 'UNKNOWN'),
            path=triage_result.get('path', 'rare'),
            diagnosis=sorted_hyp[0] if sorted_hyp else None,
            confidence=sorted_hyp[0].get('confidence', 0) if sorted_hyp else 0,
            confidence_level=sorted_hyp[0].get('confidence_level', 'medium') if sorted_hyp else 'medium',
            is_rare_disease_alert=True,
            urgency=triage_result.get('urgency', 'routine'),
            differential_diagnosis=sorted_hyp[:5],
            triage=triage_result,
            referral=state.get('referral_decision', {}),
            debate_process=state.get('debate_state'),
            falsification_log=falsification_entries,
            knowledge_graph=state.get('knowledge_graph_weights', {}),
            memory_context=state.get('memory_context'),
            guideline_check=state.get('guideline_check_result'),
            hitl_questions=state.get('hitl_questions', []),
            hitl_status=state.get('hitl_status', 'normal'),
            excluded_hypotheses=state.get('excluded_hypotheses', []),
            recommended_tests=triage_result.get('recommended_tests', []),
            data_completeness_score=state.get('data_assessment_result', {}).get('score', 0),
        )

        return {'final_report': report, 'current_phase': 'mdt_final_report'}
    
    # ===== Helper Methods =====
    
    def _init_state(self, patient_data: Dict) -> DiagnosticState:
        """初始化状态"""
        return DiagnosticState(
            patient_data=patient_data,
            collected_history={},
            collected_labs={},
            collected_imaging={},
            asked_questions=[],
            patient_answers={},
            data_assessment_result=None,
            triage_result=None,
            hypotheses=[],
            reflection_result=None,
            debate_state=None,
            falsification_log=[],
            hitl_status='normal',
            hitl_questions=[],
            knowledge_graph_weights={},
            excluded_hypotheses=[],
            memory_context={},
            guideline_check_result=None,
            referral_decision={},
            final_report={},
            current_phase='init',
            retry_count=0,
            errors=[],
        )
    
    async def _run_specialist_analyses(self, state: DiagnosticState) -> list:
        """运行专科 Agent 分析 (支持并行)"""
        import asyncio
        
        results = []
        
        # 优先使用MDT管理器进行团队分析
        if self.mdt_manager:
            logger.info("使用MDT管理器进行团队分析")
            team = self.mdt_manager.assemble_team(state['patient_data'])
            team_results = await self.mdt_manager.execute_team_analysis(
                team, state['patient_data']
            )
            return team_results
        
        # 回退：直接并行运行所有专科Agent
        logger.info("直接并行运行专科Agent")
        tasks = []
        agent_names = []
        for agent_name, agent in self.specialist_agents.items():
            tasks.append(self._run_single_agent(agent_name, agent, state))
            agent_names.append(agent_name)
        
        if tasks:
            outcomes = await asyncio.gather(*tasks, return_exceptions=True)
            for i, outcome in enumerate(outcomes):
                if isinstance(outcome, Exception):
                    logger.error(f"Specialist agent {agent_names[i]} failed: {outcome}")
                elif outcome:
                    results.append(outcome)
        
        return results
    
    async def _run_single_agent(self, name: str, agent: Any, state: DiagnosticState) -> Optional[Dict]:
        """运行单个 Agent"""
        try:
            input_data = {
                'patient_data': state['patient_data'],
                'context': {
                    'memory': state.get('memory_context', {}),
                    'longitudinal_summary': state.get('memory_context', {}).get('longitudinal_summary', ''),
                },
            }
            result = await agent.execute(input_data)
            if result.success:
                return {
                    'specialty': name,
                    'data': result.data,
                }
        except Exception as e:
            logger.error(f"Specialist agent {name} failed: {e}")
        
        return None
    
    # ===== Public API =====
    
    async def run_full_pipeline(
        self,
        patient_data: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        执行完整的五层对抗推理流程
        
        Args:
            patient_data: 患者数据
            config: LangGraph 运行时配置 (含 thread_id, checkpoint 等)
        
        Returns:
            Dict: 完整的诊断报告
        """
        checkpointer = MemorySaver()
        compiled = self.graph.compile(checkpointer=checkpointer)
        
        thread_id = config.get('thread_id', 'default') if config else 'default'
        run_config = {"configurable": {"thread_id": thread_id}}
        
        initial_state = self._init_state(patient_data)
        
        final_state = None
        async for event in compiled.astream(initial_state, config=run_config):
            for node_name, node_output in event.items():
                logger.debug(f"Node '{node_name}' completed")
            final_state = event
        
        if final_state:
            last_event = final_state
            for key in reversed(list(last_event.keys())):
                if last_event[key].get('final_report'):
                    return last_event[key]['final_report']
        
        return compiled.get_state(config=run_config).values.get('final_report', {
            'status': 'completed',
            'message': '诊断流程完成',
        })
    
    async def resume_from_hitl(
        self,
        thread_id: str,
        patient_answers: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        从 HITL 挂起状态恢复
        
        Args:
            thread_id: 挂起时的 thread_id
            patient_answers: 医生补充的数据
        
        Returns:
            Dict: 恢复后的诊断报告
        """
        checkpointer = MemorySaver()
        compiled = self.graph.compile(checkpointer=checkpointer)
        
        run_config = {"configurable": {"thread_id": thread_id}}
        
        state_snapshot = compiled.get_state(config=run_config)
        current_values = state_snapshot.values
        
        current_values['hitl_status'] = 'resumed'
        
        pd = current_values.get('patient_data', {})
        if isinstance(pd, dict):
            pd_labs = pd.get('labs', {})
            if isinstance(pd_labs, dict):
                pd_labs.update(patient_answers.get('labs', {}))
            pd_sym = pd.get('symptoms', {})
            if isinstance(pd_sym, dict):
                pd_sym.update(patient_answers.get('symptoms', {}))
        
        compiled.update_state(config=run_config, values={'hitl_status': 'resumed', 'patient_data': pd})
        
        final_state = None
        async for event in compiled.astream(None, config=run_config):
            for node_name, node_output in event.items():
                logger.debug(f"Resume Node '{node_name}' completed")
            final_state = event
        
        if final_state:
            last_event = final_state
            for key in reversed(list(last_event.keys())):
                if last_event[key].get('final_report'):
                    return last_event[key]['final_report']
        
        return compiled.get_state(config=run_config).values.get('final_report', {
            'status': 'resumed_completed',
            'message': '诊断流程已恢复并完成',
        })
    
    def get_graph_structure(self) -> Dict[str, Any]:
        """获取图结构信息 (用于可视化)"""
        compiled = self.graph.compile()
        return {
            'nodes': list(compiled.get_graph().nodes.keys()),
            'edges': [
                (edge.source, edge.target)
                for edge in compiled.get_graph().edges
            ],
        }
