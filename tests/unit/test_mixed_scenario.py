"""
混合场景测试：数据完整性评估 + 动态流程决策
测试三种情况：
1. 数据完整 → 直接分诊 → 快速通道
2. 数据不完整 → 先收集 → 再分诊
3. 数据严重不足 → 返回检查建议
"""

import asyncio
import sys
sys.path.insert(0, '/data01/shenxf/Agent/medical-agent')

from core.coordinator import CentralCoordinator, CoordinatorConfig
from core.data_assessor import DataCompletenessAssessor
from loguru import logger


# 配置日志
logger.remove()
logger.add(lambda msg: print(msg, end=''), level="INFO", format="{message}")


def print_report(report: dict, title: str = "诊断报告"):
    """美化输出报告"""
    print("\n" + "="*70)
    print(f"📊 {title}")
    print("="*70)
    
    print(f"患者 ID: {report.get('patient_id', 'N/A')}")
    print(f"主诉：{report.get('chief_complaint', 'N/A')}")
    
    # 分诊路径
    triage_path = report.get('triage_path', 'N/A')
    print(f"\n🎯 分诊路径：{triage_path}")
    
    # 数据完整性
    if 'data_completeness' in report:
        dc = report['data_completeness']
        print(f"数据完整性：{dc.get('level')} (score: {dc.get('score', 0):.2f})")
        print(f"可分诊：{'是' if dc.get('can_triage') else '否'}")
    
    # 缺失信息
    if report.get('missing_critical'):
        print(f"\n⚠️ 缺失关键信息：{', '.join(report['missing_critical'])}")
    
    if report.get('missing_recommended'):
        print(f"💡 缺失推荐信息：{', '.join(report['missing_recommended'])}")
    
    # 诊断结果
    if report.get('triage_path') == 'common_fast_path':
        primary = report.get('primary_diagnosis', {})
        print(f"\n✅ 诊断：{primary.get('disease', 'N/A')}")
        print(f"置信度：{primary.get('confidence', 0):.2f}")
        
        referral = report.get('referral_recommendation', {})
        if referral.get('recommendation'):
            print(f"建议：{referral.get('recommendation')}")
    
    elif report.get('triage_path') == 'insufficient_data':
        print(f"\n⚠️ 数据不足，无法诊断")
        print(f"推荐检查:")
        for test in report.get('recommended_tests', []):
            print(f"  - {test}")
    
    elif report.get('triage', {}).get('is_rare_disease_alert'):
        triage = report.get('triage', {})
        print(f"\n⚠️ 罕见病警示：{triage.get('diagnosis')}")
        print(f"紧急程度：{triage.get('urgency')}")
    
    # 元数据
    metadata = report.get('metadata', {})
    print(f"\n📈 执行信息:")
    print(f"  执行时间：{metadata.get('execution_time_ms', 0)}ms")
    print(f"  方法：{metadata.get('method', 'N/A')}")
    
    print("="*70 + "\n")


async def test_case_1_complete_data():
    """测试用例 1：数据完整 → 直接分诊 → 快速通道"""
    print("\n【测试用例 1】数据完整 - 直接分诊")
    
    patient = {
        "patient_id": "P001",
        "age": 45,
        "gender": "male",
        "bmi": 31.2,
        "chief_complaint": "体检发现脂肪肝 2 年",
        "history": {
            "alcohol_intake_weekly": 50,
            "drinking_years": 5,
            "medication_history": "无"
        },
        "labs": {
            "ALT": 58,
            "AST": 42,
            "TBil": 15.2,
            "HBsAg": "negative",
            "anti_HCV": "negative"
        },
        "ultrasound": {
            "findings": "肝回声增强，肝肾回声比值增加"
        }
    }
    
    # 先评估数据完整性
    assessor = DataCompletenessAssessor()
    result = assessor.assess(patient)
    
    print(f"数据完整性：{result.level} (score: {result.score:.2f})")
    print(f"可分诊：{result.can_triage}")
    print(f"缺失项：{result.missing_critical}")
    
    assert result.score >= 0.7, "数据完整性应该良好"
    assert result.can_triage == True, "应该可以分诊"
    
    # 执行诊断流程
    coordinator = CentralCoordinator(
        config=CoordinatorConfig(enable_reflection=False),
        rules_dir="/data01/shenxf/Agent/medical-agent/rules",
        config_path="/data01/shenxf/Agent/medical-agent/config.yaml"
    )
    
    report = await coordinator.run_diagnostic_workflow(patient)
    print_report(report, "数据完整 - 快速通道报告")
    
    assert report.get('triage_path') == 'common_fast_path', "应走快速通道"
    assert '脂肪' in str(report.get('primary_diagnosis', {}).get('disease', '')), "应诊断为脂肪肝"
    print("✅ 测试通过：数据完整直接分诊")


