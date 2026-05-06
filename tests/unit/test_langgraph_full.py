#!/usr/bin/env python3
"""
LangGraph 完整流程测试
测试从 L1 预处理到 L5 输出的完整流程
"""

import asyncio
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.graph_orchestrator import LangGraphDiagnosticGraph
from core.medical_middleware import (
    MDTManager, DebateMediator, FalsificationEngine,
    InformationGapAssessor, GuidelineVerifier, GraphUpdater, MemoryRetriever
)
from agents import HepatologistAgent, NeurologistAgent, RheumatologistAgent, HematologistAgent
from loguru import logger

logger.remove()
logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level} | {message}")


WILSON_CASE = {
    "patient_id": "TEST_WD_LANGGRAPH_001",
    "chief_complaint": "进行性肢体震颤、言语不清 6 个月，加重伴黄疸 2 周",
    "age": 23,
    "gender": "male",
    
    "symptoms": {
        "tremor": True,
        "dysarthria": True,
        "jaundice": True,
        "behavioral_changes": True
    },
    
    "history": {
        "alcohol_intake": 0,
        "medication_history": "氟西汀 20mg qd",
        "liver_disease_history": "1 年前体检发现转氨酶升高"
    },
    
    "labs": {
        "ALT": 125,
        "AST": 98,
        "TBil": 52.5,
        "DBil": 28.3,
        "ALP": 145,
        "GGT": 78,
        "Albumin": 32,
        "PT": 15.2,
        "INR": 1.3,
        "Platelet": 95,
        "ceruloplasmin": 0.08,
        "HBsAg": "negative",
        "Anti_HCV": "negative"
    },
    
    "ultrasound": {
        "findings": "肝脏轻度增大，回声增粗，脾大"
    },
    
    "eye_exam": {
        "kf_ring": "阳性"
    },
    
    "special_tests": {
        "brain_mri": "双侧豆状核对称性异常信号"
    }
}


async def test_langgraph_workflow():
    """测试 LangGraph 完整工作流"""
    
    print("=" * 80)
    print("LangGraph 完整流程测试 - Wilson 病诊断")
    print("=" * 80)
    print()
    
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    agent_pool = {
        'HepatologistAgent': HepatologistAgent(),
        'NeurologistAgent': NeurologistAgent(),
        'RheumatologistAgent': RheumatologistAgent(),
        'HematologyAgent': HematologyAgent(),
    }
    
    logger.info("初始化 LangGraphDiagnosticGraph...")
    orchestrator = LangGraphDiagnosticGraph(
        mdt_manager=MDTManager(agent_pool=agent_pool),
        debate_mediator=DebateMediator(max_rounds=2),
        falsification_engine=FalsificationEngine(),
        gap_assessor=InformationGapAssessor(),
        guideline_verifier=GuidelineVerifier(),
        graph_updater=GraphUpdater(),
        memory_retriever=MemoryRetriever(),
    )
    
    logger.info("初始化成功")
    print()
    
    print("-" * 80)
    print("测试病例摘要")
    print("-" * 80)
    print(f"患者：{WILSON_CASE['patient_id']}")
    print(f"主诉：{WILSON_CASE['chief_complaint']}")
    print(f"年龄：{WILSON_CASE['age']}岁，性别：{WILSON_CASE['gender']}")
    print()
    print("关键指标:")
    print(f"  铜蓝蛋白：{WILSON_CASE['labs']['ceruloplasmin']} g/L")
    print(f"  ALT: {WILSON_CASE['labs']['ALT']} U/L")
    print(f"  TBil: {WILSON_CASE['labs']['TBil']} μmol/L")
    print(f"  K-F 环：{WILSON_CASE['eye_exam']['kf_ring']}")
    print()
    
    print("-" * 80)
    print("执行 LangGraph 诊断流程")
    print("-" * 80)
    print()
    
    report = await orchestrator.run_full_pipeline(WILSON_CASE)
    
    print("=" * 80)
    print("诊断结果")
    print("=" * 80)
    print()
    
    triage = report.get('triage', {})
    path = triage.get('path', 'unknown')
    print(f"分诊路径：{path}")
    
    diff_diag = report.get('differential_diagnosis', [])
    if diff_diag:
        print(f"\n候选诊断:")
        for d in diff_diag[:5]:
            disease = d.get('disease', 'N/A') if isinstance(d, dict) else str(d)
            conf = d.get('confidence', 0) if isinstance(d, dict) else 0
            print(f"  - {disease} (置信度: {conf:.2f})")
    
    primary = report.get('diagnosis')
    if primary:
        disease_name = primary.get('disease', 'N/A') if isinstance(primary, dict) else str(primary)
        conf = primary.get('confidence', 0) if isinstance(primary, dict) else 0
        print(f"\n主要诊断：{disease_name} (置信度: {conf:.2f})")
    
    referral = report.get('referral', {})
    print(f"\n转诊建议：{referral}")
    
    falsification_log = report.get('falsification_log', [])
    if falsification_log:
        print(f"\n证伪日志:")
        for entry in falsification_log:
            hyp = entry.get('hypothesis', 'N/A')
            falsified = entry.get('falsified', False)
            print(f"  - {hyp}: 被证伪={falsified}")
    
    hitl_status = report.get('hitl_status', 'normal')
    print(f"\nHITL状态：{hitl_status}")
    
    hitl_questions = report.get('hitl_questions', [])
    if hitl_questions:
        print(f"\n追问问题:")
        for q in hitl_questions:
            print(f"  - {q.get('question', '')}")
    
    print()
    print("=" * 80)
    print("验证结果")
    print("=" * 80)
    print()
    
    has_wilson = False
    if diff_diag:
        for d in diff_diag:
            disease = d.get('disease', '') if isinstance(d, dict) else str(d)
            if 'Wilson' in disease or 'wilson' in disease.lower() or '肝豆' in disease:
                has_wilson = True
                break
    
    is_rare = path in ['rare_deep_path', 'rare']
    
    print(f"1. Wilson病在候选诊断中：{'通过' if has_wilson else '未匹配'}")
    print(f"2. 罕见病路径触发：{'通过' if is_rare else '未触发'} (路径: {path})")
    print()
    
    if has_wilson or is_rare:
        print("测试通过！")
    else:
        print("测试未完全匹配，请查看上述诊断结果")
    
    print()
    print("=" * 80)
    
    os.makedirs(os.path.join(base_dir, 'tests', 'results'), exist_ok=True)
    with open(os.path.join(base_dir, 'tests', 'results', 'langgraph_wilson_test.json'), 'w', encoding='utf-8') as f:
        json.dump({
            'test_case': 'Wilson_Disease_LangGraph',
            'report': report,
            'has_wilson': has_wilson,
            'is_rare': is_rare,
            'passed': has_wilson or is_rare
        }, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"结果已保存至：tests/results/langgraph_wilson_test.json")


if __name__ == "__main__":
    asyncio.run(test_langgraph_workflow())
