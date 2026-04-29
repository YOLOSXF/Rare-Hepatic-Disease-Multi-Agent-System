"""
验证三个隐患修复的测试脚本
"""

import sys
sys.path.insert(0, '/data01/shenxf/Agent/medical-agent')

from core.data_assessor import DataCompletenessAssessor
from core.preprocessor import DataPreprocessor
from loguru import logger

logger.remove()


def test_fix_1_imaging_not_required():
    """
    隐患1修复验证：影像学不再是硬性拦截
    测试：只有肝功能数据、没有影像学的患者应该可以进行分诊
    """
    print("\n" + "="*60)
    print("【隐患1修复验证】影像学不再是硬性拦截")
    print("="*60)
    
    assessor = DataCompletenessAssessor()
    
    # 测试用例：只有肝功能数据，没有影像学
    patient_without_imaging = {
        "age": 35,
        "gender": "male",
        "chief_complaint": "体检发现ALT升高",
        "labs": {
            "ALT": 300,  # 显著升高
            "AST": 250,
            "TBil": 45.8
        }
    }
    
    result = assessor.assess(patient_without_imaging)
    
    print(f"患者数据：")
    print(f"  - 年龄：{patient_without_imaging['age']}")
    print(f"  - 主诉：{patient_without_imaging['chief_complaint']}")
    print(f"  - ALT：{patient_without_imaging['labs']['ALT']}")
    print(f"  - 影像学：无")
    print(f"\n评估结果：")
    print(f"  - 完整性评分：{result.score}")
    print(f"  - 可分诊：{result.can_triage}")
    print(f"  - 缺失关键项：{result.missing_critical}")
    print(f"  - 建议行动：{result.recommended_actions}")
    
    # 验证：应该可以进行分诊（即使没有影像学）
    assert result.can_triage == True, "❌ 修复失败：没有影像学的患者应该可以进行分诊"
    
    # 验证：影像学应该在缺失列表中（作为推荐项）
    assert '腹部影像学（超声/CT/MRI）' in result.missing_critical or \
           '腹部影像学（超声/CT/MRI）' in result.missing_recommended, \
           "❌ 修复失败：影像学应该在缺失列表中"
    
    print("\n✅ 隐患1修复验证通过：影像学不再是分诊的硬性拦截")


def test_fix_2_within_days_replaced():
    """
    隐患2修复验证：DILI规则中的within_days已替换为布尔标志
    测试：检查YAML规则中是否还存在within_days操作符
    """
    print("\n" + "="*60)
    print("【隐患2修复验证】DILI规则中的within_days已替换")
    print("="*60)
    
    import yaml
    
    yaml_path = "/data01/shenxf/Agent/medical-agent/rules/common_diseases.yaml"
    with open(yaml_path, 'r', encoding='utf-8') as f:
        rules = yaml.safe_load(f)
    
    # 检查DILI规则
    dili_rules = rules.get('dili', {})
    supporting_rules = dili_rules.get('supporting_rules', [])
    
    print(f"DILI支持规则数量：{len(supporting_rules)}")
    
    has_within_days = False
    has_hepatotoxic_flag = False
    
    for rule in supporting_rules:
        field = rule.get('field', '')
        operator = rule.get('operator', '')
        
        print(f"  - 字段：{field}, 操作符：{operator}")
        
        if operator == 'within_days':
            has_within_days = True
        
        if 'has_recent_hepatotoxic_medication' in field:
            has_hepatotoxic_flag = True
    
    print(f"\n检查结果：")
    print(f"  - 存在within_days操作符：{has_within_days}")
    print(f"  - 存在hepatotoxic布尔标志：{has_hepatotoxic_flag}")
    
    # 验证：不应该存在within_days操作符
    assert has_within_days == False, "❌ 修复失败：DILI规则中仍然存在within_days操作符"
    
    # 验证：应该存在hepatotoxic布尔标志
    assert has_hepatotoxic_flag == True, "❌ 修复失败：DILI规则中缺少hepatotoxic布尔标志"
    
    print("\n✅ 隐患2修复验证通过：within_days已替换为布尔标志")


