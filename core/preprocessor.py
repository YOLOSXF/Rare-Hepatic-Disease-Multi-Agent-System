"""
数据标准化与预处理模块（L1 层）
负责文本清洗、结构化、单位统一、缺失值标记
"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from loguru import logger
import re


@dataclass
class PreprocessingResult:
    """预处理结果"""
    success: bool
    standardized_data: Dict[str, Any]
    extracted_hpo_terms: List[str] = field(default_factory=list)
    missing_values: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class DataPreprocessor:
    """
    数据预处理器
    
    功能：
    1. 文本清洗与结构化
    2. 检验指标单位统一
    3. 缺失值标记
    4. HPO 术语提取（可选）
    """
    
    # 检验指标单位转换规则
    LAB_UNIT_CONVERSIONS = {
        'ALT': {'target_unit': 'U/L', 'conversions': {'U/L': 1, 'IU/L': 1}},
        'AST': {'target_unit': 'U/L', 'conversions': {'U/L': 1, 'IU/L': 1}},
        'GGT': {'target_unit': 'U/L', 'conversions': {'U/L': 1}},
        'ALP': {'target_unit': 'U/L', 'conversions': {'U/L': 1}},
        'TBil': {'target_unit': 'μmol/L', 'conversions': {'μmol/L': 1, 'mg/dL': 17.1}},
        'DBil': {'target_unit': 'μmol/L', 'conversions': {'μmol/L': 1, 'mg/dL': 17.1}},
        'Albumin': {'target_unit': 'g/L', 'conversions': {'g/L': 1, 'g/dL': 10}},
        'ceruloplasmin': {'target_unit': 'g/L', 'conversions': {'g/L': 1, 'mg/L': 0.001}},
        'ferritin': {'target_unit': 'μg/L', 'conversions': {'μg/L': 1, 'ng/mL': 1}},
        'IgG': {'target_unit': 'g/L', 'conversions': {'g/L': 1, 'mg/dL': 0.01}},
    }
    
    # 症状到 HPO 术语的映射
    SYMPTOM_TO_HPO = {
        '震颤': 'HP:0001337',  # Tremor
        '黄疸': 'HP:0000952',  # Jaundice
        '乏力': 'HP:0003396',  # Fatigue
        '腹胀': 'HP:0003270',  # Abdominal distension
        '食欲不振': 'HP:0002039',  # Anorexia
        '恶心': 'HP:0002018',  # Nausea
        '呕吐': 'HP:0002013',  # Vomiting
        '腹痛': 'HP:0002027',  # Abdominal pain
        '皮肤瘙痒': 'HP:0000989',  # Pruritus
        '构音障碍': 'HP:0001260',  # Dysarthria
        '行为异常': 'HP:0000736',  # Behavioral abnormality
        '肝脾肿大': 'HP:0001434',  # Hepatosplenomegaly
    }
    
    def __init__(self, enable_nlp: bool = False):
        self.enable_nlp = enable_nlp
    
    def preprocess(self, raw_data: Dict[str, Any]) -> PreprocessingResult:
        """
        执行数据预处理
        
        Args:
            raw_data: 原始患者数据
        
        Returns:
            PreprocessingResult: 预处理结果
        """
        standardized = {}
        warnings = []
        errors = []
        missing = []
        hpo_terms = []
        
        try:
            # 1. 基本信息标准化
            standardized['basic_info'] = self._standardize_basic_info(
                raw_data, missing, warnings
            )
            
            # 将 age/gender 提升到顶层，确保下游分诊引擎可直接读取
            if 'age' in standardized['basic_info']:
                standardized['age'] = standardized['basic_info']['age']
            if 'gender' in standardized['basic_info']:
                standardized['gender'] = standardized['basic_info']['gender']
            
            # 2. 主诉清洗
            standardized['chief_complaint'] = self._clean_chief_complaint(
                raw_data.get('chief_complaint', '')
            )
            
            # 3. 症状提取与 HPO 映射
            symptoms, hpo_terms = self._extract_symptoms(raw_data)
            standardized['symptoms'] = symptoms
            
            # 4. 检验数据标准化
            standardized['labs'] = self._standardize_labs(
                raw_data.get('labs', {}), missing, warnings
            )
            
            # 5. 影像学数据标准化
            standardized['imaging'] = self._standardize_imaging(
                raw_data, missing, warnings
            )
            
            # 6. 病史结构化
            standardized['history'] = self._structure_history(
                raw_data, missing, warnings
            )
            
            # 7. 缺失值汇总
            missing.extend(self._check_critical_missing(standardized))
            
            return PreprocessingResult(
                success=True,
                standardized_data=standardized,
                extracted_hpo_terms=hpo_terms,
                missing_values=missing,
                warnings=warnings,
                errors=errors
            )
            
        except Exception as e:
            errors.append(f"预处理失败：{str(e)}")
            return PreprocessingResult(
                success=False,
                standardized_data=standardized,
                errors=errors
            )
    
    def _standardize_basic_info(
        self,
        data: Dict,
        missing: List[str],
        warnings: List[str]
    ) -> Dict[str, Any]:
        """标准化基本信息"""
        basic = {}
        
        # 患者 ID
        basic['patient_id'] = data.get('patient_id', 'UNKNOWN')
        
        # 年龄
        age = data.get('age')
        if age is None or str(age).strip() == '':
            missing.append('年龄')
        elif not isinstance(age, int):
            try:
                basic['age'] = int(age)
            except (ValueError, TypeError):
                warnings.append(f'年龄格式异常：{age}')
                missing.append('年龄')
        else:
            basic['age'] = age
        
        # 性别
        gender = data.get('gender')
        if gender is None or str(gender).strip() == '':
            missing.append('性别')
        else:
            basic['gender'] = 'male' if str(gender).lower() in ['male', '男', 'm'] else 'female'
        
        # BMI（可选）
        bmi = data.get('bmi')
        if bmi is not None and bmi != '':
            try:
                basic['bmi'] = float(bmi)
            except (ValueError, TypeError):
                warnings.append(f'BMI 格式异常：{bmi}')
        
        return basic
    
    def _clean_chief_complaint(self, complaint: str) -> str:
        """清洗主诉"""
        if not complaint:
            return ''
        
        # 去除多余空格和换行
        cleaned = re.sub(r'\s+', ' ', complaint.strip())
        
        # 提取时间信息
        time_pattern = r'(\d+[年月周天日小时])'
        time_matches = re.findall(time_pattern, cleaned)
        
        return cleaned
    
    def _extract_symptoms(self, data: Dict) -> Tuple[Dict[str, bool], List[str]]:
        """
        提取症状并映射到 HPO 术语
        
        Returns:
            Tuple[症状字典，HPO 术语列表]
        """
        symptoms = {}
        hpo_terms = []
        
        # 从现病史提取
        hpi = data.get('hpi', {})
        if isinstance(hpi, dict):
            hpi_symptoms = hpi.get('symptoms', {})
            if isinstance(hpi_symptoms, dict):
                for key, value in hpi_symptoms.items():
                    symptoms[key] = bool(value)
                    if key in self.SYMPTOM_TO_HPO:
                        hpo_terms.append(self.SYMPTOM_TO_HPO[key])
        
        # 从主诉文本提取
        chief_complaint = data.get('chief_complaint', '')
        if chief_complaint:
            for cn_symptom, hpo_id in self.SYMPTOM_TO_HPO.items():
                if cn_symptom in chief_complaint:
                    symptom_key = cn_symptom
                    symptoms[symptom_key] = True
                    if hpo_id not in hpo_terms:
                        hpo_terms.append(hpo_id)
        
        # 从症状列表提取
        symptom_list = data.get('symptoms', [])
        if isinstance(symptom_list, list):
            for symptom in symptom_list:
                if isinstance(symptom, str):
                    symptoms[symptom] = True
                    for cn_symptom, hpo_id in self.SYMPTOM_TO_HPO.items():
                        if cn_symptom in symptom or symptom in cn_symptom:
                            if hpo_id not in hpo_terms:
                                hpo_terms.append(hpo_id)
        
        return symptoms, hpo_terms
    
    def _standardize_labs(
        self,
        labs: Dict,
        missing: List[str],
        warnings: List[str]
    ) -> Dict[str, Any]:
        """标准化检验数据"""
        standardized = {}
        
        if not isinstance(labs, dict):
            warnings.append('检验数据格式异常')
            return standardized
        
        for test_name, value in labs.items():
            if test_name not in self.LAB_UNIT_CONVERSIONS:
                standardized[test_name] = value
                continue
            
            # 处理数值
            if isinstance(value, dict):
                # 有单位信息
                val = value.get('value')
                unit = value.get('unit', '')
                
                try:
                    val = float(val) if val is not None else None
                except (ValueError, TypeError):
                    warnings.append(f'{test_name} 数值格式异常：{val}')
                    val = None
                
                # 单位转换
                if val is not None and unit:
                    conversion = self.LAB_UNIT_CONVERSIONS[test_name]
                    if unit in conversion['conversions']:
                        factor = conversion['conversions'][unit]
                        standardized[test_name] = val * factor
                    else:
                        warnings.append(f'{test_name} 未知单位：{unit}，保持原值')
                        standardized[test_name] = val
                else:
                    standardized[test_name] = val
            else:
                # 直接数值，假设已是标准单位
                try:
                    standardized[test_name] = float(value) if value is not None else None
                except (ValueError, TypeError):
                    warnings.append(f'{test_name} 数值格式异常：{value}')
                    standardized[test_name] = value
        
        # 检查关键检验缺失
        critical_tests = ['ALT', 'AST', 'TBil']
        for test in critical_tests:
            if test not in standardized or standardized[test] is None:
                missing.append(f'{test}（肝功能）')
        
        return standardized
    
    def _standardize_imaging(
        self,
        data: Dict,
        missing: List[str],
        warnings: List[str]
    ) -> Dict[str, Any]:
        """标准化影像学数据"""
        imaging = {}
        
        # 超声
        ultrasound = data.get('ultrasound', {})
        if isinstance(ultrasound, dict):
            imaging['ultrasound'] = {
                'findings': ultrasound.get('findings', ''),
                'impression': ultrasound.get('impression', ''),
                'liver_size': ultrasound.get('liver_size', ''),
                'echogenicity': ultrasound.get('echogenicity', ''),
                'ascites': ultrasound.get('ascites', False)
            }
        elif isinstance(ultrasound, str):
            # 如果是字符串，尝试解析
            imaging['ultrasound'] = {
                'findings': ultrasound,
                'impression': ''
            }
        else:
            missing.append('腹部超声')
        
        # CT（可选）
        ct = data.get('ct', {})
        if ct:
            imaging['ct'] = ct
        
        # MRI（可选）
        mri = data.get('mri', {})
        if mri:
            imaging['mri'] = mri
        
        # 眼科检查（特殊）
        eye_exam = data.get('eye_exam', {})
        if eye_exam:
            imaging['eye_exam'] = eye_exam
        
        return imaging
    
    def _structure_history(
        self,
        data: Dict,
        missing: List[str],
        warnings: List[str]
    ) -> Dict[str, Any]:
        """结构化病史"""
        history = {}
        raw_history = data.get('history', {})
        
        if not isinstance(raw_history, dict):
            raw_history = {}
        
        # 饮酒史
        alcohol = raw_history.get('alcohol_intake') or raw_history.get('alcohol_intake_weekly')
        if alcohol is None:
            missing.append('饮酒史')
            history['alcohol_intake_weekly'] = 0
        else:
            try:
                history['alcohol_intake_weekly'] = float(alcohol)
            except (ValueError, TypeError):
                warnings.append(f'饮酒史格式异常：{alcohol}')
                history['alcohol_intake_weekly'] = 0
        
        # 用药史
        medication = raw_history.get('medication_history')
        if not medication:
            missing.append('用药史')
            history['medication_history'] = '无'
        else:
            history['medication_history'] = str(medication)
        
        # 既往肝病史
        liver_history = raw_history.get('liver_disease_history') or raw_history.get('liver_history')
        history['liver_disease_history'] = liver_history if liver_history else '无'
        
        # 家族史
        family_history = raw_history.get('family_history', [])
        history['family_history'] = family_history if isinstance(family_history, list) else []
        
        # 病毒性肝炎史
        viral_hepatitis = raw_history.get('viral_hepatitis')
        history['viral_hepatitis'] = bool(viral_hepatitis) if viral_hepatitis is not None else False
        
        return history
    
    def _check_critical_missing(self, standardized: Dict) -> List[str]:
        """检查关键缺失项"""
        missing = []
        
        # 基本信息
        basic = standardized.get('basic_info', {})
        age = basic.get('age')
        if age is None or str(age).strip() == '':
            missing.append('年龄')
        gender = basic.get('gender')
        if gender is None or str(gender).strip() == '':
            missing.append('性别')
        
        # 主诉
        if not standardized.get('chief_complaint'):
            missing.append('主诉')
        
        # 检验
        labs = standardized.get('labs', {})
        for test in ['ALT', 'AST', 'TBil']:
            if test not in labs or labs[test] is None:
                if f'{test}（肝功能）' not in missing:
                    missing.append(f'{test}（肝功能）')
        
        return missing


# ==================== 使用示例 ====================

if __name__ == "__main__":
    # 示例数据
    raw_patient = {
        "patient_id": "P001",
        "age": "45",  # 字符串格式
        "gender": "男",
        "chief_complaint": "乏力、腹胀 2 月，加重伴黄疸 1 周",
        "hpi": {
            "symptoms": {
                "tremor": False,
                "jaundice": True,
                "fatigue": True
            }
        },
        "labs": {
            "ALT": {"value": 85, "unit": "U/L"},
            "AST": {"value": 120, "unit": "U/L"},
            "TBil": {"value": 5.2, "unit": "mg/dL"},  # 需要转换
            "ceruloplasmin": 0.15
        },
        "ultrasound": "肝回声增强，肝肾回声比值增加",
        "history": {
            "alcohol_intake_weekly": 280,
            "medication_history": "无特殊用药"
        }
    }
    
    preprocessor = DataPreprocessor()
    result = preprocessor.preprocess(raw_patient)
    
    print(f"预处理成功：{result.success}")
    print(f"HPO 术语：{result.extracted_hpo_terms}")
    print(f"缺失项：{result.missing_values}")
    print(f"警告：{result.warnings}")
    print(f"\n标准化数据:")
    import json
    print(json.dumps(result.standardized_data, ensure_ascii=False, indent=2))
