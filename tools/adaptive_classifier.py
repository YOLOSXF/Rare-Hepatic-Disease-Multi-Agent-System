"""
自适应病例分类器
参考 HEAL 项目实现

功能：
1. 根据病历复杂度自动分为简单/中等/复杂
2. 支持 LLM 分类和规则分类
3. 用于 L2 分诊路由决策
"""

from typing import Dict, Any, Optional
from loguru import logger
import json


class AdaptiveCaseClassifier:
    """
    自适应病例分类器
    
    根据病历复杂度自动分为三类：
    - 简单：症状明确、病情稳定、特征典型
    - 中等：症状模糊、指标波动、个体差异
    - 复杂：多重异常、结果不一致、需要专家会诊
    """
    
    def __init__(self, llm_client=None):
        """
        初始化分类器
        
        Args:
            llm_client: LLM 客户端（可选）
        """
        self.llm_client = llm_client
        self._llm_initialized = False
    
    def _get_llm_client(self):
        """懒加载 LLM 客户端"""
        if not self._llm_initialized:
            from core.llm_client import LLMClient
            self.llm_client = LLMClient.from_env()
            self._llm_initialized = True
            logger.info(f"AdaptiveClassifier LLM initialized: {self.llm_client.model}")
        return self.llm_client
    
    def classify(self, patient_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        分类病历复杂度
        
        Args:
            patient_data: 患者数据
        
        Returns:
            分类结果
        """
        # 提取特征
        features = self._extract_features(patient_data)
        
        # 使用 LLM 分类
        try:
            llm = self._get_llm_client()
            result = self._classify_with_llm(features, patient_data, llm)
            logger.info(f"Classified case as {result['complexity']} using LLM")
            return result
        except Exception as e:
            logger.error(f"LLM classification failed: {e}")
            # 降级：使用规则分类
            result = self._classify_with_rules(features)
            logger.info(f"Classified case as {result['complexity']} using rules")
            return result
    
    def _extract_features(self, patient_data: Dict) -> Dict[str, bool]:
        """
        提取病历特征
        
        Args:
            patient_data: 患者数据
        
        Returns:
            特征字典
        """
        features = {
            "疾病特征明确": False,
            "病情稳定": True,
            "特征典型": False,
            "多重异常指标": False,
            "症状复杂性": False,
            "病史复杂性": False,
            "检查结果不一致": False,
            "症状模糊性": False,
            "生物标志物模糊性": False,
            "个体差异复杂性": False,
            "检查结果不确定性": False,
        }
        
        # 分析症状
        symptoms = patient_data.get("symptoms", {})
        symptom_count = sum(1 for v in symptoms.values() if v)
        
        if symptom_count <= 3:
            features["疾病特征明确"] = True
            features["特征典型"] = True
        elif symptom_count >= 6:
            features["症状复杂性"] = True
            features["多重异常指标"] = True
        
        # 分析检验结果
        labs = patient_data.get("labs", {})
        abnormal_count = 0
        
        # 简化判断：超过正常值 2 倍为异常
        lab_ranges = {
            "ALT": (0, 40),
            "AST": (0, 40),
            "TBil": (3.4, 20.5),
            "ALP": (40, 125),
            "GGT": (0, 60),
        }
        
        for test, (low, high) in lab_ranges.items():
            value = labs.get(test)
            if value:
                if value > high * 2 or value < low * 0.5:
                    abnormal_count += 1
        
        if abnormal_count >= 4:
            features["多重异常指标"] = True
            features["生物标志物模糊性"] = True
        elif abnormal_count >= 2:
            features["检查结果不确定性"] = True
        
        # 分析病史
        history = patient_data.get("history", {})
        if history.get("medication_history") or history.get("liver_disease_history"):
            features["病史复杂性"] = True
        
        # 分析年龄
        age = patient_data.get("age")
        if age and (age < 18 or age > 65):
            features["个体差异复杂性"] = True
        
        # 判断病情稳定性
        if features["多重异常指标"] or features["检查结果不一致"]:
            features["病情稳定"] = False
        
        return features
    
    def _classify_with_llm(self, features: Dict, patient_data: Dict, llm) -> Dict:
        """
        使用 LLM 分类
        
        Args:
            features: 特征字典
            patient_data: 患者数据
            llm: LLM 客户端
        
        Returns:
            分类结果
        """
        system_prompt = """你是一名肝病分类专家，请根据患者特征将病历分为简单、中等、复杂三类。

分类标准：
1. 简单病历：
   - 疾病特征明确，具有较高的识别度
   - 病情稳定、特征典型
   - 症状少（≤3 个），检验指标异常少（<2 项）

2. 中等病历：
   - 症状和生物标志物的模糊性或交叉性
   - 个体差异的复杂性（年龄、性别、病史等）
   - 检查结果的不确定性（临界值）
   - 症状中等（4-5 个），检验指标异常中等（2-3 项）

3. 复杂病历：
   - 多重异常指标（≥4 项）
   - 症状和病史的复杂性
   - 影像学或实验室检查结果不一致
   - 症状多（≥6 个），需要专家会诊

输出格式（JSON）：
{
    "complexity": "简单/中等/复杂",
    "confidence": 0.0-1.0,
    "reasoning": "分类理由",
    "recommended_track": "common_track/rare_track/uncertain_track"
}
"""
        
        # 构建患者特征描述
        feature_text = "患者特征：\n"
        for feature, value in features.items():
            if value:
                feature_text += f"- {feature}\n"
        
        feature_text += f"\n年龄：{patient_data.get('age', '未知')}\n"
        feature_text += f"性别：{patient_data.get('gender', '未知')}\n"
        feature_text += f"主诉：{patient_data.get('chief_complaint', '未知')}\n"
        
        response = llm.complete(
            prompt=feature_text,
            system_prompt=system_prompt,
            max_tokens=300
        )
        
        # 解析 JSON
        try:
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()
            
            result = json.loads(response)
            
            # 验证结果
            complexity = result.get("complexity", "中等")
            if complexity not in ["简单", "中等", "复杂"]:
                complexity = "中等"
            
            return {
                "complexity": complexity,
                "confidence": result.get("confidence", 0.7),
                "reasoning": result.get("reasoning", ""),
                "recommended_track": result.get("recommended_track", "common_track"),
                "features": features
            }
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            # 降级：使用规则分类
            return self._classify_with_rules(features)
    
    def _classify_with_rules(self, features: Dict) -> Dict:
        """
        使用规则分类（降级方案）
        
        Args:
            features: 特征字典
        
        Returns:
            分类结果
        """
        # 计算复杂度分数
        complexity_score = 0
        
        # 简单特征（负分）
        if features["疾病特征明确"]:
            complexity_score -= 2
        if features["病情稳定"]:
            complexity_score -= 1
        if features["特征典型"]:
            complexity_score -= 1
        
        # 复杂特征（正分）
        if features["多重异常指标"]:
            complexity_score += 3
        if features["症状复杂性"]:
            complexity_score += 2
        if features["病史复杂性"]:
            complexity_score += 1
        if features["检查结果不一致"]:
            complexity_score += 3
        if features["生物标志物模糊性"]:
            complexity_score += 2
        if features["个体差异复杂性"]:
            complexity_score += 1
        if features["检查结果不确定性"]:
            complexity_score += 1
        
        # 根据分数分类
        if complexity_score <= -2:
            complexity = "简单"
            confidence = 0.9
            track = "common_track"
        elif complexity_score <= 2:
            complexity = "中等"
            confidence = 0.7
            track = "common_track"
        else:
            complexity = "复杂"
            confidence = 0.8
            track = "rare_track" if features["多重异常指标"] else "uncertain_track"
        
        return {
            "complexity": complexity,
            "confidence": confidence,
            "reasoning": f"复杂度分数：{complexity_score}",
            "recommended_track": track,
            "features": features
        }


# ==================== 使用示例 ====================

if __name__ == "__main__":
    print("=" * 60)
    print("自适应病例分类器测试")
    print("=" * 60)
    print()
    
    # 创建分类器
    classifier = AdaptiveCaseClassifier()
    
    # 测试病例 1：简单
    case1 = {
        "age": 35,
        "gender": "male",
        "chief_complaint": "体检发现脂肪肝",
        "symptoms": {
            "fatigue": False,
            "jaundice": False,
            "abdominal_pain": False
        },
        "labs": {
            "ALT": 55,
            "AST": 45,
            "TBil": 15
        }
    }
    
    print("测试病例 1（简单）:")
    result1 = classifier.classify(case1)
    print(f"  分类：{result1['complexity']}")
    print(f"  置信度：{result1['confidence']}")
    print(f"  推荐路径：{result1['recommended_track']}")
    print()
    
    # 测试病例 2：复杂
    case2 = {
        "age": 23,
        "gender": "male",
        "chief_complaint": "乏力、黄疸 2 周，伴震颤",
        "symptoms": {
            "tremor": True,
            "jaundice": True,
            "fatigue": True,
            "dysarthria": True,
            "abdominal_pain": True,
            "behavioral_changes": True
        },
        "labs": {
            "ALT": 125,
            "AST": 98,
            "TBil": 52.5,
            "ALP": 145,
            "GGT": 78,
            "Ceruloplasmin": 0.08
        }
    }
    
    print("测试病例 2（复杂）:")
    result2 = classifier.classify(case2)
    print(f"  分类：{result2['complexity']}")
    print(f"  置信度：{result2['confidence']}")
    print(f"  推荐路径：{result2['recommended_track']}")
    print()
    
    print("=" * 60)
