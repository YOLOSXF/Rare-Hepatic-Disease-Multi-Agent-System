"""
信息缺口评估与精准追问

基于竞争假设识别鉴别诊断中的关键缺失证据，生成精准追问问题。
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum


class QuestionPriority(Enum):
    """问题优先级"""
    CRITICAL = "critical"    # 关键缺证，必须补充
    HIGH = "high"           # 重要缺证，强烈建议补充
    MEDIUM = "medium"       # 一般缺证，建议补充
    LOW = "low"             # 参考性缺证，可选补充


@dataclass
class GapQuestion:
    """缺口问题"""
    field: str                      # 字段名
    question: str                   # 问题内容
    rationale: str                  # 追问理由
    priority: QuestionPriority      # 优先级
    related_disease: str            # 相关疾病
    expected_test: str              # 推荐检查


@dataclass
class GapAssessmentResult:
    """缺口评估结果"""
    has_gaps: bool                  # 是否存在缺口
    questions: List[GapQuestion]    # 追问问题列表
    gap_summary: str                # 缺口摘要


class InformationGapAssessor:
    """
    信息缺口评估器
    
    功能：
    1. 基于竞争假设识别关键缺证
    2. 生成精准追问问题（限2轮防骚扰）
    3. 评估是否满足鉴别诊断要求
    """
    
    def __init__(self, max_questions_per_round: int = 3, max_rounds: int = 2):
        self.max_questions_per_round = max_questions_per_round
        self.max_rounds = max_rounds
    
    def assess(
        self,
        hypotheses: List[Dict[str, Any]],
        patient_data: Dict[str, Any]
    ) -> GapAssessmentResult:
        """
        评估信息缺口
        
        Args:
            hypotheses: 诊断假设列表
            patient_data: 患者数据
            
        Returns:
            GapAssessmentResult: 缺口评估结果
        """
        questions = []
        
        # 基于假设识别缺失的关键证据
        for hypothesis in hypotheses:
            disease = hypothesis.get('disease', '')
            
            # 根据疾病类型确定关键缺证
            disease_questions = self._generate_disease_specific_questions(
                disease, patient_data
            )
            questions.extend(disease_questions)
        
        # 去重并排序
        questions = self._deduplicate_and_sort(questions)
        
        # 限制问题数量
        questions = questions[:self.max_questions_per_round]
        
        has_gaps = len(questions) > 0
        
        return GapAssessmentResult(
            has_gaps=has_gaps,
            questions=questions,
            gap_summary=f"识别到 {len(questions)} 个关键信息缺口" if has_gaps else "信息充足"
        )
    
    def should_interrupt(self, gap_result: GapAssessmentResult) -> bool:
        """
        判断是否应中断（HITL挂起）
        
        规则：
        - 存在 CRITICAL 级别缺证：必须挂起
        - 存在 HIGH 级别缺证：建议挂起
        - 只有 MEDIUM/LOW 级别：不挂起，记录建议
        """
        for q in gap_result.questions:
            if q.priority in (QuestionPriority.CRITICAL, QuestionPriority.HIGH):
                return True
        return False
    
    def _generate_disease_specific_questions(
        self,
        disease: str,
        patient_data: Dict
    ) -> List[GapQuestion]:
        """生成疾病特定的追问问题"""
        questions = []
        labs = patient_data.get('labs', {})
        symptoms = patient_data.get('symptoms', {})
        
        # Wilson病关键缺证
        if 'Wilson' in disease or 'wilson' in disease.lower():
            if 'Ceruloplasmin' not in labs:
                questions.append(GapQuestion(
                    field="Ceruloplasmin",
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
        
        # PBC关键缺证
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
        
        # 血色病关键缺证
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
        """去重并排序"""
        # 按 field 去重
        seen = set()
        unique = []
        for q in questions:
            if q.field not in seen:
                seen.add(q.field)
                unique.append(q)
        
        # 按优先级排序
        priority_order = {
            QuestionPriority.CRITICAL: 0,
            QuestionPriority.HIGH: 1,
            QuestionPriority.MEDIUM: 2,
            QuestionPriority.LOW: 3
        }
        unique.sort(key=lambda x: priority_order.get(x.priority, 99))
        
        return unique
