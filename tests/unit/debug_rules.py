#!/usr/bin/env python3
"""
规则匹配调试脚本
"""

import sys
sys.path.insert(0, '/data01/shenxf/Agent/medical-agent')

from core.triage import RuleEngine

# 测试数据
patient = {
    "age": 23,
    "gender": "male",
    "labs": {
        "Ceruloplasmin": 0.08,
        "ALT": 125
    },
    "symptoms": {
        "tremor": True,
        "dysarthria": True
    },
    "eye_exam": {
        "kf_ring": "阳性"
    }
}

# 初始化规则引擎
engine = RuleEngine(rules_dir="/data01/shenxf/Agent/medical-agent/rules")

print("=" * 80)
print("规则匹配调试")
print("=" * 80)
print()

# 测试 Wilson 病规则
wilson_config = engine.rare_rules.get('wilson_disease')
if wilson_config:
    print(f"Wilson 病规则配置：{wilson_config.get('name')}")
    print()
    
    # 测试核心规则
    print("核心规则匹配:")
    for rule in wilson_config.get('core_rules', []):
        field = rule.get('field')
        operator = rule.get('operator')
        value = rule.get('value')
        
        actual = engine._get_nested_value(patient, field)
        matched = engine._evaluate_operator(actual, operator, value)
        
        print(f"  字段：{field}")
        print(f"  实际值：{actual}")
        print(f"  期望值：{operator} {value}")
        print(f"  匹配：{'✅' if matched else '❌'}")
        print()
    
    # 测试完整匹配
    print("完整疾病匹配:")
    result = engine.match_disease('wilson_disease', wilson_config, patient)
    print(f"  疾病：{result.disease_name}")
    print(f"  类别：{result.category}")
    print(f"  得分：{result.total_score:.2f} / {result.max_possible_score:.2f}")
    print(f"  标准化得分：{result.normalized_score:.2f}")
    print(f"  置信度：{result.confidence_level}")
    print(f"  紧急程度：{result.urgency}")
    print()
    print(f"  匹配的规则数：{len(result.matched_rules)}")
    print(f"  未满足的核心规则：{result.missed_core_rules}")
else:
    print("❌ 未找到 Wilson 病规则")

print()
print("=" * 80)
