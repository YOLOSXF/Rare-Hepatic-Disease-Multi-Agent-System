"""
L2 智能初筛分诊模块
实现三层分流机制：
1. 规则引擎快速匹配常见病
2. LLM 兜底分析非典型病例
3. 输出三级分类：常见/可疑罕见/不确定

支持规则热更新：修改 YAML 文件后无需重启，自动生效
"""

from typing import Dict, List, Optional, Any, Tuple
from pydantic import BaseModel
from loguru import logger
import yaml
import os
import time
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class RuleMatchResult:
    """单条规则匹配结果"""
    rule_field: str
    operator: str
    expected_value: Any
    actual_value: Any
    matched: bool
    score: float
    note: str = ""


@dataclass
class DiseaseMatchResult:
    """疾病匹配结果"""
    disease_id: str
    disease_name: str
    category: str  # common/rare
    total_score: float
    max_possible_score: float
    normalized_score: float
    confidence_level: str  # high/medium/low/none
    matched_rules: List[RuleMatchResult] = field(default_factory=list)
    missed_core_rules: List[str] = field(default_factory=list)
    field_score_details: Dict[str, Dict[str, float]] = field(default_factory=dict)
    output: Optional[Dict] = None
    urgency: str = "routine"


@dataclass
class TriageResult:
    """初筛分诊结果"""
    path: str  # common/rare/uncertain
    diagnosis: Optional[str] = None
    confidence: float = 0.0
    confidence_level: str = "none"
    matched_diseases: List[DiseaseMatchResult] = field(default_factory=list)
    referral_recommendation: Optional[str] = None
    follow_up_plan: Optional[str] = None
    recommended_tests: List[str] = field(default_factory=list)
    is_rare_disease_alert: bool = False
    urgency: str = "routine"
    uncertainty_reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class RuleEngine:
    """
    规则引擎
    支持 YAML 配置、热更新、加权评分
    """
    
    def __init__(self, rules_dir: str = "rules"):
        # 转换为绝对路径
        rules_path = Path(rules_dir)
        if not rules_path.is_absolute():
            # 如果是相对路径，基于当前文件所在目录解析
            rules_path = Path(__file__).parent.parent / rules_dir
        
        self.rules_dir = rules_path
        self.common_rules: Dict = {}
        self.rare_rules: Dict = {}
        self.field_test_mapping: Dict[str, str] = {}
        self.last_load_time: float = 0
        self._file_hashes: Dict[str, str] = {}
        
        # 自动加载规则
        self.load_rules()
    
    def _get_file_hash(self, filepath: Path) -> str:
        """获取文件哈希（用于检测变更），返回文件最后修改时间的字符串格式时间戳"""
        try:
            return str(filepath.stat().st_mtime)
        except Exception:
            return ""
    
    def load_rules(self, force: bool = False) -> bool:
        """
        加载规则文件（支持热更新）
        
        Args:
            force: 是否强制重新加载
        
        Returns:
            bool: 是否成功加载
        """
        try:
            # 检查文件是否变更
            common_file = self.rules_dir / "common_diseases.yaml"
            rare_file = self.rules_dir / "rare_diseases.yaml"
            mapping_file = self.rules_dir / "field_test_mapping.yaml"
            
            logger.debug(f"Checking rules files: common={common_file}, rare={rare_file}")
            
            common_changed = force or self._file_hashes.get(str(common_file)) != self._get_file_hash(common_file)
            rare_changed = force or self._file_hashes.get(str(rare_file)) != self._get_file_hash(rare_file)
            mapping_changed = force or self._file_hashes.get(str(mapping_file)) != self._get_file_hash(mapping_file)
            
            if not (common_changed or rare_changed or mapping_changed):
                logger.debug("Rules unchanged, skipping reload")
                return True
            
            # 加载常见病规则
            if common_file.exists() and common_changed:
                with open(common_file, 'r', encoding='utf-8') as f:
                    self.common_rules = yaml.safe_load(f)
                self._file_hashes[str(common_file)] = self._get_file_hash(common_file)
                rule_count = len(self.common_rules) - 2  # 减去 version 和 last_updated
                logger.info(f"Loaded {rule_count} common disease rules from {common_file}")
            elif not common_file.exists():
                logger.warning(f"Common diseases file not found: {common_file}")
            
            # 加载罕见病规则
            if rare_file.exists() and rare_changed:
                with open(rare_file, 'r', encoding='utf-8') as f:
                    self.rare_rules = yaml.safe_load(f)
                self._file_hashes[str(rare_file)] = self._get_file_hash(rare_file)
                rule_count = len(self.rare_rules) - 2  # 减去 version 和 last_updated
                logger.info(f"Loaded {rule_count} rare disease rules from {rare_file}")
            elif not rare_file.exists():
                logger.warning(f"Rare diseases file not found: {rare_file}")

            # 加载字段到检查项映射
            if mapping_file.exists() and mapping_changed:
                with open(mapping_file, 'r', encoding='utf-8') as f:
                    mapping_data = yaml.safe_load(f) or {}

                raw_mapping = mapping_data.get('mapping', mapping_data)
                if not isinstance(raw_mapping, dict):
                    logger.warning("field_test_mapping.yaml format is invalid, fallback to empty mapping")
                    self.field_test_mapping = {}
                else:
                    self.field_test_mapping = {
                        str(k): str(v) for k, v in raw_mapping.items()
                    }

                self._file_hashes[str(mapping_file)] = self._get_file_hash(mapping_file)
                logger.info(f"Loaded {len(self.field_test_mapping)} field-to-test mappings")
            
            self.last_load_time = time.time()
            return True
            
        except Exception as e:
            logger.error(f"Failed to load rules: {e}")
            return False
    
    def _get_nested_value(self, data: Dict, field_path: str) -> Any:
        """
        获取嵌套字段值（大小写不敏感）
        
        Args:
            data: 输入数据
            field_path: 字段路径（如 "labs.ALT" 或 "history.alcohol_intake"）
        
        Returns:
            字段值，不存在返回 None
        """
        keys = field_path.split('.')
        current = data
        
        for key in keys:
            if isinstance(current, dict):
                # 首先尝试精确匹配
                if key in current:
                    current = current[key]
                else:
                    # 大小写不敏感匹配（用于检验项目等）
                    matched = False
                    for existing_key in current.keys():
                        if existing_key.lower() == key.lower():
                            current = current[existing_key]
                            matched = True
                            break
                    if not matched:
                        return None
            else:
                return None
        
        return current
    
    def _is_empty_or_missing(self, val: Any) -> bool:
        """
        判断值是否在广义上为空/缺失。
        注意：不包含 0 或 False，因为它们在临床逻辑中可能是有效输入（如病史年限为 0）。
        针对医学上的无效零值（如 ALT=0），应由上游的 Data Assessor 预处理节点统一置为 None。
        """
        if val is None:
            return True
        if isinstance(val, str) and not val.strip():
            return True
        if isinstance(val, (list, dict, set)) and not val:
            return True
        return False
        
    def _evaluate_operator(self, actual: Any, operator: str, expected: Any) -> bool:
        """
        评估运算符
        
        支持的运算符：
        - 比较：>, <, >=, <=, ==, !=
        - 字符串：contains, startswith, endswith
        - 特殊：has_recent_medication, within_days
        """
        if actual is None:
            return False
        
        try:
            if operator == ">":
                return float(actual) > float(expected)
            elif operator == "<":
                return float(actual) < float(expected)
            elif operator == ">=":
                return float(actual) >= float(expected)
            elif operator == "<=":
                return float(actual) <= float(expected)
            elif operator == "==":
                if isinstance(expected, bool):
                    if isinstance(actual, bool):
                        return actual == expected
                    str_act = str(actual).lower()
                    if expected is True:
                        return str_act in ['true', 'yes', 'positive', '阳性', '有', '1']
                    else:
                        return str_act in ['false', 'no', 'negative', '阴性', '无', '0', 'none']
                return str(actual).lower() == str(expected).lower()
            elif operator == "!=":
                if isinstance(expected, bool):
                    if isinstance(actual, bool):
                        return actual != expected
                    str_act = str(actual).lower()
                    if expected is True:
                        return str_act not in ['true', 'yes', 'positive', '阳性', '有', '1']
                    else:
                        return str_act not in ['false', 'no', 'negative', '阴性', '无', '0', 'none']
                return str(actual).lower() != str(expected).lower()
            elif operator in ("contains", "startswith", "endswith"):
                expected_str = str(expected).lower()
                actual_list = actual if isinstance(actual, (list, tuple, set)) else [actual]
                
                for item in actual_list:
                    item_str = str(item).lower()
                    if operator == "contains" and expected_str in item_str:
                        return True
                    elif operator == "startswith" and item_str.startswith(expected_str):
                        return True
                    elif operator == "endswith" and item_str.endswith(expected_str):
                        return True
                return False
            elif operator == "has_recent_medication":
                # actual 代表相应字段的值
                if isinstance(actual, bool):
                    return actual
                val_str = str(actual).strip().lower()
                return len(val_str) > 0 and val_str not in ['无', '无特殊用药', 'none', '否', 'no']
            elif operator == "within_days":
                #todo
                # 需提供日期解析逻辑，避免由于默认返回 True 而造成误诊
                logger.warning(f"Operator 'within_days' is not fully implemented. evaluated to False. actual: {actual}")
                return False
            else:
                logger.warning(f"Unknown operator: {operator}")
                return False
                
        except (ValueError, TypeError) as e:
            logger.debug(f"Operator evaluation failed: {operator} {actual} {expected}, error: {e}")
            return False
    
    def match_disease(
        self,
        disease_id: str,
        disease_config: Dict,
        patient_data: Dict
    ) -> DiseaseMatchResult:
        """
        匹配单个疾病
        
        Args:
            disease_id: 疾病 ID
            disease_config: 疾病规则配置
            patient_data: 患者数据
        
        Returns:
            DiseaseMatchResult: 匹配结果
        """
        matched_rules = []
        missed_core_rules = []
        missing_required_fields = []
        
        # 1. 检查核心规则（如果有）
        core_rules = disease_config.get('core_rules', [])
        
        for rule in core_rules:
            field_path = rule.get('field')
            operator = rule.get('operator')
            expected = rule.get('value')
            required = rule.get('required', False)
            
            actual = self._get_nested_value(patient_data, field_path)
            matched = self._evaluate_operator(actual, operator, expected)
            
            rule_result = RuleMatchResult(
                rule_field=field_path,
                operator=operator,
                expected_value=expected,
                actual_value=actual,
                matched=matched,
                score=rule.get('score', 0),
                note=rule.get('note', '')
            )
            matched_rules.append(rule_result)
            
            if required and not matched:
                if actual is None:
                    # 报告中缺少关键数据
                    missing_required_fields.append(field_path)
                else:
                    # 报告中存在关键数据，但不符合
                    missed_core_rules.append(f"{field_path} {operator} {expected}")
        
        # 如果有核心规则由于检测结果明确不符（排除），直接排阴
        if missed_core_rules:
            return DiseaseMatchResult(
                disease_id=disease_id,
                disease_name=disease_config.get('name', disease_id),
                category=disease_config.get('category', 'unknown'),
                total_score=0,
                max_possible_score=1,
                normalized_score=0,
                confidence_level='none',
                matched_rules=matched_rules,
                missed_core_rules=missed_core_rules,
                field_score_details={},
                output=disease_config.get('output'),
                urgency=disease_config.get('urgency', 'routine')
            )
            
        # 如果是因为缺失了关键检查导致无法判断，标记为 insufficient_data
        if missing_required_fields:
            return DiseaseMatchResult(
                disease_id=disease_id,
                disease_name=disease_config.get('name', disease_id),
                category=disease_config.get('category', 'unknown'),
                total_score=0,
                max_possible_score=1,
                normalized_score=0,
                confidence_level='insufficient_data',
                matched_rules=matched_rules,
                missed_core_rules=missing_required_fields,
                field_score_details={},
                output=disease_config.get('output'),
                urgency=disease_config.get('urgency', 'routine')
            )
        
        # 2. 检查支持规则
        supporting_rules = disease_config.get('supporting_rules', disease_config.get('rules', []))
        field_combine_strategy = disease_config.get('field_combine_strategy', {})
        
        field_max_available = {} #这个字段在“本疾病的 supporting_rules 里”，理论上最多能拿到多少分

        field_actual_score = {} #这个字段在当前患者身上，实际拿到了多少分
        
        for rule in supporting_rules:
            field_path = rule.get('field')
            operator = rule.get('operator')
            expected = rule.get('value')
            score = rule.get('score', 0.1)
            
            actual = self._get_nested_value(patient_data, field_path) #取出患者报告的值
            matched = self._evaluate_operator(actual, operator, expected)
            
            strategy = field_combine_strategy.get(field_path, 'max')
            
            # 记录该字段最大的可能分
            if strategy == 'sum':
                field_max_available[field_path] = field_max_available.get(field_path, 0) + score
            else:
                field_max_available[field_path] = max(
                    field_max_available.get(field_path, 0), score
                )
            
            rule_result = RuleMatchResult(
                rule_field=field_path,
                operator=operator,
                expected_value=expected,
                actual_value=actual,
                matched=matched,
                score=score,
                note=rule.get('note', '')
            )
            matched_rules.append(rule_result)
            
            
            if matched:
                if strategy == 'sum':
                    field_actual_score[field_path] = field_actual_score.get(field_path, 0) + score
                else:
                    field_actual_score[field_path] = max(
                        field_actual_score.get(field_path, 0), score
                    )
        
        # 3. 计算标准化得分
        total_score = sum(field_actual_score.values())
        max_possible_score = 0.0
        
        field_score_details = {}
        
        # 动态分母：只有已做检查的字段最高可能分计算进去，防稀释
        for field_path, max_s in field_max_available.items():
            val = self._get_nested_value(patient_data, field_path)
            if not self._is_empty_or_missing(val):
                max_possible_score += max_s
                
                # 记录得分明细
                actual_s = field_actual_score.get(field_path, 0.0)
                field_score_details[field_path] = {
                    "actual": actual_s,
                    "max": max_s,
                    "strategy": field_combine_strategy.get(field_path, 'max')
                }
                
        # 证据的完整性/缺失应由 missing_required_fields 机制或上层的 Data Assessment 模块负责处理。
        
        normalized_score = total_score / max_possible_score if max_possible_score > 0 else 0
        
        # 4. 确定置信度等级
        thresholds = disease_config.get('thresholds', {})
        if normalized_score >= thresholds.get('high_confidence', 0.8):
            confidence_level = 'high'
        elif normalized_score >= thresholds.get('medium_confidence', 0.5):
            confidence_level = 'medium'
        elif normalized_score >= thresholds.get('low_confidence', 0.3):
            confidence_level = 'low'
        else:
            confidence_level = 'none'
        
        return DiseaseMatchResult(
            disease_id=disease_id,
            disease_name=disease_config.get('name', disease_id),
            category=disease_config.get('category', 'unknown'),
            total_score=total_score,
            max_possible_score=max_possible_score,
            normalized_score=normalized_score,
            confidence_level=confidence_level,
            matched_rules=matched_rules,
            missed_core_rules=missed_core_rules,
            field_score_details=field_score_details,
            output=disease_config.get('output'),
            urgency=disease_config.get('urgency', 'routine')
        )
    
    def match_all(self, patient_data: Dict) -> List[DiseaseMatchResult]:
        """
        匹配所有疾病规则
        
        Args:
            patient_data: 患者数据
        
        Returns:
            List[DiseaseMatchResult]: 按得分排序的匹配结果
        """
        # 检查规则是否需要热更新
        self.load_rules()
        
        results = []
        
        # 匹配常见病
        for disease_id, disease_config in self.common_rules.items():
            if disease_id in ['version', 'last_updated']:
                continue
            
            result = self.match_disease(disease_id, disease_config, patient_data)
            if result.confidence_level != 'none':
                results.append(result)
        
        # 匹配罕见病
        for disease_id, disease_config in self.rare_rules.items():
            if disease_id in ['version', 'last_updated']:
                continue
            
            result = self.match_disease(disease_id, disease_config, patient_data)
            if result.confidence_level != 'none':
                results.append(result)
        
        # 按得分排序
        results.sort(key=lambda x: x.normalized_score, reverse=True)
        
        return results