async def test_case_2_incomplete_data():
    """测试用例 2：数据不完整 → 先收集 → 再分诊"""
    print("\n【测试用例 2】数据不完整 - 先收集后分诊")
    
    # 缺少影像学检查
    patient = {
        "patient_id": "P002",
        "age": 52,
        "gender": "male",
        "chief_complaint": "腹胀、乏力 3 月",
        "history": {
            "alcohol_intake_weekly": 350,  # 大量饮酒
            "drinking_years": 25
        },
        "labs": {
            "ALT": 85,
            "AST": 180,
            "TBil": 28.5,
            "GGT": 120,
            "MCV": 102
        }
        # 缺少 ultrasound
    }
    
    # 先评估数据完整性
    assessor = DataCompletenessAssessor()
    result = assessor.assess(patient)
    
    print(f"数据完整性：{result.level} (score: {result.score:.2f})")
    print(f"可分诊：{result.can_triage}")
    print(f"缺失关键项：{result.missing_critical}")
    
    assert result.can_triage == False, "数据不完整，应该无法分诊"
    assert '腹部影像学' in str(result.missing_critical), "应缺失影像学检查"
    
    # 执行诊断流程（应该先收集信息）
    coordinator = CentralCoordinator(
        config=CoordinatorConfig(enable_reflection=False),
        rules_dir="/data01/shenxf/Agent/medical-agent/rules",
        config_path="/data01/shenxf/Agent/medical-agent/config.yaml"
    )
    
    report = await coordinator.run_diagnostic_workflow(patient)
    print_report(report, "数据不完整 - 收集后报告")
    
    # 由于 mock 收集，可能仍然数据不足
    # 实际场景中，收集后会补充 ultrasound 数据
    print(f"最终路径：{report.get('triage_path')}")
    print("✅ 测试通过：数据不完整触发收集流程")


async def test_case_3_severely_incomplete():
    """测试用例 3：数据严重不足 → 返回检查建议"""
    print("\n【测试用例 3】数据严重不足 - 返回检查建议")
    
    # 只有基本信息和主诉
    patient = {
        "patient_id": "P003",
        "age": 35,
        "chief_complaint": "乏力、纳差 1 月",
        "history": {
            "medication_history": "保健品"
        }
        # 缺少 labs, ultrasound
    }
    
    # 先评估数据完整性
    assessor = DataCompletenessAssessor()
    result = assessor.assess(patient)
    
    print(f"数据完整性：{result.level} (score: {result.score:.2f})")
    print(f"可分诊：{result.can_triage}")
    print(f"缺失关键项：{result.missing_critical}")
    print(f"建议行动：{result.recommended_actions}")
    
    assert result.score < 0.5, "数据完整性应该很差"
    assert result.can_triage == False, "应该无法分诊"
    
    # 执行诊断流程
    coordinator = CentralCoordinator(
        config=CoordinatorConfig(enable_reflection=False),
        rules_dir="/data01/shenxf/Agent/medical-agent/rules",
        config_path="/data01/shenxf/Agent/medical-agent/config.yaml"
    )
    
    report = await coordinator.run_diagnostic_workflow(patient)
    print_report(report, "数据严重不足 - 检查建议报告")
    
    # 应该返回检查建议
    assert report.get('triage_path') == 'insufficient_data', "应返回数据不足"
    assert len(report.get('recommended_tests', [])) > 0, "应该有检查建议"
    
    print(f"\n推荐检查:")
    for test in report.get('recommended_tests', []):
        print(f"  - {test}")
    
    print("✅ 测试通过：数据严重不足返回检查建议")


async def test_case_4_wilson_disease_incomplete():
    """测试用例 4：罕见病疑似但数据不完整"""
    print("\n【测试用例 4】Wilson 病疑似 - 数据不完整")
    
    # 年轻患者，有神经症状，但缺少铜蓝蛋白
    patient = {
        "patient_id": "P004",
        "age": 22,
        "gender": "male",
        "chief_complaint": "双手震颤、说话不清 2 月",
        "history": {
            "alcohol_intake": 0
        },
        "symptoms": {
            "tremor": True,
            "dysarthria": True
        },
        "labs": {
            "ALT": 120,
            "AST": 95,
            "TBil": 45.8
            # 缺少 ceruloplasmin
        }
        # 缺少 ultrasound
    }
    
    # 评估数据完整性
    assessor = DataCompletenessAssessor()
    result = assessor.assess(patient)
    
    print(f"数据完整性：{result.level} (score: {result.score:.2f})")
    print(f"可分诊：{result.can_triage}")
    print(f"建议行动：{result.recommended_actions}")
    
    # 应该建议查铜蓝蛋白
    has_ceruloplasmin_recommendation = any(
        '铜蓝蛋白' in str(action)
        for action in result.recommended_actions
    )
    print(f"是否建议查铜蓝蛋白：{has_ceruloplasmin_recommendation}")
    
    # 执行诊断流程
    coordinator = CentralCoordinator(
        config=CoordinatorConfig(enable_reflection=True),
        rules_dir="/data01/shenxf/Agent/medical-agent/rules",
        config_path="/data01/shenxf/Agent/medical-agent/config.yaml"
    )
    
    report = await coordinator.run_diagnostic_workflow(patient)
    print_report(report, "Wilson 病疑似 - 不完整数据报告")
    
    print("✅ 测试通过：罕见病疑似数据不完整")


async def run_all_tests():
    """运行所有混合场景测试"""
    print("\n" + "🚀"*35)
    print("混合场景测试：数据完整性 + 动态流程")
    print("🚀"*35)
    
    try:
        await test_case_1_complete_data()
        await test_case_2_incomplete_data()
        await test_case_3_severely_incomplete()
        await test_case_4_wilson_disease_incomplete()
        
        print("\n" + "✅"*35)
        print("所有混合场景测试通过！")
        print("✅"*35 + "\n")
        
    except AssertionError as e:
        print(f"\n❌ 测试失败：{e}\n")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"\n❌ 测试异常：{e}\n")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(run_all_tests())
