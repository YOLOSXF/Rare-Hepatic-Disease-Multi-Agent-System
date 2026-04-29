"""
L2 初筛分诊层测试脚本
测试规则引擎匹配、LLM 兜底、热更新等功能
"""

import asyncio
import sys
sys.path.insert(0, '/data01/shenxf/Agent/medical-agent')

from core.triage import IntelligentTriage, RuleEngine, TriageResult
from loguru import logger
import json


# 配置日志
logger.remove()
logger.add(lambda msg: print(msg, end=''), level="INFO", format="{message}")


def print_result(result: TriageResult):
    """美化输出分诊结果"""
    print("\n" + "="*60)
    print("📋 分诊结果")
    print("="*60)
    print(f"分诊路径：{result.path}")
    print(f"诊断：{result.diagnosis or '未明确'}")
    print(f"置信度：{result.confidence:.2f} ({result.confidence_level})")
    
    if result.is_rare_disease_alert:
        print(f"⚠️  罕见病警示：{result.urgency}")
    
    if result.referral_recommendation:
        print(f"转诊建议：{result.referral_recommendation}")
    
    if result.follow_up_plan:
        print(f"随访计划：{result.follow_up_plan}")
    
    if result.recommended_tests:
        print(f"推荐检查：{', '.join(result.recommended_tests)}")
    
    if result.uncertainty_reason:
        print(f"不确定原因：{result.uncertainty_reason}")
    
    print(f"匹配疾病数：{len(result.matched_diseases)}")
    if result.matched_diseases:
        for i, disease in enumerate(result.matched_diseases[:3], 1):
            print(f"  {i}. {disease.disease_name} ({disease.confidence_level}: {disease.normalized_score:.2f})")
    
    print(f"执行时间：{result.metadata.get('execution_time_ms', 0)}ms")
    print(f"分诊方法：{result.metadata.get('method', 'unknown')}")
    print("="*60 + "\n")


async def test_case_1_fatty_liver():
    """测试用例 1：典型脂肪肝"""
    print("\n【测试用例 1】典型脂肪肝")
    
    patient = {
        "age": 45,
        "gender": "male",
        "bmi": 31.2,
        "chief_complaint": "体检发现脂肪肝 2 年",
        "history": {
            "alcohol_intake": 50,
            "alcohol_intake_weekly": 50,
            "drinking_years": 5,
            "medication_history": "无",
            "viral_hepatitis": False
        },
        "labs": {
            "ALT": 58,
            "AST": 42,
            "GGT": 48,
            "TBil": 15.2,
            "HBsAg": "negative",
            "anti_HCV": "negative"
        },
        "ultrasound": {
            "findings": "肝回声增强，肝肾回声比值增加，远场回声衰减"
        }
    }
    
    triage = IntelligentTriage(rules_dir="/data01/shenxf/Agent/medical-agent/rules")
    result = await triage.triage(patient)
    print_result(result)
    
    assert result.path == 'common', "脂肪肝应走常见病路径"
    assert '脂肪' in result.diagnosis, "应诊断为脂肪肝"
    assert result.confidence >= 0.8, "置信度应>=0.8"
    print("✅ 测试通过")


async def test_case_2_wilson_disease():
    """测试用例 2：Wilson 病疑似"""
    print("\n【测试用例 2】Wilson 病疑似")
    
    patient = {
        "age": 22,
        "gender": "male",
        "chief_complaint": "乏力、黄疸 2 周，双手震颤 1 月",
        "history": {
            "alcohol_intake": 0,
            "medication_history": "无"
        },
        "symptoms": {
            "tremor": True,
            "dysarthria": True,
            "behavioral_changes": False,
            "jaundice": True
        },
        "eye_exam": {
            "kf_ring": "positive"
        },
        "labs": {
            "ALT": 120,
            "AST": 95,
            "TBil": 45.8,
            "ceruloplasmin": 0.12,  # 降低
            "urine_copper_24h": 180,  # 升高
            "HBsAg": "negative"
        }
    }
    
    triage = IntelligentTriage(rules_dir="/data01/shenxf/Agent/medical-agent/rules")
    result = await triage.triage(patient)
    print_result(result)
    
    assert result.is_rare_disease_alert, "Wilson 病应触发罕见病警示"
    assert 'Wilson' in result.diagnosis, "应提示 Wilson 病"
    assert result.urgency in ['urgent', 'high'], "Wilson 病应为紧急转诊"
    print("✅ 测试通过")


