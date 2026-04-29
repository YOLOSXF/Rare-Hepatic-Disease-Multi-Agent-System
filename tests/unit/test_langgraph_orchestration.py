"""
LangGraph 编排测试
测试多智能体协作流程
"""

import asyncio
import sys
sys.path.insert(0, '/data01/shenxf/Agent/medical-agent')

from core.langgraph_orchestrator import LangGraphOrchestrator
from loguru import logger


# 配置日志
logger.remove()
logger.add(lambda msg: print(msg, end=''), level="INFO", format="{message}")


def print_report(report: dict):
    """美化输出报告"""
    print("\n" + "="*70)
    print("📊 LangGraph 诊断报告")
    print("="*70)
    
    print(f"患者 ID: {report.get('patient_id', 'N/A')}")
    print(f"主诉：{report.get('chief_complaint', 'N/A')}")
    print(f"分诊路径：{report.get('triage_path', 'N/A')}")
    
    # 诊断
    primary = report.get('primary_diagnosis')
    if primary:
        if isinstance(primary, dict):
            print(f"诊断：{primary.get('disease', 'N/A')}")
            print(f"置信度：{primary.get('confidence', 0):.2f}")
        else:
            print(f"诊断：{primary}")
    
    # 转诊建议
    referral = report.get('referral_recommendation', {})
    if isinstance(referral, dict):
        print(f"\n转诊建议：{referral.get('recommendation', 'N/A')}")
        print(f"紧急程度：{referral.get('urgency', 'N/A')}")
    
    # 分诊信息
    triage = report.get('triage', {})
    if triage:
        print(f"\n分诊详情:")
        print(f"  诊断：{triage.get('diagnosis', 'N/A')}")
        print(f"  置信度：{triage.get('confidence', 0):.2f}")
        print(f"  罕见病警示：{'⚠️ 是' if triage.get('is_rare_disease_alert') else '否'}")
        
        if triage.get('recommended_tests'):
            print(f"  推荐检查：{', '.join(triage['recommended_tests'][:3])}")
    
    # 元数据
    metadata = report.get('metadata', {})
    print(f"\n流程信息:")
    print(f"  数据完整性：{metadata.get('data_completeness', 0):.2f}")
    print(f"  追问问题数：{metadata.get('questions_asked', 0)}")
    print(f"  方法：{metadata.get('method', 'N/A')}")
    
    print("="*70 + "\n")


async def test_case_1_complete_data():
    """测试用例 1：数据完整 - 跳过信息收集"""
    print("\n【测试用例 1】数据完整 - 跳过信息收集")
    
    patient = {
        "patient_id": "P001",
        "age": 45,
        "gender": "male",
        "bmi": 31.2,
        "chief_complaint": "体检发现脂肪肝",
        "history": {
            "alcohol_intake_weekly": 50,
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
    
    orchestrator = LangGraphOrchestrator(
        rules_dir="/data01/shenxf/Agent/medical-agent/rules",
        config_path="/data01/shenxf/Agent/medical-agent/config.yaml"
    )
    
    report = await orchestrator.run_diagnosis(patient)
    print_report(report)
    
    assert report.get('success') == True, "应该成功"
    assert report.get('triage_path') in ['common', 'common_fast_path'], "应走常见病路径"
    print("✅ 测试通过：数据完整流程")


async def test_case_2_incomplete_data():
    """测试用例 2：数据不完整 - 触发信息收集"""
    print("\n【测试用例 2】数据不完整 - 触发信息收集")
    
    patient = {
        "patient_id": "P002",
        "age": 52,
        "gender": "male",
        "chief_complaint": "腹胀、乏力",
        "history": {
            "alcohol_intake_weekly": 350
        },
        "labs": {
            "ALT": 85,
            "AST": 180,
            "TBil": 28.5
        }
        # 缺少 ultrasound
    }
    
    orchestrator = LangGraphOrchestrator(
        rules_dir="/data01/shenxf/Agent/medical-agent/rules",
        config_path="/data01/shenxf/Agent/medical-agent/config.yaml"
    )
    
    report = await orchestrator.run_diagnosis(patient)
    print_report(report)
    
    metadata = report.get('metadata', {})
    print(f"数据完整性：{metadata.get('data_completeness', 0):.2f}")
    print(f"追问问题数：{metadata.get('questions_asked', 0)}")
    
    assert report.get('success') == True, "应该成功"
    print("✅ 测试通过：数据不完整流程")


async def test_case_3_rare_disease_alert():
    """测试用例 3：罕见病警示"""
    print("\n【测试用例 3】罕见病警示 - Wilson 病疑似")
    
    patient = {
        "patient_id": "P003",
        "age": 22,
        "gender": "male",
        "chief_complaint": "双手震颤、黄疸",
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
            "TBil": 45.8,
            "ceruloplasmin": 0.12
        },
        "eye_exam": {
            "kf_ring": "positive"
        }
    }
    
    orchestrator = LangGraphOrchestrator(
        rules_dir="/data01/shenxf/Agent/medical-agent/rules",
        config_path="/data01/shenxf/Agent/medical-agent/config.yaml"
    )
    
    report = await orchestrator.run_diagnosis(patient)
    print_report(report)
    
    triage = report.get('triage', {})
    assert triage.get('is_rare_disease_alert') == True, "应触发罕见病警示"
    assert 'Wilson' in str(triage.get('diagnosis', '')), "应提示 Wilson 病"
    print("✅ 测试通过：罕见病警示")


async def test_case_4_thread_continuation():
    """测试用例 4：断点续传（同一 thread_id）"""
    print("\n【测试用例 4】断点续传测试")
    
    patient = {
        "patient_id": "P004",
        "age": 38,
        "gender": "female",
        "chief_complaint": "乏力、皮肤黄染",
        "history": {
            "autoimmune_disease": True
        },
        "labs": {
            "ALT": 156,
            "AST": 142,
            "IgG": 18.5,
            "ANA": "positive"
        }
    }
    
    orchestrator = LangGraphOrchestrator(
        rules_dir="/data01/shenxf/Agent/medical-agent/rules",
        config_path="/data01/shenxf/Agent/medical-agent/config.yaml"
    )
    
    # 第一次诊断
    thread_id = "test_thread_001"
    report1 = await orchestrator.run_diagnosis(patient, thread_id=thread_id)
    print(f"第一次诊断完成：{report1.get('triage_path')}")
    
    # 第二次诊断（使用相同 thread_id）
    report2 = await orchestrator.run_diagnosis(patient, thread_id=thread_id)
    print(f"第二次诊断完成：{report2.get('triage_path')}")
    
    assert report1.get('success') == True, "第一次应该成功"
    assert report2.get('success') == True, "第二次应该成功"
    print("✅ 测试通过：断点续传")


async def run_all_tests():
    """运行所有测试"""
    print("\n" + "🚀"*35)
    print("LangGraph 编排测试")
    print("🚀"*35)
    
    try:
        await test_case_1_complete_data()
        await test_case_2_incomplete_data()
        await test_case_3_rare_disease_alert()
        await test_case_4_thread_continuation()
        
        print("\n" + "✅"*35)
        print("所有 LangGraph 测试通过！")
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
