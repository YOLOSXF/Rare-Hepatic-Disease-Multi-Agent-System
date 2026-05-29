"""
信息缺口评估与精准追问

基于竞争假设识别鉴别诊断中的关键缺失证据，生成精准追问问题。

KG集成:
- integration.info_gap=true: 使用 KG get_info_gap_priority() 替代硬编码追问规则
- integration.info_gap=false: 回退到原有硬编码规则
- kg_interface=None: 回退到原有硬编码规则
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
from loguru import logger


class QuestionPriority(Enum):
    """问题优先级"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class GapQuestion:
    """缺口问题"""
    field: str
    question: str
    rationale: str
    priority: QuestionPriority
    related_disease: str
    expected_test: str


@dataclass
class GapAssessmentResult:
    """缺口评估结果"""
    has_gaps: bool
    questions: List[GapQuestion]
    gap_summary: str


class InformationGapAssessor:
    """
    信息缺口评估器
    
    功能：
    1. 基于竞争假设识别关键缺证
    2. 生成精准追问问题（限2轮防骚扰）
    3. 评估是否满足鉴别诊断要求
    
    KG集成路径:
    - kg_interface + integration.info_gap → KG get_info_gap_priority()
    - 降级路径 → 原有硬编码 if-elif 规则
    """
    
    def __init__(
        self,
        max_questions_per_round: int = 3,
        max_rounds: int = 2,
        kg_interface: Optional[Any] = None,
    ):
        self.max_questions_per_round = max_questions_per_round
        self.max_rounds = max_rounds
        self.kg_interface = kg_interface
    
    def assess(
        self,
        hypotheses: List[Dict[str, Any]],
        patient_data: Dict[str, Any]
    ) -> GapAssessmentResult:
        questions = []
        
        for hypothesis in hypotheses:
            disease = hypothesis.get('disease', '')
            disease_questions = self._generate_disease_specific_questions(
                disease, patient_data
            )
            questions.extend(disease_questions)
        
        questions = self._deduplicate_and_sort(questions)
        questions = questions[:self.max_questions_per_round]
        
        has_gaps = len(questions) > 0
        
        return GapAssessmentResult(
            has_gaps=has_gaps,
            questions=questions,
            gap_summary=f"识别到 {len(questions)} 个关键信息缺口" if has_gaps else "信息充足"
        )
    
    def should_interrupt(self, gap_result: GapAssessmentResult) -> bool:
        for q in gap_result.questions:
            if q.priority in (QuestionPriority.CRITICAL, QuestionPriority.HIGH):
                return True
        return False
    
    def _generate_disease_specific_questions(
        self,
        disease: str,
        patient_data: Dict
    ) -> List[GapQuestion]:
        """生成疾病特定的追问问题（优先KG路径，降级到硬编码路径）"""
        
        if self.kg_interface and self.kg_interface.is_enabled():
            try:
                kg_config = self.kg_interface.config
                if kg_config.integration.info_gap:
                    questions = self._generate_questions_via_kg(disease, patient_data)
                    if questions is not None:
                        logger.info(f"KG追问路径: disease={disease}, questions={len(questions)}")
                        return questions
            except Exception as e:
                logger.warning(f"KG追问路径失败，降级到硬编码: {e}")
        
        return self._generate_questions_via_hardcoded(disease, patient_data)
    
    def _generate_questions_via_kg(
        self, disease: str, patient_data: Dict
    ) -> Optional[List[GapQuestion]]:
        gap_features = self.kg_interface.get_info_gap_priority(patient_data)

        if not gap_features:
            return None

        questions = []
        for feature_name in gap_features[:self.max_questions_per_round * 2]:
            priority = QuestionPriority.HIGH

            try:
                if self.kg_interface:
                    query = """
                    MATCH (f:Feature {name: $name})
                    RETURN f.is_core AS is_core, f.specificity AS specificity
                    LIMIT 1
                    """
                    results = self.kg_interface._run_neo4j_query(query, {"name": feature_name})
                    if results:
                        record = results[0]
                        is_core = record.get("is_core", False)
                        if is_core:
                            priority = QuestionPriority.CRITICAL
                else:
                    from core.kg.kg_config import KGConfig
                    config = KGConfig.from_yaml()
                    driver = config.get_neo4j_driver()
                    with driver.session(database=config.neo4j.database) as session:
                        result = session.run(
                            """
                            MATCH (f:Feature {name: $name})
                            RETURN f.is_core AS is_core, f.specificity AS specificity
                            LIMIT 1
                            """,
                            {"name": feature_name}
                        )
                        record = result.single()
                        if record:
                            is_core = record.get("is_core", False)
                            if is_core:
                                priority = QuestionPriority.CRITICAL
                    driver.close()
            except Exception:
                pass

            questions.append(GapQuestion(
                field=feature_name,
                question=f"请提供{feature_name}相关检查结果",
                rationale=f"{feature_name}是{disease}鉴别诊断的关键指标",
                priority=priority,
                related_disease=disease,
                expected_test=feature_name,
            ))

        return questions
    
    def _generate_questions_via_hardcoded(
        self, disease: str, patient_data: Dict
    ) -> List[GapQuestion]:
        questions = []
        labs = patient_data.get('labs', {})
        symptoms_raw = patient_data.get('symptoms', {})
        symptoms = symptoms_raw if isinstance(symptoms_raw, dict) else {}
        
        if 'Wilson' in disease or 'wilson' in disease.lower():
            if 'ceruloplasmin' not in labs:
                questions.append(GapQuestion(
                    field="ceruloplasmin",
                    question="请提供血清铜蓝蛋白水平",
                    rationale="铜蓝蛋白是Wilson病的关键诊断指标",
                    priority=QuestionPriority.CRITICAL,
                    related_disease="Wilson病",
                    expected_test="血清铜蓝蛋白"
                ))
            if not symptoms.get('kf_ring') and 'eye_exam' not in patient_data:
                questions.append(GapQuestion(
                    field="kf_ring",
                    question="是否进行眼科裂隙灯检查？有无Kayser-Fleischer环？",
                    rationale="K-F环是Wilson病的特征性体征",
                    priority=QuestionPriority.HIGH,
                    related_disease="Wilson病",
                    expected_test="眼科裂隙灯检查"
                ))
        
        if 'PBC' in disease or '胆汁性' in disease:
            if 'AMA_M2' not in labs:
                questions.append(GapQuestion(
                    field="AMA_M2",
                    question="请提供AMA-M2抗体结果",
                    rationale="AMA-M2是PBC的特异性抗体",
                    priority=QuestionPriority.CRITICAL,
                    related_disease="原发性胆汁性胆管炎",
                    expected_test="AMA-M2抗体"
                ))
        
        if '血色病' in disease or 'hemochromatosis' in disease.lower():
            if 'Ferritin' not in labs:
                questions.append(GapQuestion(
                    field="Ferritin",
                    question="请提供血清铁蛋白水平",
                    rationale="铁蛋白是血色病的关键筛查指标",
                    priority=QuestionPriority.CRITICAL,
                    related_disease="遗传性血色病",
                    expected_test="血清铁蛋白+转铁蛋白饱和度"
                ))
        
        return questions
    
    def _deduplicate_and_sort(self, questions: List[GapQuestion]) -> List[GapQuestion]:
        seen = set()
        unique = []
        for q in questions:
            if q.field not in seen:
                seen.add(q.field)
                unique.append(q)
        
        priority_order = {
            QuestionPriority.CRITICAL: 0,
            QuestionPriority.HIGH: 1,
            QuestionPriority.MEDIUM: 2,
            QuestionPriority.LOW: 3
        }
        unique.sort(key=lambda x: priority_order.get(x.priority, 99))
        
        return unique
