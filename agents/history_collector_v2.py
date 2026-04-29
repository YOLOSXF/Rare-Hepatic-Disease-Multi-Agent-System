"""
病史采集 Agent V2（基于 LangGraph + 主动追问）
支持多轮对话式病史采集，动态生成追问问题

注意：此模块由 LangGraphOrchestrator 直接使用，避免通过 agents.__init__ 导入
"""

from typing import Dict, List, Optional, Any
from loguru import logger
import asyncio
import sys

# 延迟导入，避免循环依赖
def _get_langgraph_state():
    from core.langgraph_state import InformationCollectionState
    return InformationCollectionState

def _get_llm_client():
    from core.llm_client import LLMClient
    return LLMClient


class HistoryCollectorAgentV2:
    """
    病史采集 Agent V2
    
    核心功能：
    1. 结构化采集患者病史
    2. 主动追问关键信息（多轮对话）
    3. 罕见病红旗征筛查
    4. 病史完整度评估
    5. 动态生成追问问题
    """
    
    def __init__(
        self,
        llm_client=None,
        config_path: str = "config.yaml",
        max_followup_rounds: int = 3
    ):
        self.llm_client = llm_client
        self.config_path = config_path
        self.max_followup_rounds = max_followup_rounds
        self._client_initialized = False
        self._state_imported = False
        self._llm_imported = False
        
        # 罕见病特征签名（用于主动追问）
        self.rare_disease_signatures = {
            "Wilson_Disease": {
                "core_symptoms": ["tremor", "dysarthria", "behavioral_changes", "jaundice"],
                "key_question": "是否有震颤、说话不清或行为改变？",
                "critical_test": "铜蓝蛋白",
                "age_range": (5, 40),
                "inheritance": "常染色体隐性"
            },
            "Autoimmune_Hepatitis": {
                "core_symptoms": ["fatigue", "jaundice", "arthralgia"],
                "key_question": "是否有关节痛或其他自身免疫病史？",
                "critical_test": "自身抗体 (ANA/SMA/LKM-1)",
                "age_range": (10, 70),
                "gender_bias": "female",
                "inheritance": "多基因"
            },
            "Hereditary_Hemochromatosis": {
                "core_symptoms": ["fatigue", "skin_hyperpigmentation", "joint_pain"],
                "key_question": "是否有皮肤变黑、关节痛或糖尿病？",
                "critical_test": "铁蛋白 + 转铁蛋白饱和度",
                "age_range": (30, 60),
                "gender_bias": "male",
                "inheritance": "常染色体隐性"
            },
            "Primary_Biliary_Cholangitis": {
                "core_symptoms": ["pruritus", "fatigue", "jaundice"],
                "key_question": "是否有手掌足底瘙痒（夜间加重）？",
                "critical_test": "AMA/AMA-M2",
                "age_range": (30, 65),
                "gender_bias": "female",
                "inheritance": "多基因"
            },
            "Alpha1_Antitrypsin_Deficiency": {
                "core_symptoms": ["dyspnea", "jaundice", "failure_to_thrive"],
                "key_question": "是否有早发肺气肿或新生儿黄疸？",
                "critical_test": "α1-抗胰蛋白酶水平",
                "age_range": (0, 50),
                "inheritance": "常染色体隐性"
            }
        }
    
    async def initialize(self) -> bool:
        """
        初始化 Agent（兼容 BaseAgent 接口）
        
        Returns:
            bool: 是否初始化成功
        """
        try:
            # 懒加载 LLM 客户端
            self._get_llm_client()
            logger.info("HistoryCollectorAgentV2 initialized successfully")
            return True
        except Exception as e:
            logger.error(f"HistoryCollectorAgentV2 initialization failed: {e}")
            return False
    
    async def execute(self, input_data: Dict[str, Any]):
        """
        执行病史采集（兼容 BaseAgent 接口）
        
        Args:
            input_data: 输入数据
        
        Returns:
            AgentResponse: 执行结果
        """
        from agents.base_agent import AgentResponse
        
        try:
            patient_data = input_data
            result = await self.collect_history(patient_data)
            
            # 将 TypedDict 转换为普通字典
            result_dict = dict(result)
            
            return AgentResponse(
                success=True,
                data={
                    'structured_history': result_dict.get('structured_history', {}),
                    'missing_critical_info': result_dict.get('missing_critical_info', []),
                    'completeness_score': result_dict.get('completeness_score', 0),
                    'rare_disease_flags': result_dict.get('rare_disease_flags', [])
                },
                metadata={
                    "questions_asked": len(result_dict.get('asked_questions', [])),
                    "completeness_score": result_dict.get('completeness_score', 0)
                }
            )
        except Exception as e:
            logger.error(f"HistoryCollectorAgentV2 execute failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return AgentResponse(
                success=False,
                error=str(e)
            )
    
    def _get_llm_client(self):
        """懒加载 LangChain LLM 客户端"""
        if not self._client_initialized:
            LLMClient = _get_llm_client()
            self.llm_client = LLMClient.from_yaml(self.config_path)
            self._client_initialized = True
            logger.info(f"HistoryCollector LLM initialized (LangChain): {self.llm_client.model}")
        return self.llm_client
    
    async def collect_history(
        self,
        patient_data: Dict[str, Any],
        existing_history: Optional[Dict] = None
    ):
        """
        执行病史采集（支持多轮追问）
        
        Args:
            patient_data: 患者基本信息
            existing_history: 已有病史（可选）
        
        Returns:
            InformationCollectionState: 采集结果
        """
        # 延迟导入状态类
        if not self._state_imported:
            InformationCollectionState = _get_langgraph_state()
            self._state_imported = True
        
        state = InformationCollectionState(
            patient_data=patient_data,
            existing_history=existing_history or {},
            current_questions=[],
            asked_questions=[],
            collected_answers={},
            structured_history={},
            rare_disease_flags=[],
            completeness_score=0.0,
            missing_critical_info=[],
            round_count=0,
            max_rounds=self.max_followup_rounds,
            should_continue=True
        )
        
        # 第 1 轮：提取初始病史
        state = await self._extract_initial_history(state)
        
        # 第 2-N 轮：主动追问
        while state['should_continue'] and state['round_count'] < state['max_rounds']:
            state = await self._generate_followup_questions(state)
            
            if state['current_questions']:
                # 模拟患者回答（实际应用中通过对话获取）
                state = await self._simulate_patient_answers(state)
                state['round_count'] += 1
            else:
                state['should_continue'] = False
        
        # 筛查罕见病红旗征
        state = self._screen_rare_disease_flags(state)
        
        # 计算完整度
        state['completeness_score'] = self._calculate_completeness(state)
        
        # 识别缺失关键信息
        state['missing_critical_info'] = self._identify_missing_critical(state)
        
        return state
    
    async def _extract_initial_history(
        self,
        state
    ) -> Any:
        """提取初始病史"""
        patient_data = state['patient_data']
        existing = state['existing_history']
        
        # 结构化病史
        structured = {
            'chief_complaint': patient_data.get('chief_complaint', ''),
            'history_of_present_illness': self._extract_hpi(patient_data),
            'past_medical_history': {
                'age': patient_data.get('age'),
                'gender': patient_data.get('gender'),
                **existing.get('past_medical_history', {})
            },
            'family_history': existing.get('family_history', []),
            'social_history': {
                'alcohol': patient_data.get('history', {}).get('alcohol_intake', 0),
                'smoking': existing.get('smoking', False),
                'occupation': existing.get('occupation', '')
            },
            'medication_history': existing.get('medication_history', ''),
            'review_of_systems': existing.get('review_of_systems', {})
        }
        
        state['structured_history'] = structured
        state['collected_answers'].update(structured)
        
        return state
    
    def _extract_hpi(self, patient_data: Dict) -> Dict:
        """提取现病史"""
        hpi = {}
        
        # 从主诉提取
        chief = patient_data.get('chief_complaint', '')
        if chief:
            hpi['chief_complaint'] = chief
        
        # 从症状提取
        symptoms = patient_data.get('symptoms', {})
        if symptoms:
            hpi['symptoms'] = symptoms
        
        # 从检验推断
        labs = patient_data.get('labs', {})
        if labs:
            hpi['lab_findings'] = {
                'elevated_liver_enzymes': labs.get('ALT', 0) > 40 or labs.get('AST', 0) > 40,
                'jaundice': labs.get('TBil', 0) > 34.2,
                'cholestasis': labs.get('ALP', 0) > 150 or labs.get('GGT', 0) > 60
            }
        
        return hpi
    
    async def _generate_followup_questions(
        self,
        state
    ) -> Any:
        """
        生成追问问题（基于信息缺口和罕见病怀疑）
        
        使用 LLM 动态生成问题
        """
        llm = self._get_llm_client()
        
        # 构建提示词
        current_history = state['structured_history']
        patient_data = state['patient_data']
        
        system_prompt = """你是一名经验丰富的肝病科医生，擅长通过问诊采集病史。
请根据现有病史，生成需要追问的关键问题。

要求：
1. 每次生成 2-4 个最关键的问题
2. 优先追问与罕见病相关的症状
3. 问题要具体、有针对性
4. 避免重复已问的问题

输出格式（JSON）：
{
    "questions": [
        {
            "field": "字段名",
            "question": "具体问题",
            "rationale": "为什么问这个问题",
            "priority": "critical/high/medium/low",
            "related_disease": "相关疾病（如有）"
        }
    ],
    "should_continue": true/false
}"""
        
        user_prompt = f"""现有病史：
- 年龄：{patient_data.get('age', '未知')}
- 性别：{patient_data.get('gender', '未知')}
- 主诉：{current_history.get('chief_complaint', '未知')}
- 现病史：{current_history.get('history_of_present_illness', {})}
- 既往史：{current_history.get('past_medical_history', {})}
- 饮酒史：{current_history.get('social_history', {}).get('alcohol', '未知')}
- 用药史：{current_history.get('medication_history', '未知')}
- 已问问题：{state['asked_questions']}

请生成需要追问的问题。"""
        
        try:
            response = await llm.complete(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.3
            )
            
            import json
            import re
            
            # 解析 JSON
            json_match = re.search(r'```(?:json)?\s*({.*?})\s*```', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = response
            
            result = json.loads(json_str)
            
            # 更新状态
            questions = result.get('questions', [])
            state['current_questions'] = questions[:4]  # 最多 4 个问题
            state['should_continue'] = result.get('should_continue', len(questions) > 0)
            
            logger.info(f"Generated {len(state['current_questions'])} followup questions")
            
        except Exception as e:
            logger.error(f"Failed to generate followup questions: {e}")
            # 降级：使用规则生成问题
            state = self._generate_rules_based_questions(state)
        
        return state
    
    def _generate_rules_based_questions(
        self,
        state
    ) -> Any:
        """
        基于规则生成追问问题（降级方案）
        """
        questions = []
        patient_data = state['patient_data']
        current_history = state['structured_history']
        pmh = current_history.get('past_medical_history', {})
        hpi = current_history.get('history_of_present_illness', {})
        
        # 1. 基于年龄的罕见病筛查
        age = pmh.get('age')
        if age and age < 40:
            if hpi.get('lab_findings', {}).get('elevated_liver_enzymes'):
                questions.append({
                    'field': 'neurological_symptoms',
                    'question': '您是否有过震颤、说话不清、写字困难或行为改变？',
                    'rationale': '年轻肝病患者需排除 Wilson 病（肝豆状核变性）',
                    'priority': 'critical',
                    'related_disease': 'Wilson_Disease'
                })
                
                questions.append({
                    'field': 'eye_exam',
                    'question': '是否做过眼科裂隙灯检查？医生是否提到角膜有色素环（K-F 环）？',
                    'rationale': 'K-F 环是 Wilson 病的特征性体征',
                    'priority': 'critical',
                    'related_disease': 'Wilson_Disease'
                })
        
        # 2. 基于性别的罕见病筛查
        gender = pmh.get('gender')
        if gender == 'female':
            hpi_symptoms = hpi.get('symptoms', {})
            if hpi_symptoms.get('pruritus') or '瘙痒' in str(hpi_symptoms):
                questions.append({
                    'field': 'pruritus_details',
                    'question': '瘙痒是否在手掌和足底最明显？夜间是否加重？',
                    'rationale': 'PBC 特征性瘙痒模式',
                    'priority': 'high',
                    'related_disease': 'Primary_Biliary_Cholangitis'
                })
        
        # 3. 用药史追问
        if not current_history.get('medication_history'):
            questions.append({
                'field': 'medication_history',
                'question': '近 3 个月内是否服用过：抗结核药、抗癫痫药、中草药、解热镇痛药？',
                'rationale': '排查药物性肝损伤',
                'priority': 'high',
                'related_disease': 'DILI'
            })
        
        # 4. 家族史
        if not current_history.get('family_history'):
            questions.append({
                'field': 'family_history',
                'question': '您的家族中是否有肝病、遗传病或其他慢性疾病患者？',
                'rationale': '排查遗传性肝病',
                'priority': 'medium',
                'related_disease': None
            })
        
        # 按优先级排序
        priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        questions.sort(key=lambda x: priority_order.get(x.get('priority', 'low'), 4))
        
        state['current_questions'] = questions[:4]
        state['should_continue'] = len(questions) > 0
        
        return state
    
    async def _simulate_patient_answers(
        self,
        state
    ) -> Any:
        """
        模拟患者回答（实际应用中通过对话获取）
        
        这里根据已有数据推断答案
        """
        questions = state['current_questions']
        patient_data = state['patient_data']
        
        for question in questions:
            field = question.get('field')
            answer = self._infer_answer(field, patient_data, question)
            
            state['collected_answers'][field] = answer
            state['asked_questions'].append(question)
        
        # 更新结构化病史
        state['structured_history'].update(state['collected_answers'])
        
        # 清除当前问题
        state['current_questions'] = []
        
        return state
    
    def _infer_answer(
        self,
        field: str,
        patient_data: Dict,
        question
    ) -> Any:
        """根据已有数据推断答案"""
        # 实际应用中，这里应该等待用户输入
        # 现在根据已有数据推断
        
        if field == 'neurological_symptoms':
            return patient_data.get('symptoms', {}).get('tremor', False)
        
        elif field == 'eye_exam':
            return patient_data.get('eye_exam', {}).get('kf_ring', 'unknown')
        
        elif field == 'medication_history':
            return patient_data.get('history', {}).get('medication_history', '无特殊用药')
        
        elif field == 'family_history':
            return patient_data.get('history', {}).get('family_history', [])
        
        else:
            return None
    
    def _screen_rare_disease_flags(
        self,
        state
    ) -> Any:
        """筛查罕见病红旗征"""
        flags = []
        history = state['structured_history']
        pmh = history.get('past_medical_history', {})
        hpi = history.get('history_of_present_illness', {})
        
        # Wilson 病筛查
        age = pmh.get('age')
        if age is None:
            age = 100
        has_liver_issue = hpi.get('lab_findings', {}).get('elevated_liver_enzymes')
        has_neuro = hpi.get('symptoms', {}).get('tremor') or hpi.get('symptoms', {}).get('dysarthria')
        
        if age < 40 and has_liver_issue and has_neuro:
            flags.append({
                'disease': 'Wilson_Disease',
                'flags_found': ['年龄<40 岁', '肝功能异常', '神经症状'],
                'urgency': 'high',
                'recommended_tests': ['铜蓝蛋白', '24 小时尿铜', '裂隙灯检查', 'ATP7B 基因检测']
            })
        
        # AIH 筛查
        if pmh.get('gender') == 'female':
            if pmh.get('autoimmune_disease') or hpi.get('symptoms', {}).get('arthralgia'):
                flags.append({
                    'disease': 'Autoimmune_Hepatitis',
                    'flags_found': ['女性', '自身免疫病史/关节痛'],
                    'urgency': 'medium-high',
                    'recommended_tests': ['ANA', 'SMA', 'LKM-1', 'IgG', '肝活检']
                })
        
        state['rare_disease_flags'] = flags
        
        if flags:
            logger.info(f"Screened {len(flags)} rare disease flags")
        
        return state
    
    def _calculate_completeness(
        self,
        state
    ) -> float:
        """计算病史完整度评分"""
        required_fields = [
            ('chief_complaint', None),
            ('history_of_present_illness', 'symptoms'),
            ('past_medical_history', 'age'),
            ('past_medical_history', 'gender'),
            ('social_history', 'alcohol'),
            ('medication_history', None),
            ('family_history', None)
        ]
        
        history = state['structured_history']
        filled_count = 0
        
        for field_path in required_fields:
            if self._field_exists(history, field_path):
                filled_count += 1
        
        return round(filled_count / len(required_fields), 2)
    
    def _field_exists(self, data: Dict, field_path: tuple) -> bool:
        """检查嵌套字段是否存在"""
        current = data
        for key in field_path:
            if key is None:
                continue
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return False
        return current is not None and current != ''
    
    def _identify_missing_critical(
        self,
        state
    ) -> List[str]:
        """识别缺失的关键信息"""
        missing = []
        history = state['structured_history']
        pmh = history.get('past_medical_history', {})
        
        if not pmh.get('age'):
            missing.append('年龄')
        if not pmh.get('gender'):
            missing.append('性别')
        if not history.get('social_history', {}).get('alcohol'):
            missing.append('饮酒史')
        if not history.get('medication_history'):
            missing.append('用药史')
        
        return missing


# ==================== LangGraph Node ====================

async def history_collector_node(state: Dict) -> Dict:
    """
    LangGraph Node: 病史采集
    
    Args:
        state: DiagnosticState
    
    Returns:
        Dict: 更新后的状态
    """
    agent = HistoryCollectorAgentV2()
    
    patient_data = state.get('patient_data', {})
    existing_history = state.get('collected_history', {})
    
    result = await agent.collect_history(patient_data, existing_history)
    
    return {
        'collected_history': result['structured_history'],
        'asked_questions': result['asked_questions'],
        'patient_answers': result['collected_answers'],
        'current_phase': 'information_collection_complete'
    }