class LLMScreener:
    """
    LLM 兜底筛查器
    当规则引擎无法确定时，使用 LLM 分析非典型/边界病例
    """
    
    def __init__(
        self,
        llm_client=None,
        config_path: str = "config.yaml"
    ):
        """
        Args:
            llm_client: LLM 客户端实例（可选，不提供则从 llm_client 模块加载）
            config_path: 配置文件路径
        """
        self.llm_client = llm_client
        self.config_path = config_path
        
        # 懒加载 LLM 客户端
        self._client_initialized = False
    
    def _get_llm_client(self):
        """懒加载 LLM 客户端"""
        if not self._client_initialized:
            from .llm_client import get_llm_client
            
            if self.llm_client is None:
                logger.info(f"Loading LLM client from config: {self.config_path}")
                self.llm_client = get_llm_client(config_path=self.config_path)
            
            self._client_initialized = True
            model_name = getattr(self.llm_client, 'model_name', None) or getattr(self.llm_client, 'model', 'unknown')
            logger.info(f"LLM screener initialized with model: {model_name}")
        
        return self.llm_client
    
    def _build_triage_prompt(self, patient_data: Dict) -> str:
        """构建分诊提示词"""
        prompt_parts = []
        
        # 基本信息
        if patient_data.get('age'):
            prompt_parts.append(f"年龄：{patient_data['age']}岁")
        if patient_data.get('gender'):
            prompt_parts.append(f"性别：{patient_data['gender']}")
        if patient_data.get('bmi'):
            prompt_parts.append(f"BMI: {patient_data['bmi']}")
        
        # 主诉
        if patient_data.get('chief_complaint'):
            prompt_parts.append(f"主诉：{patient_data['chief_complaint']}")
        
        # 病史
        history = patient_data.get('history', {})
        if history:
            history_parts = []
            if history.get('alcohol_intake_weekly'):
                history_parts.append(f"饮酒史：每周{history['alcohol_intake_weekly']}g 酒精")
            if history.get('drinking_years'):
                history_parts.append(f"饮酒年限：{history['drinking_years']}年")
            if history.get('medication_history'):
                history_parts.append(f"用药史：{history['medication_history']}")
            if history.get('viral_hepatitis'):
                history_parts.append(f"病毒性肝炎：{'有' if history['viral_hepatitis'] else '无'}")
            if history.get('autoimmune_disease'):
                history_parts.append(f"自身免疫病史：{'有' if history['autoimmune_disease'] else '无'}")
            
            if history_parts:
                prompt_parts.append("病史：" + "；".join(history_parts))
        
        # 症状
        symptoms = patient_data.get('symptoms', {})
        if symptoms:
            symptom_list = []
            for key, value in symptoms.items():
                if value:
                    symptom_name = key.replace('_', ' ')
                    symptom_list.append(symptom_name)
            if symptom_list:
                prompt_parts.append(f"症状：{', '.join(symptom_list)}")
        
        # 检验结果
        labs = patient_data.get('labs', {})
        if labs:
            lab_parts = []
            lab_mappings = {
                'ALT': 'ALT',
                'AST': 'AST',
                'GGT': 'GGT',
                'TBil': '总胆红素',
                'ALP': '碱性磷酸酶',
                'HBsAg': '乙肝表面抗原',
                'anti_HCV': '丙肝抗体',
                'ANA': 'ANA',
                'SMA': 'SMA',
                'IgG': 'IgG',
                'ceruloplasmin': '铜蓝蛋白',
                'ferritin': '铁蛋白',
                'AMA': 'AMA',
                'AST_ALT_ratio': 'AST/ALT 比值'
            }
            for key, value in labs.items():
                if key in lab_mappings and value is not None:
                    lab_name = lab_mappings[key]
                    if isinstance(value, bool):
                        lab_parts.append(f"{lab_name}: {'阳性' if value else '阴性'}")
                    elif isinstance(value, (int, float)):
                        lab_parts.append(f"{lab_name}: {value}")
                    else:
                        lab_parts.append(f"{lab_name}: {value}")
            
            if lab_parts:
                prompt_parts.append("检验结果：" + "；".join(lab_parts))
        
        # 影像学
        ultrasound = patient_data.get('ultrasound', {})
        if ultrasound and ultrasound.get('findings'):
            prompt_parts.append(f"超声：{ultrasound['findings']}")
        
        # 眼科检查
        eye_exam = patient_data.get('eye_exam', {})
        if eye_exam:
            if eye_exam.get('kf_ring') == 'positive':
                prompt_parts.append("眼科检查：K-F 环阳性")
        
        return "\n".join(prompt_parts)
    
    async def analyze(self, patient_data: Dict) -> Dict:
        """
        使用 LLM 分析病例
        
        Args:
            patient_data: 患者数据
        
        Returns:
            Dict: 分析结果（category, confidence, reasoning）
        """
        logger.info("llm开始分析")
        client = self._get_llm_client()
        
        # 构建提示词
        patient_info = self._build_triage_prompt(patient_data)
        
        system_prompt = """你是一名经验丰富的肝病科医生，负责初步分诊患者。
请根据提供的患者信息，判断最可能的诊断方向。

你需要将病例分为三类之一：
1. common（常见病）：脂肪肝、酒精性肝病、药物性肝损伤、病毒性肝炎等
2. rare（可疑罕见病）：Wilson 病、自身免疫性肝炎、血色病、PBC 等需要进一步专科检查的疾病
3. uncertain（不确定）：信息不足或不典型，需要进一步检查

请严格遵循以下输出格式（JSON）：
{
    "category": "common/rare/uncertain",
    "confidence": 0.0-1.0,
    "reasoning": "简要分析推理过程",
    "most_likely_diagnosis": "最可能的诊断",
    "recommended_tests": ["建议检查 1", "建议检查 2"],
    "red_flags": ["需要警惕的红旗征"]
}

注意事项：
- 年轻患者（<40 岁）+ 肝功能异常 + 神经症状 → 警惕 Wilson 病
- 女性 + 自身抗体阳性 + IgG 升高 → 警惕自身免疫性肝炎
- AST/ALT>2 + 长期饮酒 → 酒精性肝病
- 近期用药史 + 肝功能异常 → 药物性肝损伤
- 肥胖 + 超声脂肪肝 → 脂肪肝"""
        
        user_prompt = f"""请分析以下患者病例：

{patient_info}

---
请按照要求的 JSON 格式输出分诊结果。"""
        
        try:
            import json
            import re
            from langchain_core.messages import SystemMessage, HumanMessage
            
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]
            
            response = await client.ainvoke(messages)
            response_text = response.content
            logger.info(f"llm解析结果：{response_text}")
            
            # 解析 JSON 响应
            # 提取 JSON（可能包含在 markdown 代码块中）
            json_match = re.search(r'```(?:json)?\s*({.*?})\s*```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # 尝试直接解析
                json_str = response_text
            
            result = json.loads(json_str)
            
            # 验证必要字段
            if 'category' not in result:
                result['category'] = 'uncertain'
            if 'confidence' not in result:
                result['confidence'] = 0.5
            if 'recommended_tests' not in result:
                result['recommended_tests'] = ['肝功能全套', '腹部超声']
            
            logger.info(f"LLM triage result: {result.get('category')} (confidence: {result.get('confidence', 0):.2f})")
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            
            # 降级处理：返回默认结果
            return {
                'category': 'uncertain',
                'confidence': 0.5,
                'reasoning': 'LLM 响应解析失败，建议进一步检查',
                'recommended_tests': ['肝功能全套', '腹部超声', '病毒性肝炎标志物']
            }
        except Exception as e:
            error_msg = str(e).lower()
            if 'api key' in error_msg or 'authentication' in error_msg:
                logger.error(f"LLM API authentication failed: {e}")
                fallback_reason = 'LLM API 认证失败，请检查 API 密钥配置'
            elif 'rate limit' in error_msg or 'quota' in error_msg or '429' in error_msg:
                logger.error(f"LLM API rate limit exceeded: {e}")
                fallback_reason = 'LLM API 请求频率超限，请稍后重试'
            elif 'timeout' in error_msg or 'connection' in error_msg:
                logger.error(f"LLM API connection error: {e}")
                fallback_reason = 'LLM API 连接超时，请检查网络配置'
            else:
                logger.error(f"LLM analysis failed: {e}")
                fallback_reason = f'LLM 分析失败：{str(e)}'
            
            # 降级处理
            return {
                'category': 'uncertain',
                'confidence': 0.5,
                'reasoning': fallback_reason,
                'recommended_tests': ['肝功能全套', '腹部超声']
            }
    
    async def close(self):
        """关闭 LLM 客户端"""
        if self.llm_client and self._client_initialized:
            close_fn = getattr(self.llm_client, 'close', None)
            if close_fn is None:
                return

            result = close_fn()
            if hasattr(result, '__await__'):
                await result


class IntelligentTriage:
    """
    智能初筛分诊器 (v2.0 - 分层拦截策略)
    
    整合规则引擎和 LLM 兜底，实现基于置信度权重的三层分流：
    
    策略1: 极高置信常见病绝对压制 (≥0.85)
        - 常见病置信度 ≥0.85 时，直接压制 low 置信度的罕见病预警
        - 被压制的罕见病降级为"随访建议"输出
    
    策略2: 高/中置信罕见病突破机制 (≥medium)
        - 只有罕见病置信度达到 medium 以上时，才允许突破常见病拦截
        - 进入 L3 深度诊断流程
    
    策略3: 低置信罕见病降级处理
        - 低置信罕见病不触发 L3，而是作为排他性建议输出
    """
    
    # 可配置阈值（支持不同医院场景调整）
    HIGH_CONF_COMMON_THRESHOLD = 0.85  # 极高置信常见病阈值
    RARE_BREAKTHROUGH_CONFIDENCE = 0.5  # 罕见病突破阈值（对应 medium 级别）
    
    def __init__(
        self,
        rules_dir: str = "rules",
        llm_config: Optional[Dict] = None,
        config_path: str = "config.yaml"
    ):
        self.rule_engine = RuleEngine(rules_dir)
        self.llm_screener = LLMScreener(
            llm_client=None,
            config_path=config_path
        )

    def _field_to_test_name(self, field_path: str) -> str:
        """将缺失字段路径映射为更可读的检查建议。"""
        return self.rule_engine.field_test_mapping.get(field_path, field_path)

    def _build_missing_data_recommendations(self, insufficient_matches: List[DiseaseMatchResult]) -> List[str]:
        """根据 insufficient_data 结果聚合缺失核心字段，生成补检建议。"""
        missing_fields: List[str] = []
        for match in insufficient_matches:
            missing_fields.extend(match.missed_core_rules)

        # 保序去重
        dedup_fields = list(dict.fromkeys(missing_fields))
        if not dedup_fields:
            return ["请补充关键病史与核心检验项目"]

        return [self._field_to_test_name(field) for field in dedup_fields]

    def _is_high_risk_rare_insufficient(self, match: DiseaseMatchResult) -> bool:
        """判断 insufficient_data 候选中是否属于高风险罕见病。"""
        if match.category != 'rare':
            return False

        urgency = str(match.urgency or '').lower()
        high_risk_levels = {'high', 'urgent', 'emergency', 'critical'}
        return urgency in high_risk_levels or 'high' in urgency

    def _merge_recommended_tests(self, base_tests: List[str], extra_tests: List[str]) -> List[str]:
        """合并并去重检查建议，保持原顺序。"""
        merged = list(base_tests) + list(extra_tests)
        return list(dict.fromkeys(merged))
    
    def _build_followup_for_suppressed_rare(self, suppressed_rare: List[DiseaseMatchResult]) -> str:
        """
        为被压制的低置信罕见病生成随访建议
        
        Args:
            suppressed_rare: 被压制的罕见病列表
        
        Returns:
            str: 随访建议文本
        """
        if not suppressed_rare:
            return None
        
        rare_names = [r.disease_name for r in suppressed_rare]
        
        followup_parts = [
            f"建议随访排除：{'、'.join(rare_names)}",
            "虽然当前证据更支持常见病诊断，但考虑到以下因素，建议定期复查：",
        ]
        
        for rare in suppressed_rare:
            if rare.normalized_score < 0.35:
                followup_parts.append(
                    f"- {rare.disease_name}（置信度{rare.confidence_level}）："
                    f"存在部分非典型特征，建议6-12个月后复查相关指标"
                )
            else:
                followup_parts.append(
                    f"- {rare.disease_name}（置信度{rare.confidence_level}）："
                    f"需警惕可能存在的重叠表现，建议3-6个月后专科随访"
                )
        
        return "\n".join(followup_parts)
    
    def _apply_confidence_interception(
        self,
        common_matches: List[DiseaseMatchResult],
        rare_matches: List[DiseaseMatchResult]
    ) -> Tuple[Optional[str], Optional[DiseaseMatchResult], List[DiseaseMatchResult]]:
        """
        应用三层拦截策略进行置信度权重对比决策
        
        策略逻辑：
        1. 极高置信常见病绝对压制 (≥0.85)
           - 如果最高常见病置信度 ≥ 0.85 且为 high 级别
           - 检查是否有 low 置信度的罕见病
           - 如果有 → 返回 ('common_suppressed', top_common, suppressed_rare)
        
        2. 高/中置信罕见病突破机制 (≥medium)
           - 如果最高罕见病置信度达到 medium 或以上
           - 返回 ('rare_breakthrough', top_rare, rare_matches)
        
        3. 低置信罕见病降级处理
           - 如果罕见病只有 low 置信度且被高置信常见病压制
           - 返回 ('common_suppressed', top_common, suppressed_rare)
        
        Args:
            common_matches: 常见病匹配结果列表
            rare_matches: 罕见病匹配结果列表
        
        Returns:
            Tuple[decision, primary_match, secondary_matches]:
                - decision: 'common_suppressed' | 'rare_breakthrough' | None
                - primary_match: 主要匹配结果
                - secondary_matches: 次要匹配结果（被压制或突破的）
        """
        # 获取各自最高置信度的结果
        top_common = common_matches[0] if common_matches else None
        top_rare = rare_matches[0] if rare_matches else None
        
        # ===== 策略1: 极高置信常见病绝对压制 =====
        if top_common and top_common.normalized_score >= self.HIGH_CONF_COMMON_THRESHOLD:
            
            # 检查是否有需要被压制的低置信罕见病
            low_conf_rare = [
                r for r in rare_matches 
                if r.confidence_level == 'low'
            ]
            
            # 只有当所有罕见病都是 low 置信度时才执行压制
            if low_conf_rare and len(low_conf_rare) == len(rare_matches):
                logger.info(
                    f"策略1触发: 极高置信常见病 '{top_common.disease_name}' "
                    f"({top_common.normalized_score:.2f}) 压制 "
                    f"{len(low_conf_rare)} 个低置信罕见病"
                )
                return (
                    'common_suppressed',
                    top_common,
                    low_conf_rare
                )
            
            # 如果存在 medium/high 罕见病，进入策略2判断
            high_conf_rare = [
                r for r in rare_matches 
                if r.confidence_level in ['high', 'medium']
            ]
            
            if high_conf_rare:
                logger.info(
                    f"检测到高置信罕见病 ({len(high_conf_rare)} 个)，"
                    f"进入策略2突破机制评估"
                )
                # 不返回，继续到策略2处理
        
        # ===== 策略2: 高/中置信罕见病突破机制 =====
        if top_rare and top_rare.confidence_level in ['high', 'medium']:
            
            # 检查是否达到突破阈值
            if top_rare.normalized_score >= self.RARE_BREAKTHROUGH_CONFIDENCE:
                
                # 即使有高置信常见病，也允许罕见病突破（红旗征强烈）
                should_breakthrough = True
                
                if top_common and top_common.normalized_score >= self.HIGH_CONF_COMMON_THRESHOLD:
                    # 特殊情况：极高置信常见病 vs 高置信罕见病
                    # 记录警告日志，但仍然允许罕见病突破
                    logger.warning(
                        f"策略2突破: 高置信罕见病 '{top_rare.disease_name}' "
                        f"(confidence={top_rare.normalized_score:.2f}, level={top_rare.confidence_level}) "
                        f"突破极高置信常见病 '{top_common.disease_name}' "
                        f"(confidence={top_common.normalized_score:.2f})"
                    )
                
                if should_breakthrough:
                    logger.info(
                        f"策略2触发: 高置信罕见病 '{top_rare.disease_name}' "
                        f"突破进入 L3 深度诊断"
                    )
                    return (
                        'rare_breakthrough',
                        top_rare,
                        rare_matches
                    )
        
        # ===== 策略3: 低置信罕见病降级处理 =====
        if top_common and rare_matches:
            # 中等/高置信常见病可以压制 low 罕见病
            if top_common.confidence_level in ['high', 'medium']:
                low_conf_rare = [
                    r for r in rare_matches 
                    if r.confidence_level == 'low'
                ]
                
                if low_conf_rare and len(low_conf_rare) == len(rare_matches):
                    logger.info(
                        f"策略3触发: 中高置信常见病 '{top_common.disease_name}' "
                        f"({top_common.confidence_level}) 降级处理 "
                        f"{len(low_conf_rare)} 个低置信罕见病"
                    )
                    return (
                        'common_suppressed',
                        top_common,
                        low_conf_rare
                    )
        
        # 无明确决策，返回 None 让后续逻辑处理
        return (None, None, [])
    
    def _create_common_result_with_suppression(
        self,
        top_common: DiseaseMatchResult,
        suppressed_rare: List[DiseaseMatchResult],
        start_time: float
    ) -> TriageResult:
        """
        创建包含罕见病压制信息的常见病结果
        
        Args:
            top_common: 最高置信度的常见病匹配结果
            suppressed_rare: 被压制的罕见病列表
            start_time: 开始时间戳
        
        Returns:
            TriageResult: 分诊结果（path='common'，包含随访建议）
        """
        # 生成随访建议
        followup_plan = self._build_followup_for_suppressed_rare(suppressed_rare)
        
        # 合并被压制罕见病的推荐检查
        recommended_tests = list(top_common.output.get('recommended_tests', []) if top_common.output else [])
        
        for rare in suppressed_rare:
            if rare.output and rare.output.get('recommended_tests'):
                tests_to_add = [t for t in rare.output['recommended_tests'] if t not in recommended_tests]
                recommended_tests.extend(tests_to_add[:2])  # 每个罕见病最多加2个检查
        
        result = TriageResult(
            path='common',
            diagnosis=top_common.disease_name,
            confidence=top_common.normalized_score,
            confidence_level=top_common.confidence_level,
            matched_diseases=[top_common] + suppressed_rare[:3],
            referral_recommendation=top_common.output.get('referral') if top_common.output else None,
            follow_up_plan=followup_plan,
            recommended_tests=recommended_tests,
            is_rare_disease_alert=False,  # 关键：不触发罕见病告警
            urgency=top_common.urgency,
            metadata={
                'method': 'confidence_interception_strategy_1_or_3',
                'suppressed_rare_alerts': [r.disease_id for r in suppressed_rare],
                'suppression_reason': f"high_confidence_common_override (score={top_common.normalized_score:.2f})",
                'execution_time_ms': int((time.time() - start_time) * 1000),
                'interception_applied': True
            }
        )
        
        logger.info(
            f"Triage result (with suppression): {top_common.disease_name} "
            f"- suppressed {len(suppressed_rare)} rare disease alerts"
        )
        
        return result
    
    def _create_rare_breakthrough_result(
        self,
        top_rare: DiseaseMatchResult,
        rare_matches: List[DiseaseMatchResult],
        start_time: float
    ) -> TriageResult:
        """
        创建罕见病突破结果（进入 L3 深度诊断）
        
        Args:
            top_rare: 最高置信度的罕见病匹配结果
            rare_matches: 所有罕见病匹配结果
            start_time: 开始时间戳
        
        Returns:
            TriageResult: 分诊结果（path='rare'，触发 L3 深度诊断）
        """
        result = TriageResult(
            path='rare',
            diagnosis=top_rare.disease_name,
            confidence=top_rare.normalized_score,
            confidence_level=top_rare.confidence_level,
            matched_diseases=rare_matches,
            referral_recommendation=top_rare.output.get('referral') if top_rare.output else "转诊至三甲医院肝病中心",
            urgency=top_rare.urgency,
            is_rare_disease_alert=True,
            recommended_tests=top_rare.output.get('recommended_tests', []) if top_rare.output else [],
            metadata={
                'method': 'confidence_interception_strategy_2_breakthrough',
                'breakthrough_reason': f"high_confidence_rare (level={top_rare.confidence_level}, score={top_rare.normalized_score:.2f})",
                'execution_time_ms': int((time.time() - start_time) * 1000)
            }
        )
        
        logger.warning(
            f"Rare disease breakthrough: {top_rare.disease_name} "
            f"(urgency: {top_rare.urgency}, confidence: {top_rare.confidence_level})"
        )
        
        return result
    
    async def triage(
        self,
        patient_data: Dict,
        data_assessment: Optional[Dict] = None
    ) -> TriageResult:
        """
        执行初筛分诊 (v2.2 - 支持数据评估短路拦截)

        决策流程（互斥分支，按优先级依次判断）：

        【闪电拦截】数据评估短路机制
            - 如果数据评估已判定数据不足且无罕见病线索，直接返回，不唤醒重型引擎
            - 节省算力，避免无意义地加载YAML规则、执行正则匹配、调用LLM

        【分支 1】三层拦截策略：常见病与罕见病共存时，按置信度权重裁决
            - 策略1: 极高置信常见病绝对压制 (≥0.85, 罕见病全low)
            - 策略2: 高/中置信罕见病突破机制 (≥medium, score≥0.5)
            - 策略3: 低置信罕见病降级处理

        【分支 2】纯罕见病预警：无任何常见病匹配时，罕见病直接告警

        【分支 3】常见病分流（含纯常见病 + 拦截策略遗漏的共存场景）
            - 统一处理 high/medium 置信度，不再区分快速通道

        【分支 4】核心检查缺失：核心规则缺项挂起，输出结构化补检建议

        【分支 5】LLM 兜底分析：规则引擎无明确匹配时

        Args:
            patient_data: 患者数据（包含病史、检验、影像等）
            data_assessment: 可选，数据评估结果，用于短路拦截
                - can_triage: 是否可以分诊
                - has_rare_clue: 是否有罕见病线索
                - assessment_recommendations: 数据评估生成的检查建议

        Returns:
            TriageResult: 分诊结果
        """
        start_time = time.time()

        # ⭐【闪电拦截机制】：利用数据评估结果进行短路拦截
        if data_assessment:
            can_triage = data_assessment.get('can_triage', True)
            has_rare_clue = data_assessment.get('has_rare_clue', False)
            assessment_recommendations = data_assessment.get('assessment_recommendations', [])

            # 数据严重不足且无罕见病线索时，直接返回，不唤醒重型引擎
            if not can_triage and not has_rare_clue:
                logger.warning(
                    f"⚡ L2闪电拦截触发：数据严重不足 (can_triage={can_triage}, "
                    f"has_rare_clue={has_rare_clue})，跳过重型引擎，耗时 0ms"
                )
                return TriageResult(
                    path='uncertain',
                    diagnosis=None,
                    confidence=0.0,
                    confidence_level='insufficient_data',
                    uncertainty_reason='基线信息极度缺失（如无任何肝功能指标），系统无法进行安全分诊。',
                    recommended_tests=assessment_recommendations,
                    metadata={
                        'method': 'fast_short_circuit_by_data_assessment',
                        'execution_time_ms': 0,
                        'data_assessment_can_triage': can_triage,
                        'data_assessment_has_rare_clue': has_rare_clue,
                    }
                )

        # 0. 规则引擎匹配所有疾病
        rule_results = self.rule_engine.match_all(patient_data)
        
        common_matches = [r for r in rule_results if r.category == 'common']
        rare_matches = [r for r in rule_results if r.category == 'rare' and r.confidence_level != 'none']
        
        # ====== 分支 1：三层拦截策略（常见病与罕见病共存时） ======
        if common_matches and rare_matches:
            decision, primary_match, secondary_matches = self._apply_confidence_interception(
                common_matches, rare_matches
            )
            if decision == 'common_suppressed':
                return self._create_common_result_with_suppression(
                    top_common=primary_match,
                    suppressed_rare=secondary_matches,
                    start_time=start_time
                )
            elif decision == 'rare_breakthrough':
                return self._create_rare_breakthrough_result(
                    top_rare=primary_match,
                    rare_matches=secondary_matches,
                    start_time=start_time
                )
        
        # ====== 分支 2：纯罕见病预警（无任何常见病匹配） ======
        if rare_matches and not common_matches:
            top_rare = rare_matches[0]
            result = TriageResult(
                path='rare',
                diagnosis=top_rare.disease_name,
                confidence=top_rare.normalized_score,
                confidence_level=top_rare.confidence_level,
                matched_diseases=rare_matches,
                referral_recommendation=top_rare.output.get('referral') if top_rare.output else "转诊至三甲医院肝病中心",
                urgency=top_rare.urgency,
                is_rare_disease_alert=True,
                recommended_tests=top_rare.output.get('recommended_tests', []) if top_rare.output else [],
                metadata={
                    'method': 'rule_engine_rare_only',
                    'execution_time_ms': int((time.time() - start_time) * 1000)
                }
            )
            logger.warning(f"Rare disease alert (no common match): {top_rare.disease_name} (urgency: {top_rare.urgency})")
            return result
        
        # ====== 分支 3：常见病分流（纯常见病 / 拦截策略未覆盖的共存场景） ======
        # 注：策略1已覆盖"≥0.85 + 罕见全low"，这里处理剩余 high/medium 常见病
        if common_matches:
            top_match = common_matches[0]
            if top_match.confidence_level in ['high', 'medium']:
                result = TriageResult(
                    path='common',
                    diagnosis=top_match.disease_name,
                    confidence=top_match.normalized_score,
                    confidence_level=top_match.confidence_level,
                    matched_diseases=common_matches[:3],
                    referral_recommendation=top_match.output.get('referral') if top_match.output else None,
                    follow_up_plan=top_match.output.get('followup') if top_match.output else None,
                    recommended_tests=top_match.output.get('recommended_tests', []) if top_match.output else [],
                    metadata={
                        'method': 'rule_engine_common',
                        'execution_time_ms': int((time.time() - start_time) * 1000)
                    }
                )
                logger.info(f"Triage common ({top_match.confidence_level}): {top_match.disease_name} (score={top_match.normalized_score:.2f})")
                return result
        
        # ====== 分支 4：核心检查缺失（insufficient_data） ======
        insufficient_matches = [
            r for r in rule_results
            if r.confidence_level == 'insufficient_data'
        ]

        if insufficient_matches:
            recommended_tests = self._build_missing_data_recommendations(insufficient_matches)

            # 检查是否有高风险罕见病线索（用于graph_orchestrator路由决策）
            high_risk_rare_insufficient = [
                m for m in insufficient_matches
                if self._is_high_risk_rare_insufficient(m)
            ]
            
            # 同时检查患者数据中是否有罕见病临床线索
            has_clinical_rare_clue = self._check_clinical_rare_clue(patient_data)
            has_high_risk_rare_clue = len(high_risk_rare_insufficient) > 0 or has_clinical_rare_clue

            llm_risk_review = None
            if has_high_risk_rare_clue:
                logger.warning(
                    f"Insufficient data with high-risk rare candidates: {len(high_risk_rare_insufficient)}, "
                    f"clinical clue: {has_clinical_rare_clue}; triggering LLM risk review"
                )
                llm_risk_review = await self.llm_screener.analyze(patient_data)

                llm_category = llm_risk_review.get('category', 'uncertain')
                llm_confidence = float(llm_risk_review.get('confidence', 0.0) or 0.0)

                # 只有LLM也确认rare且置信度足够高时才升级为罕见病告警
                if llm_category == 'rare' and llm_confidence >= 0.7:  # 提高阈值到0.7
                    top_rare = high_risk_rare_insufficient[0] if high_risk_rare_insufficient else None
                    rare_disease_name = top_rare.disease_name if top_rare else llm_risk_review.get('most_likely_diagnosis', '罕见肝病')
                    
                    merged_tests = self._merge_recommended_tests(
                        recommended_tests,
                        llm_risk_review.get('recommended_tests', [])
                    )

                    if llm_confidence >= 0.8:
                        llm_confidence_level = 'high'
                    elif llm_confidence >= 0.7:
                        llm_confidence_level = 'medium'
                    else:
                        llm_confidence_level = 'low'

                    return TriageResult(
                        path='rare',
                        diagnosis=rare_disease_name,
                        confidence=llm_confidence,
                        confidence_level=llm_confidence_level,
                        matched_diseases=high_risk_rare_insufficient,
                        referral_recommendation="建议尽快转诊至三甲医院肝病中心完善检查",
                        urgency='high',
                        is_rare_disease_alert=True,
                        recommended_tests=merged_tests,
                        uncertainty_reason=llm_risk_review.get('reasoning', '高风险罕见病线索存在，建议尽快完善检查并转诊。'),
                        metadata={
                            'method': 'insufficient_data_llm_risk_review_rare_alert',
                            'execution_time_ms': int((time.time() - start_time) * 1000),
                            'missing_fields_count': sum(len(m.missed_core_rules) for m in insufficient_matches),
                            'high_risk_rare_insufficient_count': len(high_risk_rare_insufficient),
                            'has_clinical_rare_clue': has_clinical_rare_clue,
                            'llm_risk_review_category': llm_category,
                            'llm_risk_review_confidence': llm_confidence
                        }
                    )
                else:
                    # LLM不认为是罕见病或置信度不够，记录但不升级
                    logger.info(f"LLM risk review result: {llm_category} (conf={llm_confidence:.2f}), not upgrading to rare alert")

            # 无高风险罕见病线索，或LLM评估不通过，返回insufficient_data
            result = TriageResult(
                path='insufficient_data',  # 明确标记为insufficient_data
                confidence=0.0,
                confidence_level='insufficient_data',
                matched_diseases=insufficient_matches,
                uncertainty_reason='核心检查缺失，无法完成规则引擎判定，请优先补齐关键检查。',
                recommended_tests=recommended_tests,
                metadata={
                    'method': 'rule_engine_insufficient_data',
                    'execution_time_ms': int((time.time() - start_time) * 1000),
                    'missing_fields_count': sum(len(m.missed_core_rules) for m in insufficient_matches),
                    'high_risk_rare_insufficient_count': len(high_risk_rare_insufficient),
                    'has_clinical_rare_clue': has_clinical_rare_clue,
                    'llm_risk_review_triggered': llm_risk_review is not None,
                    'llm_risk_review_category': llm_risk_review.get('category') if llm_risk_review else None,
                    'llm_risk_review_confidence': llm_risk_review.get('confidence') if llm_risk_review else None
                }
            )
            logger.info(f"Triage insufficient data: {len(insufficient_matches)} candidate diseases, no high-risk rare clue")
            return result
        
        # ====== 分支 5：LLM 兜底分析 ======
        logger.info("Falling back to LLM screener")
        llm_result = await self.llm_screener.analyze(patient_data)
        
        result = TriageResult(
            path=llm_result.get('category', 'uncertain'),
            confidence=llm_result.get('confidence', 0.5),
            confidence_level='medium' if llm_result.get('confidence', 0) >= 0.6 else 'low',
            uncertainty_reason=llm_result.get('reasoning'),
            recommended_tests=llm_result.get('recommended_tests', []),
            metadata={
                'method': 'llm_fallback',
                'execution_time_ms': int((time.time() - start_time) * 1000),
                'rule_matches_count': len(rule_results)
            }
        )
        
        logger.info(f"Triage LLM fallback: {llm_result.get('category', 'uncertain')}")
        return result
    
    def _check_clinical_rare_clue(self, patient_data: Dict) -> bool:
        """
        检查患者数据中是否有罕见病临床线索
        
        用于在insufficient_data情况下判断是否可能为罕见病
        
        线索包括：
        1. 年轻患者（<40岁）+ 肝功能显著异常（ALT/AST>80）
        2. 有神经系统症状（手抖、言语不清、行为改变）
        3. 眼科检查发现K-F环
        4. 铜蓝蛋白降低（<0.20 g/L）
        5. 女性+IgG显著升高（>15 g/L）+ 转氨酶升高
        
        Returns:
            bool: 是否有罕见病临床线索
        """
        age = patient_data.get('age', 100)
        labs = patient_data.get('labs', {})
        symptoms = patient_data.get('symptoms', {})
        eye_exam = patient_data.get('eye_exam', {})
        gender = patient_data.get('gender', '')
        
        # 线索1：年轻+肝功能显著异常（Wilson病、AIH等）
        if age < 40:
            alt = labs.get('ALT', 0)
            ast = labs.get('AST', 0)
            if alt > 80 or ast > 80:
                return True
        
        # 线索2：神经系统症状（Wilson病）
        if symptoms.get('tremor') or symptoms.get('dysarthria') or symptoms.get('behavioral_changes'):
            return True
        
        # 线索3：K-F环阳性（Wilson病确诊级体征）
        if eye_exam.get('kf_ring') == 'positive':
            return True
        
        # 线索4：铜蓝蛋白降低（Wilson病）
        ceruloplasmin = labs.get('ceruloplasmin')
        if ceruloplasmin is not None and ceruloplasmin < 0.20:
            return True
        
        # 线索5：女性+IgG显著升高+转氨酶升高（AIH）
        if gender == 'female':
            igg = labs.get('IgG', 0)
            alt = labs.get('ALT', 0)
            if igg > 15 and alt > 40:
                return True
        
        return False
    
    def get_rules_status(self) -> Dict:
        """获取规则加载状态"""
        return {
            'common_rules_count': len(self.rule_engine.common_rules) - 2 if self.rule_engine.common_rules else 0,
            'rare_rules_count': len(self.rule_engine.rare_rules) - 2 if self.rule_engine.rare_rules else 0,
            'last_load_time': self.rule_engine.last_load_time,
            'rules_dir': str(self.rule_engine.rules_dir)
        }


# ==================== 使用示例 ====================
if __name__ == "__main__":
    import asyncio
    
    # 示例患者数据（已修复字段名和规则匹配问题）
    TEST_PATIENTS = [
    # 1. 典型非酒精性脂肪肝（高置信常见病 → 快速通道）
    {
        "age": 45,
        "gender": "male",
        "bmi": 33.5,
        "chief_complaint": "体检发现转氨酶升高",
        "history": {
            "alcohol_intake_weekly": 0,  # 规则期望的字段名
            "drinking_years": 0,
            "medication_history": "无",
            "viral_hepatitis": False,
            "autoimmune_disease": False
        },
        "symptoms": {"fatigue": True},
        "labs": {
            "ALT": 82, "AST": 61, "GGT": 70,
            "HBsAg": "negative", "anti_HCV": "negative"
        },
        "ultrasound": {"findings": "中度脂肪肝，肝回声增强"},  # 添加关键词匹配规则
        "eye_exam": {}
    },
    # 2. 典型酒精性肝病（中置信常见病 → 常规通道）
    # 修复：确保不会触发AIH（缺少ANA阳性）
    {
        "age": 53,
        "gender": "male",
        "bmi": 27.2,
        "chief_complaint": "乏力、食欲差",
        "history": {
            "alcohol_intake_weekly": 450,  # 酒精摄入高，AIH规则要求<140
            "drinking_years": 18,
            "medication_history": "无",
            "viral_hepatitis": False
        },
        "symptoms": {"fatigue": True, "anorexia": True},
        "labs": {
            "ALT": 90, "AST": 195, "GGT": 220,
            "AST_ALT_ratio": 2.17, "HBsAg": "negative",
            "ANA": "negative",  # 明确阴性，排除AIH
            "IgG": 11.0  # 正常范围
        },
        "ultrasound": {"findings": "肝实质增粗"},
        "eye_exam": {}
    },
    # 3. 肝豆状核变性（罕见病 → 触发罕见病预警）
    # 修复：使用正确的字段名ceruloplasmin（小写），并确保Wilson病得分最高
    {
        "age": 16,
        "gender": "female",
        "bmi": 17.9,
        "chief_complaint": "手抖、肝功能异常",
        "history": {
            "alcohol_intake_weekly": 0,
            "drinking_years": 0,
            "medication_history": "无",
            "viral_hepatitis": False,
            "family_history": "有肝病家族史"
        },
        "symptoms": {"tremor": True, "fatigue": True},
        "labs": {
            "ALT": 130, "AST": 101,
            "ceruloplasmin": 0.08,  # 显著降低（g/L），使用小写字段名
            "ANA": "negative",  # 排除AIH
            "HBsAg": "negative"
        },
        "ultrasound": {"findings": "肝硬化早期"},
        "eye_exam": {"kf_ring": "positive"}
    },
    # 4. 核心检查缺失（数据不足 → 输出针对性补检）
    # 修复：缺少ANA/SMA，AIH规则要求ANA阳性为必要条件
    {
        "age": 38,
        "gender": "female",
        "bmi": 23.1,
        "chief_complaint": "反复转氨酶升高",
        "history": {
            "alcohol_intake_weekly": 0,
            "drinking_years": 0,
            "medication_history": "无",
            "viral_hepatitis": False
        },
        "symptoms": {"fatigue": True},
        "labs": {
            "ALT": 160, "AST": 142, "IgG": 29.3,
            # 缺少ANA/SMA，AIH规则要求ANA阳性
            "HBsAg": "negative", "anti_HCV": "negative"
        },
        "ultrasound": {"findings": "肝回声增粗"},
        "eye_exam": {}
    },
    # 5. 非典型病例（规则无匹配 → LLM兜底）
    {
        "age": 31,
        "gender": "female",
        "bmi": 22.3,
        "chief_complaint": "间断皮肤黄染",
        "history": {
            "alcohol_intake_weekly": 0,
            "drinking_years": 0,
            "medication_history": "间断服中药",
            "viral_hepatitis": False
        },
        "symptoms": {"jaundice": True, "fatigue": True},
        "labs": {
            "ALT": 72, "AST": 58, "TBil": 36.5,
            "HBsAg": "negative", "anti_HCV": "negative",
            "ANA": "weak_positive", "SMA": "negative"
        },
        "ultrasound": {"findings": "肝脏形态正常"},
        "eye_exam": {}
    }
]
    
    async def test_triage():
        triage = IntelligentTriage(rules_dir="/data01/shenxf/Agent/medical-agent/rules")
        # 批量测试5例患者
        for i, patient in enumerate(TEST_PATIENTS, 1):
            print(f"\n===== 第{i}例患者测试结果 =====")
            res = await triage.triage(patient)
            print(f"分诊路径：{res.path}")
            print(f"诊断结果：{res.diagnosis}")
            print(f"置信等级：{res.confidence_level}")
            print(f"罕见病预警：{res.is_rare_disease_alert}")
            print(f"推荐检查：{res.recommended_tests}")
            print(f"执行分支：{res.metadata.get('method')}")

    asyncio.run(test_triage())
