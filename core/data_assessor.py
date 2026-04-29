"""
数据完整性评估模块
用于判断患者数据是否足够进行分诊，不足时触发信息收集
"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class DataCompletenessResult:
    """数据完整性评估结果"""
    score: float  # 0.0-1.0
    level: str  # excellent/good/fair/poor
    can_triage: bool  # 是否可以进行分诊
    missing_critical: List[str] = field(default_factory=list)  # 缺失的关键信息
    missing_recommended: List[str] = field(default_factory=list)  # 缺失的推荐信息
    recommended_actions: List[str] = field(default_factory=list)  # 建议的下一步行动
    has_rare_clue: bool = False  # 是否有罕见病线索
    rare_clues: List[str] = field(default_factory=list)  # 罕见病线索列表


class DataCompletenessAssessor:
    """
    数据完整性评估器
    
    评估维度：
    1. 基本信息（年龄、性别）
    2. 主诉
    3. 病史（饮酒、用药、既往史）
    4. 检验数据（肝功能、病毒标志物）
    5. 影像学（超声/CT/MRI）
    6. 特殊检查（自身抗体、铜蓝蛋白等）
    """
    
    # 权重配置
    WEIGHTS = {
        'basic_info': 0.10,      # 基本信息
        'chief_complaint': 0.10,  # 主诉
        'history': 0.15,         # 病史
        'labs_basic': 0.25,      # 基础检验
        'labs_viral': 0.15,      # 病毒标志物
        'imaging': 0.15,         # 影像学
        'labs_special': 0.10     # 特殊检查
    }
    
    # 关键缺失项（影响分诊准确性）
    CRITICAL_FIELDS = {
        'labs_basic': ['ALT', 'AST', 'TBil'],
        'imaging': ['ultrasound.findings'],
        'basic_info': ['age', 'gender'],
    }
    
    def __init__(self):
        pass
    
    def assess(self, patient_data: Dict) -> DataCompletenessResult:
        """
        评估数据完整性
        
        Args:
            patient_data: 患者数据
        
        Returns:
            DataCompletenessResult: 评估结果
        """
        scores = {}
        missing_critical = []
        missing_recommended = []
        
        # 1. 基本信息
        scores['basic_info'] = self._assess_basic_info(patient_data, missing_critical)
        
        # 2. 主诉
        scores['chief_complaint'] = self._assess_chief_complaint(patient_data, missing_critical)
        
        # 3. 病史
        scores['history'] = self._assess_history(patient_data, missing_recommended)
        
        # 4. 基础检验
        scores['labs_basic'] = self._assess_labs_basic(patient_data, missing_critical)
        
        # 5. 病毒标志物
        scores['labs_viral'] = self._assess_labs_viral(patient_data, missing_recommended)
        
        # 6. 影像学
        scores['imaging'] = self._assess_imaging(patient_data, missing_critical)
        
        # 7. 特殊检查
        scores['labs_special'] = self._assess_labs_special(patient_data, missing_recommended)
        
        # 计算加权总分
        total_score = sum(
            scores.get(key, 0) * weight
            for key, weight in self.WEIGHTS.items()
        )
        
        # 确定完整性等级
        if total_score >= 0.9:
            level = 'excellent'
        elif total_score >= 0.7:
            level = 'good'
        elif total_score >= 0.5:
            level = 'fair'
        else:
            level = 'poor'
        
        # 判断是否可以进行分诊
        can_triage = self._can_perform_triage(patient_data, missing_critical)
        
        # 生成建议行动
        recommended_actions = self._generate_recommendations(
            missing_critical,
            missing_recommended,
            patient_data
        )
        
        # 检查罕见病线索（只计算一次，供下游复用）
        has_rare_clue, rare_clues = self.check_rare_disease_clue(patient_data)
        
        return DataCompletenessResult(
            score=round(total_score, 2), #四舍五入，保留两位小数
            level=level,
            missing_critical=missing_critical,
            missing_recommended=missing_recommended,
            can_triage=can_triage,
            recommended_actions=recommended_actions,
            has_rare_clue=has_rare_clue,
            rare_clues=rare_clues
        )
    
    def _assess_basic_info(
        self,
        data: Dict,
        missing: List[str]
    ) -> float:
        """评估基本信息"""
        score = 0.0
        
        # 年龄（必需）
        age = data.get('age')
        if age and isinstance(age, (int, float)) and 0 < age <= 120:
            score += 0.4
        else:
            missing.append('年龄')
        
        # 性别（必需）
        gender = data.get('gender')
        if gender and isinstance(gender, str) and gender in ['male', 'female', '男', '女']:
            score += 0.4
        else:
            missing.append('性别')
        
        # BMI（可选，但有助于脂肪肝诊断）
        bmi = data.get('bmi')
        if bmi and isinstance(bmi, (int, float)) and 10 <= bmi <= 60:
            score += 0.2
        
        return score
    
    def _assess_chief_complaint(
        self,
        data: Dict,
        missing: List[str]
    ) -> float:
        """评估主诉"""
        if data.get('chief_complaint'):
            return 1.0
        else:
            missing.append('主诉')
            return 0.0
    
    def _assess_history(
        self,
        data: Dict,
        missing: List[str]
    ) -> float:
        """评估病史"""
        history = data.get('history', {})
        if not isinstance(history, dict):
            history = {}
        
        score = 0.0
        max_score = 1.0
        
        # 饮酒史
        if history.get('alcohol_intake') is not None or history.get('alcohol_intake_weekly') is not None:
            score += 0.25
        else:
            missing.append('饮酒史')
        
        # 用药史
        if history.get('medication_history'):
            score += 0.25
        else:
            missing.append('用药史')
        
        # 既往肝病史
        if 'liver_disease_history' in history:
            score += 0.25
        else:
            missing.append('既往肝病史')
        
        # 家族史
        if history.get('family_history'):
            score += 0.25
        
        return min(score, max_score)
    
    def _assess_labs_basic(
        self,
        data: Dict,
        missing: List[str]
    ) -> float:
        """评估基础检验（肝功能）"""
        # 统一使用 labs 字段（移除 lab_results 别名以保持一致性）
        labs = data.get('labs', {})
        if not isinstance(labs, dict):
            labs = {}
        
        # 兼容大小写键名：将 labs 的所有键转为大写进行匹配
        labs_upper = {k.upper(): v for k, v in labs.items()}
        
        required_tests = ['ALT', 'AST', 'TBIL']
        found_count = 0
        
        for test in required_tests:
            if test in labs_upper and labs_upper[test] is not None:
                found_count += 1
            else:
                missing.append(f'{test}（肝功能）')
        
        return found_count / len(required_tests)
    
    def _assess_labs_viral(
        self,
        data: Dict,
        missing: List[str]
    ) -> float:
        """评估病毒标志物"""
        # 统一使用 labs 字段
        labs = data.get('labs', {})
        if not isinstance(labs, dict):
            labs = {}
        
        # 兼容大小写键名
        labs_upper = {k.upper(): v for k, v in labs.items()}
        
        viral_tests = {
            'HBSAG': '乙肝表面抗原',
            'ANTI_HCV': '丙肝抗体'
        }
        
        found_count = 0
        for test, name in viral_tests.items():
            if test in labs_upper:
                found_count += 1
            else:
                missing.append(f'{name}')
        
        return found_count / len(viral_tests)
    
    def _assess_imaging(
        self,
        data: Dict,
        missing: List[str]
    ) -> float:
        """评估影像学检查"""
        # 统一使用标准字段：ultrasound/ct/mri
        # 注意：imaging_results 别名已移除，需统一数据结构
        ultrasound = data.get('ultrasound', {})
        if isinstance(ultrasound, dict) and ultrasound.get('findings'):
            return 1.0
        
        ct = data.get('ct', {})
        if isinstance(ct, dict) and ct.get('findings'):
            return 1.0
        
        mri = data.get('mri', {})
        if isinstance(mri, dict) and mri.get('findings'):
            return 1.0
        
        missing.append('腹部影像学（超声/CT/MRI）')
        return 0.0
    
    def _assess_labs_special(
        self,
        data: Dict,
        missing: List[str]
    ) -> float:
        """评估特殊检查（自身抗体、铜蓝蛋白等）"""
        labs = data.get('labs', {})
        if not isinstance(labs, dict):
            labs = {}
        
        # 特殊检查项目
        special_tests = {
            'ANA': '自身抗体 ANA',
            'SMA': '自身抗体 SMA',
            'ceruloplasmin': '铜蓝蛋白',
            'AMA': '抗线粒体抗体',
            'IgG': '免疫球蛋白 IgG',
            'ferritin': '铁蛋白'
        }
        
        found_count = 0
        for test, name in special_tests.items():
            if test in labs:
                found_count += 1
        
        # 有 2 项以上就算有特殊性检查
        if found_count >= 2:
            return 1.0
        elif found_count == 1:
            return 0.5
        else:
            # 特殊检查不是必需的，只是加分项
            return 0.0
    
    def _can_perform_triage(
        self,
        data: Dict,
        missing_critical: List[str]
    ) -> bool:
        """
        判断是否可以进行分诊
        
        标准：
        1. 基本信息完整（年龄、性别）- 增加类型和范围检查
        2. 有主诉
        3. 基础肝功能（ALT、AST、TBil 至少 1-2 项）
        4. 影像学降级为强烈推荐，不再是硬性拦截
        """
        # 基本信息（增加类型和合理性检查）
        age = data.get('age')
        if not age or not isinstance(age, (int, float)) or not (0 < age <= 120):
            return False
        
        gender = data.get('gender')
        if not gender or not isinstance(gender, str):
            return False
        
        # 主诉
        chief_complaint = data.get('chief_complaint')
        if not chief_complaint or not isinstance(chief_complaint, str):
            return False
        
        # 基础肝功能（至少 1-2 项即可进行分诊）
        labs = data.get('labs', {})
        if not isinstance(labs, dict):
            return False
        
        # 兼容大小写键名
        labs_upper = {k.upper(): v for k, v in labs.items()}
        
        liver_tests = ['ALT', 'AST', 'TBIL', 'ALP', 'GGT']
        found_count = sum(1 for test in liver_tests if test in labs_upper and labs_upper[test] is not None)
        if found_count < 1:
            return False
        
        # 移除影像学的硬性拦截
        # 影像学不应该是分诊的绝对门槛，而是深度诊断（L3）的门槛
        # 缺乏影像学会在 recommended_actions 中提示，但不阻止分诊
        
        return True
    
    def _generate_recommendations(
        self,
        missing_critical: List[str],
        missing_recommended: List[str],
        patient_data: Dict
    ) -> List[str]:
        """生成建议行动"""
        recommendations = []
        
        # 关键缺失优先
        if missing_critical:
            recommendations.append(f"【必需检查】{', '.join(missing_critical[:3])}")
        
        # 推荐缺失
        if missing_recommended:
            recommendations.append(f"【建议检查】{', '.join(missing_recommended[:3])}")
        
        # 基于现有数据的智能建议
        labs = patient_data.get('labs', {})
        age = patient_data.get('age', 100)
        gender = patient_data.get('gender', '')
        symptoms = patient_data.get('symptoms', {})
        eye_exam = patient_data.get('eye_exam', {})
        
        # ALT/AST 升高但无病毒标志物 → 建议查病毒
        if (labs.get('ALT', 0) > 80 or labs.get('AST', 0) > 80):
            if 'HBsAg' not in labs or 'anti_HCV' not in labs:
                recommendations.append("转氨酶升高，建议完善病毒性肝炎标志物检查")
        
        # 年轻患者 + 肝功能异常 → 建议查铜蓝蛋白（Wilson病线索）
        if age < 40 and labs.get('ALT', 0) > 40:
            if 'ceruloplasmin' not in labs:
                recommendations.append("年轻患者肝功能异常，建议查铜蓝蛋白排除 Wilson 病")
        
        # 女性 + 肝功能异常 → 建议查自身抗体（AIH线索）
        if gender == 'female' and labs.get('ALT', 0) > 40:
            if 'ANA' not in labs:
                recommendations.append("女性肝功能异常，建议查自身抗体排除自身免疫性肝炎")
        
        # 长期饮酒史 → 建议查 GGT、MCV
        history = patient_data.get('history', {})
        if history.get('alcohol_intake_weekly', 0) > 140:
            if 'GGT' not in labs:
                recommendations.append("长期饮酒，建议查 GGT 评估酒精性肝损伤")
        
        # 罕见病特殊线索检测
        rare_clues = []
        
        # 线索1：神经系统症状（Wilson病）
        if symptoms.get('tremor') or symptoms.get('dysarthria'):
            rare_clues.append("神经系统症状")
            if 'ceruloplasmin' not in labs:
                recommendations.append("有神经系统症状，建议查铜蓝蛋白排除 Wilson 病")
        
        # 线索2：K-F环（Wilson病确诊级体征）
        if eye_exam.get('kf_ring') == 'positive':
            rare_clues.append("K-F环阳性")
            recommendations.append("眼科检查发现K-F环，高度怀疑Wilson病，建议完善铜代谢检查")
        
        # 线索3：铜蓝蛋白降低（Wilson病）
        ceruloplasmin = labs.get('ceruloplasmin')
        if ceruloplasmin is not None and ceruloplasmin < 0.20:
            rare_clues.append("铜蓝蛋白降低")
            recommendations.append("铜蓝蛋白显著降低，高度怀疑Wilson病，建议转诊至专科")
        
        # 线索4：女性+IgG显著升高（AIH）
        igg = labs.get('IgG', 0)
        if gender == 'female' and igg > 15 and labs.get('ALT', 0) > 40:
            rare_clues.append("女性+IgG显著升高")
            if 'ANA' not in labs or 'SMA' not in labs:
                recommendations.append("女性患者IgG显著升高，建议完善自身抗体谱检查")
        
        # 线索5：胆汁淤积模式（PBC/PSC）
        alp = labs.get('ALP', 0)
        ggt = labs.get('GGT', 0)
        if alp > 150 and ggt > 60:
            rare_clues.append("胆汁淤积模式")
            if 'AMA' not in labs:
                recommendations.append("ALP/GGT升高呈胆汁淤积模式，建议查AMA排除PBC")
        
        # 如果有罕见病线索，添加汇总提示
        if rare_clues:
            recommendations.insert(0, f"【罕见病线索】发现{rare_clues}，建议优先完善相关专科检查")
        
        return recommendations
    
    def check_rare_disease_clue(self, patient_data: Dict) -> Tuple[bool, List[str]]:
        """
        检查是否有罕见病线索
        
        Returns:
            Tuple[bool, List[str]]: (是否有线索, 线索列表)
        """
        clues = []
        
        age = patient_data.get('age', 100)
        labs = patient_data.get('labs', {})
        symptoms = patient_data.get('symptoms', {})
        eye_exam = patient_data.get('eye_exam', {})
        gender = patient_data.get('gender', '')
        
        # 线索1：年轻+肝功能显著异常
        if age < 40:
            alt = labs.get('ALT', 0)
            ast = labs.get('AST', 0)
            if alt > 80 or ast > 80:
                clues.append("年轻患者肝功能显著异常")
        
        # 线索2：神经系统症状
        if symptoms.get('tremor'):
            clues.append("手抖")
        if symptoms.get('dysarthria'):
            clues.append("言语不清")
        if symptoms.get('behavioral_changes'):
            clues.append("行为改变")
        
        # 线索3：K-F环
        if eye_exam.get('kf_ring') == 'positive':
            clues.append("K-F环阳性")
        
        # 线索4：铜蓝蛋白降低
        ceruloplasmin = labs.get('ceruloplasmin')
        if ceruloplasmin is not None and ceruloplasmin < 0.20:
            clues.append("铜蓝蛋白降低")
        
        # 线索5：女性+IgG升高
        igg = labs.get('IgG', 0)
        if gender == 'female' and igg > 15:
            clues.append("女性IgG显著升高")
        
        # 线索6：胆汁淤积模式
        alp = labs.get('ALP', 0)
        ggt = labs.get('GGT', 0)
        if alp > 150 and ggt > 60:
            clues.append("胆汁淤积模式")
        
        return len(clues) > 0, clues


# ==================== 使用示例 ====================
if __name__ == "__main__":
    # 示例 1：数据完整
    patient_complete = {
        "age": 45,
        "gender": "male",
        "chief_complaint": "体检发现脂肪肝",
        "history": {
            "alcohol_intake": 50,
            "medication_history": "无"
        },
        "labs": {
            "ALT": 58,
            "AST": 42,
            "TBil": 15.2,
            "HBsAg": "negative"
        },
        "ultrasound": {
            "findings": "肝回声增强"
        }
    }
    
    assessor = DataCompletenessAssessor()
    result = assessor.assess(patient_complete)
    
    print(f"完整性评分：{result.score}")
    print(f"完整性等级：{result.level}")
    print(f"可分诊：{result.can_triage}")
    print(f"建议行动：{result.recommended_actions}")
    
    # 示例 2：数据不完整
    patient_incomplete = {
        "age": 30,
        "chief_complaint": "乏力 1 周",
        "labs": {
            "ALT": 65
        }
    }
    
    result2 = assessor.assess(patient_incomplete)
    
    print(f"\n数据不完整患者:")
    print(f"完整性评分：{result2.score}")
    print(f"缺失关键项：{result2.missing_critical}")
    print(f"可分诊：{result2.can_triage}")
    print(f"建议行动：{result2.recommended_actions}")
