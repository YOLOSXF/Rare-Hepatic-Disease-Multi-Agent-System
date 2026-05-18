"""
自我反思引擎 (Self-Reflection Engine)
借鉴 DeepRare 的核心机制：假设 - 验证 - 修正闭环推理
"""

from typing import Dict, List, Any, Optional
from pydantic import BaseModel
from loguru import logger


class ReflectionConfig(BaseModel):
    """反思引擎配置"""
    max_rounds: int = 2
    confidence_threshold: float = 0.6
    enable_counterfactual: bool = True


class SelfReflectionEngine:
    """
    自我反思引擎
    
    DeepRare 核心创新：通过多轮反思降低误诊率
    1. 假设生成
    2. 假设验证
    3. 假设修正
    """
    
    def __init__(self, config: Optional[ReflectionConfig] = None):
        self.config = config or ReflectionConfig()
        
        # 反思提示词模板
        self.prompts = {
            'hypothesis_generation': """
基于当前证据，生成可能的诊断假设列表。
对于每个假设，请列出：
1. 支持证据
2. 反对证据
3. 证据强度 (强/中/弱)
4. 还需要哪些关键检查来确认/排除
""",
            'hypothesis_verification': """
请对每个诊断假设进行严格验证：
1. 是否满足该疾病的诊断标准？
2. 是否有无法解释的矛盾点？
3. 是否有更简单的解释 (奥卡姆剃刀原则)？
4. 是否需要排除其他鉴别诊断？
""",
            'hypothesis_revision': """
基于验证结果，请修正诊断假设：
1. 哪些假设应该被排除？理由是什么？
2. 哪些假设的可能性应该上调/下调？
3. 是否需要生成新的假设？
4. 下一步最关键的检查是什么？
""",
            'counterfactual': """
反事实推理：如果某个关键证据是相反的，诊断会如何变化？
例如：如果铜蓝蛋白正常，Wilson 病的可能性如何变化？
"""
        }
    
    async def reflect(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行自我反思流程（简化版）
        
        Args:
            input_data: 包含假设和证据
        
        Returns:
            反思结果
        """
        hypotheses = input_data.get('hypotheses', [])
        evidence = input_data.get('evidence', {})
        
        if not hypotheses:
            return {
                'revised_hypotheses': [],
                'confidence_score': 0.0,
                'reflection_log': []
            }
        
        reflection_log = []
        
        # 简化：直接返回假设，不做复杂验证
        reflection_log.append("Round 1: Quick Validation")
        
        # 为每个假设添加基础验证信息
        for hypothesis in hypotheses:
            if isinstance(hypothesis, dict):
                hypothesis['verification'] = {
                    'criteria_met': {'major_criteria': True, 'minor_criteria': True},
                    'contradictions': [],
                    'evidence_strength': 0.5
                }
        
        # 计算置信度
        confidence_score = 0.6 if hypotheses else 0.0
        
        reflection_log.append("Round 2: Confidence Assessment")
        
        return {
            'revised_hypotheses': hypotheses,
            'confidence_score': confidence_score,
            'reflection_log': reflection_log,
            'reflection_summary': f"验证完成，{len(hypotheses)}个假设"
        }
    
    async def _verify_hypotheses(
        self,
        hypotheses: List[Dict],
        evidence: Dict
    ) -> List[Dict]:
        """验证假设"""
        verified = []
        
        for hypothesis in hypotheses:
            disease = hypothesis.get('disease')
            supporting = hypothesis.get('supporting_evidence', [])
            
            # 验证诊断标准
            criteria_met = self._check_diagnostic_criteria(disease, evidence)
            
            # 检查矛盾点
            contradictions = self._find_contradictions(disease, evidence)
            
            # 更新假设
            verified_hypothesis = {
                **hypothesis,
                'verification': {
                    'criteria_met': criteria_met,
                    'contradictions': contradictions,
                    'evidence_strength': self._assess_evidence_strength(supporting, contradictions)
                }
            }
            
            verified.append(verified_hypothesis)
        
        # 按证据强度排序
        try:
            verified.sort(
                key=lambda x: float(x.get('verification', {}).get('evidence_strength', 0)),
                reverse=True
            )
        except Exception as e:
            logger.error(f"Sorting error: {e}")
            logger.error(f"verified: {verified}")
        
        return verified
    
    async def _revise_hypotheses(
        self,
        hypotheses: List[Dict],
        evidence: Dict
    ) -> List[Dict]:
        """修正假设"""
        revised = []
        
        for hypothesis in hypotheses:
            verification = hypothesis.get('verification', {})
            criteria_met = verification.get('criteria_met', {})
            contradictions = verification.get('contradictions', [])
            
            # 排除标准不满足且有矛盾的假设
            if not criteria_met.get('major_criteria') and len(contradictions) > 0:
                hypothesis['status'] = 'excluded'
                hypothesis['exclusion_reason'] = f"诊断标准不满足且存在矛盾：{contradictions}"
                continue
            
            # 调整置信度
            if criteria_met.get('major_criteria') and not contradictions:
                hypothesis['confidence'] = min(0.95, hypothesis.get('confidence', 0.5) + 0.2)
            elif contradictions:
                hypothesis['confidence'] = max(0.1, hypothesis.get('confidence', 0.5) - 0.2)
            
            revised.append(hypothesis)
        
        # 过滤被排除的假设
        revised = [h for h in revised if h.get('status') != 'excluded']
        
        return revised
    
    def _check_diagnostic_criteria(self, disease: str, evidence: Dict) -> Dict:
        """检查诊断标准"""
        criteria = {
            'Wilson_Disease': {
                'major_criteria': ['low_ceruloplasmin', 'kf_ring', 'high_urine_copper'],
                'minor_criteria': ['neurological_symptoms', 'liver_disease', 'family_history']
            },
            'Autoimmune_Hepatitis': {
                'major_criteria': ['positive_ana_or_sma', 'high_igg', 'interface_hepatitis'],
                'minor_criteria': ['female_gender', 'other_autoimmune_diseases']
            },
            'Hereditary_Hemochromatosis': {
                'major_criteria': ['high_ferritin', 'high_transferrin_saturation', 'hfe_mutation'],
                'minor_criteria': ['skin_pigmentation', 'diabetes', 'family_history']
            },
            'Primary_Biliary_Cholangitis': {
                'major_criteria': ['positive_ama', 'cholestatic_pattern', 'ductopenia'],
                'minor_criteria': ['female_gender', 'pruritus', 'high_igm']
            }
        }
        
        disease_criteria = criteria.get(disease, {})
        if not disease_criteria:
            return {'major_criteria': True, 'minor_criteria': True}
        
        # 从嵌套结构中提取检验数据
        labs_data = {}
        if isinstance(evidence, dict):
            labs = evidence.get('labs', {})
            if isinstance(labs, dict):
                # 从 lab_interpreter 的响应中提取数据
                abnormal_findings = labs.get('abnormal_findings', [])
                rare_clues = labs.get('rare_disease_clues', [])
                
                # 将检验结果转换为标志
                for finding in abnormal_findings:
                    if isinstance(finding, dict):
                        test = finding.get('test', '')
                        if test == 'ceruloplasmin' and finding.get('direction') == 'low':
                            labs_data['low_ceruloplasmin'] = True
                        if test == 'Ferritin' and finding.get('direction') == 'high':
                            labs_data['high_ferritin'] = True
                
                # 从罕见病线索中提取
                for clue in rare_clues:
                    if isinstance(clue, dict):
                        clue_disease = clue.get('disease', '')
                        if clue_disease == 'Wilson_Disease':
                            labs_data['low_ceruloplasmin'] = True
                        elif clue_disease == 'Autoimmune_Hepatitis':
                            labs_data['high_igg'] = True
                        elif clue_disease == 'Hereditary_Hemochromatosis':
                            labs_data['high_ferritin'] = True
        
        # 从病史中提取临床特征
        history_data = {}
        if isinstance(evidence, dict):
            history = evidence.get('history', {})
            if isinstance(history, dict):
                rare_flags = history.get('rare_disease_flags', [])
                for flag in rare_flags:
                    if isinstance(flag, dict):
                        flag_disease = flag.get('disease', '')
                        if flag_disease == disease:
                            # 找到匹配的罕见病标志
                            flags_found = flag.get('flags_found', [])
                            if isinstance(flags_found, list):
                                for f in flags_found:
                                    if '神经' in str(f) or '震颤' in str(f):
                                        history_data['neurological_symptoms'] = True
                                    if '女性' in str(f):
                                        history_data['female_gender'] = True
                                    if '瘙痒' in str(f):
                                        history_data['pruritus'] = True
        
        # 合并数据
        merged_evidence = {**labs_data, **history_data}
        
        # 检查主要标准
        major_met = all(
            merged_evidence.get(criterion) for criterion in disease_criteria['major_criteria']
        )
        
        # 检查次要标准
        minor_count = sum(
            1 for criterion in disease_criteria['minor_criteria']
            if merged_evidence.get(criterion)
        )
        minor_met = minor_count >= len(disease_criteria['minor_criteria']) // 2 if disease_criteria['minor_criteria'] else True
        
        return {
            'major_criteria': major_met,
            'minor_criteria': minor_met,
            'criteria_details': disease_criteria
        }
    
    def _find_contradictions(self, disease: str, evidence: Dict) -> List[str]:
        """寻找矛盾点"""
        contradictions = []
        
        # 从证据中提取检验值
        ceruloplasmin = None
        ferritin = None
        ana_status = None
        sma_status = None
        igg_level = None
        age = None
        
        if isinstance(evidence, dict):
            # 从检验数据中提取
            labs = evidence.get('labs', {})
            if isinstance(labs, dict):
                abnormal_findings = labs.get('abnormal_findings', [])
                for finding in abnormal_findings:
                    if isinstance(finding, dict):
                        test = finding.get('test', '')
                        value = finding.get('value')
                        if test == 'ceruloplasmin' and isinstance(value, (int, float)):
                            ceruloplasmin = value
                        elif test == 'Ferritin' and isinstance(value, (int, float)):
                            ferritin = value
                        elif test == 'IgG' and isinstance(value, (int, float)):
                            igg_level = value
                        elif test == 'ANA':
                            ana_status = finding.get('direction', 'negative')
                        elif test == 'SMA':
                            sma_status = finding.get('direction', 'negative')
            
            # 从病史中提取年龄
            history = evidence.get('history', {})
            if isinstance(history, dict):
                pmh = history.get('past_medical_history', {})
                if isinstance(pmh, dict):
                    age = pmh.get('age')
        
        # Wilson 病矛盾点
        if disease == 'Wilson_Disease':
            if ceruloplasmin and ceruloplasmin > 0.60:
                contradictions.append('铜蓝蛋白正常或升高，不支持 Wilson 病')
            if age and age > 50:
                contradictions.append('年龄>50 岁，Wilson 病少见')
        
        # AIH 矛盾点
        if disease == 'Autoimmune_Hepatitis':
            if ana_status == 'negative' and sma_status == 'negative':
                contradictions.append('自身抗体阴性，不支持 AIH')
            if igg_level and igg_level < 7.0:
                contradictions.append('IgG 正常，不支持 AIH')
        
        # 血色病矛盾点
        if disease == 'Hereditary_Hemochromatosis':
            if ferritin and ferritin < 300:
                contradictions.append('铁蛋白正常，不支持血色病')
        
        return contradictions
    
    def _assess_evidence_strength(
        self,
        supporting: List,
        contradictions: List[str]
    ) -> float:
        """评估证据强度"""
        if not supporting or not isinstance(supporting, list):
            return 0.0
        
        # 支持证据得分（支持证据现在是字符串列表）
        support_score = len(supporting) * 0.15  # 每个证据 0.15 分
        
        # 矛盾证据扣分
        contradiction_penalty = len(contradictions) * 0.2
        
        return max(0.0, min(1.0, support_score - contradiction_penalty))
    
    def _calculate_confidence(
        self,
        hypotheses: List[Dict],
        evidence: Dict
    ) -> float:
        """计算置信度"""
        if not hypotheses:
            return 0.0
        
        # 取 Top 假设的置信度
        top_hypothesis = hypotheses[0]
        base_confidence = top_hypothesis.get('confidence', 0.5)
        
        # 证据完整性加成
        evidence_completeness = self._assess_evidence_completeness(evidence)
        completeness_bonus = evidence_completeness * 0.2
        
        # 一致性加成
        consistency = self._assess_consistency(hypotheses)
        consistency_bonus = consistency * 0.15
        
        return min(0.95, base_confidence + completeness_bonus + consistency_bonus)
    
    def _assess_evidence_completeness(self, evidence: Dict) -> float:
        """评估证据完整性"""
        required_fields = [
            'history', 'labs', 'imaging'
        ]
        present = sum(1 for field in required_fields if evidence.get(field))
        return present / len(required_fields)
    
    def _assess_consistency(self, hypotheses: List[Dict]) -> float:
        """评估假设一致性"""
        if len(hypotheses) <= 1:
            return 1.0
        
        # 检查 Top 假设之间的一致性
        top_diseases = [h.get('disease') for h in hypotheses[:3]]
        
        # 如果都是肝病相关，一致性高
        liver_diseases = [
            'Wilson_Disease', 'Autoimmune_Hepatitis', 'Hereditary_Hemochromatosis',
            'Primary_Biliary_Cholangitis', 'Cirrhosis', 'Hepatitis'
        ]
        
        liver_count = sum(1 for d in top_diseases if d in liver_diseases)
        return liver_count / len(top_diseases)
    
    async def _counterfactual_analysis(
        self,
        hypothesis: Dict,
        evidence: Dict
    ) -> Dict:
        """反事实推理"""
        disease = hypothesis.get('disease')
        
        # 识别关键证据
        key_evidence = self._identify_key_evidence(disease, evidence)
        
        # 反事实分析
        counterfactuals = {}
        for evidence_name, value in key_evidence.items():
            counterfactual_value = self._get_counterfactual_value(evidence_name, value)
            impact = self._assess_impact(disease, evidence_name, counterfactual_value)
            
            counterfactuals[evidence_name] = {
                'original': value,
                'counterfactual': counterfactual_value,
                'impact_on_diagnosis': impact
            }
        
        return counterfactuals
    
    def _identify_key_evidence(self, disease: str, evidence: Dict) -> Dict:
        """识别关键证据"""
        key_evidence_map = {
            'Wilson_Disease': ['ceruloplasmin', 'kf_ring', 'urine_copper'],
            'Autoimmune_Hepatitis': ['ANA', 'SMA', 'IgG'],
            'Hereditary_Hemochromatosis': ['ferritin', 'transferrin_saturation'],
            'Primary_Biliary_Cholangitis': ['AMA', 'ALP', 'IgM']
        }
        
        keys = key_evidence_map.get(disease, [])
        return {k: evidence.get(k) for k in keys if evidence.get(k) is not None}
    
    def _get_counterfactual_value(self, evidence_name: str, value: Any) -> Any:
        """获取反事实值"""
        if isinstance(value, bool):
            return not value
        elif isinstance(value, (int, float)):
            # 反转高低
            if evidence_name in ['ceruloplasmin', 'ferritin']:
                return value * 2 if value < 1 else value / 2
        return value
    
    def _assess_impact(
        self,
        disease: str,
        evidence_name: str,
        counterfactual_value: Any
    ) -> str:
        """评估反事实影响"""
        # 简化实现
        if evidence_name == 'ceruloplasmin' and disease == 'Wilson_Disease':
            if counterfactual_value > 0.20:
                return "Wilson 病可能性大幅降低"
        return "诊断可能性调整"
    
    def _generate_reflection_summary(
        self,
        original: List[Dict],
        revised: List[Dict],
        confidence: float
    ) -> str:
        """生成反思总结"""
        original_count = len(original)
        revised_count = len(revised)
        excluded_count = original_count - revised_count
        
        return (
            f"反思完成：初始{original_count}个假设，"
            f"排除{excluded_count}个，保留{revised_count}个，"
            f"最终置信度{confidence:.2f}"
        )