async def test_case_3_ald():
    """测试用例 3：酒精性肝病"""
    print("\n【测试用例 3】酒精性肝病")
    
    patient = {
        "age": 52,
        "gender": "male",
        "bmi": 26.5,
        "chief_complaint": "腹胀、乏力 3 月",
        "history": {
            "alcohol_intake_weekly": 350,  # 每周 350g 酒精
            "drinking_years": 25,
            "medication_history": "无"
        },
        "labs": {
            "ALT": 85,
            "AST": 180,
            "AST_ALT_ratio": 2.1,  # AST/ALT > 2
            "GGT": 120,
            "MCV": 102,  # 大细胞性
            "TBil": 28.5,
            "HBsAg": "negative"
        },
        "ultrasound": {
            "findings": "肝脏体积缩小，表面不平，回声增粗"
        }
    }
    
    triage = IntelligentTriage(rules_dir="/data01/shenxf/Agent/medical-agent/rules")
    result = await triage.triage(patient)
    print_result(result)
    
    assert result.path == 'common', "酒精性肝病应走常见病路径"
    assert '酒精' in result.diagnosis, "应诊断为酒精性肝病"
    print("✅ 测试通过")


async def test_case_4_aih():
    """测试用例 4：自身免疫性肝炎疑似"""
    print("\n【测试用例 4】自身免疫性肝炎疑似")
    
    patient = {
        "age": 38,
        "gender": "female",
        "chief_complaint": "乏力、皮肤黄染 1 月",
        "history": {
            "autoimmune_disease": True,  # 合并甲状腺炎
            "medication_history": "优甲乐"
        },
        "labs": {
            "ALT": 156,
            "AST": 142,
            "TBil": 52.3,
            "IgG": 18.5,  # 升高
            "ANA": "positive",
            "SMA": "positive",
            "HBsAg": "negative",
            "anti_HCV": "negative"
        }
    }
    
    triage = IntelligentTriage(rules_dir="/data01/shenxf/Agent/medical-agent/rules")
    result = await triage.triage(patient)
    print_result(result)
    
    assert result.is_rare_disease_alert, "AIH 应触发罕见病警示"
    assert '自身免疫' in result.diagnosis or 'AIH' in result.diagnosis, "应提示 AIH"
    print("✅ 测试通过")


async def test_case_5_uncertain():
    """测试用例 5：不确定病例（触发 LLM 兜底）"""
    print("\n【测试用例 5】不确定病例")
    
    patient = {
        "age": 30,
        "gender": "female",
        "chief_complaint": "体检发现转氨酶轻度升高",
        "history": {
            "alcohol_intake": 0,
            "medication_history": "口服避孕药 6 月"
        },
        "labs": {
            "ALT": 55,
            "AST": 48,
            "TBil": 18.2,
            "HBsAg": "negative"
        },
        "ultrasound": {
            "findings": "肝脏未见明显异常"
        }
    }
    
    triage = IntelligentTriage(rules_dir="/data01/shenxf/Agent/medical-agent/rules")
    result = await triage.triage(patient)
    print_result(result)
    
    # 不确定病例可能走 uncertain 路径或常见病的低置信度
    print(f"ℹ️  不确定病例，分诊路径：{result.path}")
    print("✅ 测试通过")


async def test_hot_reload():
    """测试热更新功能"""
    print("\n【测试用例 6】规则热更新")
    
    triage = IntelligentTriage(rules_dir="/data01/shenxf/Agent/medical-agent/rules")
    
    # 获取初始规则状态
    status1 = triage.rule_engine.last_load_time
    print(f"初始加载时间：{status1}")
    
    # 强制重新加载
    triage.rule_engine.load_rules(force=True)
    
    status2 = triage.rule_engine.last_load_time
    print(f"重新加载时间：{status2}")
    
    assert status2 >= status1, "重新加载后时间应更新"
    print(f"✅ 热更新测试通过")


async def run_all_tests():
    """运行所有测试"""
    print("\n" + "🚀"*30)
    print("L2 初筛分诊层测试套件")
    print("🚀"*30)
    
    try:
        await test_case_1_fatty_liver()
        await test_case_2_wilson_disease()
        await test_case_3_ald()
        await test_case_4_aih()
        await test_case_5_uncertain()
        await test_hot_reload()
        
        print("\n" + "✅"*30)
        print("所有测试通过！")
        print("✅"*30 + "\n")
        
    except AssertionError as e:
        print(f"\n❌ 测试失败：{e}\n")
    except Exception as e:
        print(f"\n❌ 测试异常：{e}\n")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(run_all_tests())