def test_fix_3_zero_and_false_handling():
    """
    隐患3修复验证：0和False值不再被误判为缺失
    测试：年龄为0（婴儿）和饮酒史为0的患者
    """
    print("\n" + "="*60)
    print("【隐患3修复验证】0和False值不再被误判为缺失")
    print("="*60)
    
    preprocessor = DataPreprocessor()
    
    # 测试用例1：婴儿患者（年龄为0）
    infant_patient = {
        "patient_id": "P_INFANT_001",
        "age": 0,  # 婴儿
        "gender": "male",
        "chief_complaint": "黄疸2周",
        "labs": {
            "ALT": 85,
            "AST": 92,
            "TBil": 68.5
        },
        "history": {
            "alcohol_intake_weekly": 0,  # 不饮酒
            "medication_history": "无"
        }
    }
    
    result = preprocessor.preprocess(infant_patient)
    
    print(f"测试用例1：婴儿患者")
    print(f"  - 年龄：{infant_patient['age']}")
    print(f"  - 饮酒史：{infant_patient['history']['alcohol_intake_weekly']}")
    print(f"  - 缺失项：{result.missing_values}")
    print(f"  - 警告：{result.warnings}")
    
    # 验证：年龄0不应该被标记为缺失
    assert '年龄' not in result.missing_values, \
        "❌ 修复失败：年龄为0不应该被标记为缺失"
    
    # 验证：饮酒史0不应该被标记为缺失
    assert '饮酒史' not in result.missing_values, \
        "❌ 修复失败：饮酒史为0不应该被标记为缺失"
    
    # 测试用例2：年龄为0.5（几个月大的婴儿）
    infant_patient_2 = {
        "patient_id": "P_INFANT_002",
        "age": 0.5,  # 几个月大
        "gender": "female",
        "chief_complaint": "肝功能异常",
        "labs": {
            "ALT": 120,
            "AST": 110,
            "TBil": 85.2
        },
        "history": {
            "alcohol_intake_weekly": 0,
            "medication_history": "无"
        }
    }
    
    result2 = preprocessor.preprocess(infant_patient_2)
    
    print(f"\n测试用例2：几个月大的婴儿")
    print(f"  - 年龄：{infant_patient_2['age']}")
    print(f"  - 缺失项：{result2.missing_values}")
    
    # 验证：年龄0.5不应该被标记为缺失
    assert '年龄' not in result2.missing_values, \
        "❌ 修复失败：年龄为0.5不应该被标记为缺失"
    
    # 测试用例3：真正的缺失值（None）
    patient_with_missing = {
        "patient_id": "P_MISSING_001",
        "age": None,  # 真正缺失
        "gender": "",
        "chief_complaint": "乏力",
        "labs": {
            "ALT": 65
        },
        "history": {
            "alcohol_intake_weekly": None,
            "medication_history": None
        }
    }
    
    result3 = preprocessor.preprocess(patient_with_missing)
    
    print(f"\n测试用例3：真正的缺失值")
    print(f"  - 年龄：{patient_with_missing['age']}")
    print(f"  - 性别：'{patient_with_missing['gender']}'")
    print(f"  - 缺失项：{result3.missing_values}")
    
    # 验证：None和空字符串应该被标记为缺失
    assert '年龄' in result3.missing_values, \
        "❌ 修复失败：年龄为None应该被标记为缺失"
    assert '性别' in result3.missing_values, \
        "❌ 修复失败：性别为空字符串应该被标记为缺失"
    
    print("\n✅ 隐患3修复验证通过：0和False值不再被误判为缺失")


def run_all_verification_tests():
    """运行所有验证测试"""
    print("\n" + "🔍"*30)
    print("三个隐患修复验证测试套件")
    print("🔍"*30)
    
    try:
        test_fix_1_imaging_not_required()
        test_fix_2_within_days_replaced()
        test_fix_3_zero_and_false_handling()
        
        print("\n" + "✅"*30)
        print("所有三个隐患修复验证通过！")
        print("✅"*30 + "\n")
        
    except AssertionError as e:
        print(f"\n❌ 验证失败：{e}\n")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"\n❌ 验证异常：{e}\n")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    run_all_verification_tests()
