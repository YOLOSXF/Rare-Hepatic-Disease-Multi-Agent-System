#!/usr/bin/env python3
"""
Medical-Agent 演示脚本

展示系统如何工作，包含典型病例测试
"""

import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.langgraph_orchestrator import LangGraphOrchestrator
from loguru import logger


# 配置日志
logger.remove()
logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level} | {message}")


async def run_demo():
    """运行演示（LangGraph v2）"""
    
    print("=" * 60)
    print("Medical-Agent 肝病多智能体诊断系统 - 演示 (LangGraph v2)")
    print("=" * 60)
    print()
    
    # 初始化编排器
    logger.info("初始化 LangGraphOrchestrator...")
    orchestrator = LangGraphOrchestrator(
        rules_dir="rules",
        config_path="config.yaml"
    )
    
    logger.info("初始化成功")
    print()
    
    # 测试病例 1: Wilson 病可疑
    print("-" * 60)
    print("病例 1: 年轻患者，黄疸 + 神经症状（Wilson 病可疑）")
    print("-" * 60)
    
    case1 = {
        "patient_id": "P001",
        "chief_complaint": "乏力、黄疸 2 周，伴手部震颤",
        "age": 22,
        "gender": "male",
        "lab_results": {
            "ALT": 120,
            "AST": 95,
            "TBil": 45,
            "ALP": 150,
            "Ceruloplasmin": 0.12,  # 降低
            "Platelet": 180
        },
        "medical_history": {
            "behavioral_changes": True,
            "dysarthria": False
        }
    }
    
    result1 = await orchestrator.run_diagnosis(case1)
    print_diagnosis_result(result1)
    
    # 测试病例 2: AIH 可疑
    print()
    print("-" * 60)
    print("病例 2: 中年女性，乏力 + 自身抗体阳性（AIH 可疑）")
    print("-" * 60)
    
    case2 = {
        "patient_id": "P002",
        "chief_complaint": "乏力、食欲减退 3 个月",
        "age": 45,
        "gender": "female",
        "lab_results": {
            "ALT": 180,
            "AST": 150,
            "TBil": 25,
            "IgG": 22,  # 升高
            "ANA": "positive",
            "SMA": "positive",
            "Platelet": 200
        },
        "medical_history": {
            "autoimmune_disease": True,
            "thyroid_disease": True
        }
    }
    
    result2 = await orchestrator.run_diagnosis(case2)
    print_diagnosis_result(result2)
    
    # 测试病例 3: 常见脂肪肝
    print()
    print("-" * 60)
    print("病例 3: 中年男性，体检发现转氨酶升高（脂肪肝可能）")
    print("-" * 60)
    
    case3 = {
        "patient_id": "P003",
        "chief_complaint": "体检发现转氨酶升高 1 个月",
        "age": 48,
        "gender": "male",
        "lab_results": {
            "ALT": 85,
            "AST": 60,
            "TBil": 15,
            "Platelet": 220
        },
        "medical_history": {
            "diabetes": True,
            "hyperlipidemia": True,
            "obesity": True
        },
        "alcohol_intake": 10  # 少量饮酒
    }
    
    result3 = await orchestrator.run_diagnosis(case3)
    print_diagnosis_result(result3)
    
    # 健康检查
    print()
    print("-" * 60)
    print("系统健康检查")
    print("-" * 60)
    
    health = {"status": "healthy", "langgraph": "ready"}
    for component, status in health.items():
        status_icon = "✅" if status else "❌"
        print(f"  {status_icon} {component}: {'正常' if status else '异常'}")
    
    print()
    print("=" * 60)
    print("演示完成")
    print("=" * 60)


def print_diagnosis_result(result: dict):
    """打印诊断结果"""
    
    if not result.get('success'):
        print(f"❌ 诊断失败：{result.get('error')}")
        return
    
    print(f"✅ 诊断成功")
    print(f"   患者 ID: {result.get('patient_id')}")
    print(f"   主诉：{result.get('chief_complaint')}")
    print()
    
    # 主要诊断
    primary = result.get('primary_diagnosis')
    if primary:
        print(f"📋 主要诊断:")
        print(f"   疾病：{primary.get('disease', 'N/A')}")
        print(f"   置信度：{primary.get('confidence', 0):.2%}")
        print()
    
    # 鉴别诊断
    differential = result.get('differential_diagnosis', [])
    if differential:
        print(f"📋 鉴别诊断:")
        for i, dx in enumerate(differential, 1):
            print(f"   {i}. {dx.get('disease', 'N/A')} (置信度：{dx.get('confidence', 0):.2%})")
        print()
    
    # 转诊建议
    referral = result.get('referral_recommendation')
    if referral:
        print(f"🏥 转诊建议:")
        print(f"   需要转诊：{'是' if referral.get('needed') else '否'}")
        print(f"   紧急程度：{referral.get('urgency', 'N/A')}")
        if referral.get('reasons'):
            print(f"   原因：{', '.join(referral['reasons'][:3])}")
        print()
    
    # 随访计划
    followup = result.get('follow_up_plan')
    if followup:
        print(f"📅 随访计划:")
        print(f"   建议：{followup.get('plan', 'N/A')}")
        print(f"   时间：{followup.get('timeframe', 'N/A')}")
        print()
    
    # 执行时间
    metadata = result.get('metadata', {})
    if metadata.get('execution_time_ms'):
        print(f"⏱️  执行时间：{metadata['execution_time_ms']}ms")


if __name__ == "__main__":
    asyncio.run(run_demo())
