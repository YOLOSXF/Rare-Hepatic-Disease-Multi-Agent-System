# LangGraph整体框架流程测试报告

**报告ID**: RPT-LANGGRAPH-FULL-20260425220600
**生成时间**: 2026-04-25T22:06:00.723267

## 测试摘要

| 指标 | 值 |
|------|-----|
| 总测试数 | 20 |
| 通过数 | 0 |
| 失败数 | 20 |
| **总体通过率** | **0.0%** |

## 按类别统计

| 类别 | 总数 | 通过 | 通过率 |
|------|------|------|--------|
| 信息完整 | 11 | 0 | 0.0% |
| 关键信息缺失 | 6 | 0 | 0.0% |
| 非关键信息缺失 | 3 | 0 | 0.0% |

## 失败用例分析

### CASE-001: 信息完整-脂肪肝-中年男性

**类别**: 信息完整

**失败原因**: 完整度评分不达标: 预期>=0.8, 实际0.00; 分诊路径不匹配: 预期包含'common', 实际''; 置信度级别不匹配: 预期['high', 'medium'], 实际''

**预期结果**:
```json
{
  "L1": {
    "should_trigger_incomplete": false,
    "expected_missing_fields": [],
    "expected_completeness_score": ">=0.8",
    "reason": "所有关键信息完整，包括年龄、性别、主诉、肝功能、影像学检查"
  },
  "L2": {
    "expected_path": "common",
    "expected_diagnosis_contains": [
      "代谢相关脂肪性肝病",
      "MASLD",
      "脂肪肝"
    ],
    "expected_is_rare_alert": false,
    "expected_confidence_level": [
      "high",
      "medium"
    ],
    "reason": "典型脂肪肝表现：肥胖、超声脂肪肝、转氨酶轻度升高"
  }
}
```

**实际结果**:
```json
{
  "success": true,
  "report_summary": {
    "data_completeness_score": null,
    "path": null,
    "diagnosis": "代谢相关脂肪性肝病 (MASLD)",
    "confidence_level": null,
    "is_rare_disease_alert": null
  }
}
```

### CASE-002: 信息完整-酒精性肝病-中年男性

**类别**: 信息完整

**失败原因**: 完整度评分不达标: 预期>=0.8, 实际0.00; 分诊路径不匹配: 预期包含'common', 实际''; 置信度级别不匹配: 预期['high', 'medium'], 实际''

**预期结果**:
```json
{
  "L1": {
    "should_trigger_incomplete": false,
    "expected_missing_fields": [],
    "expected_completeness_score": ">=0.8",
    "reason": "关键信息完整，有明确的饮酒史和肝功能异常"
  },
  "L2": {
    "expected_path": "common",
    "expected_diagnosis_contains": [
      "酒精",
      "ALD"
    ],
    "expected_is_rare_alert": false,
    "expected_confidence_level": [
      "high",
      "medium"
    ],
    "reason": "AST/ALT>2，长期大量饮酒史，典型酒精性肝病"
  }
}
```

**实际结果**:
```json
{
  "success": true,
  "report_summary": {
    "data_completeness_score": null,
    "path": null,
    "diagnosis": "酒精性肝病 (ALD)",
    "confidence_level": null,
    "is_rare_disease_alert": null
  }
}
```

### CASE-003: 信息完整-Wilson病-年轻女性

**类别**: 信息完整

**失败原因**: 完整度评分不达标: 预期>=0.8, 实际0.00

**预期结果**:
```json
{
  "L1": {
    "should_trigger_incomplete": false,
    "expected_missing_fields": [],
    "expected_completeness_score": ">=0.8",
    "reason": "关键信息完整，包括特殊检查（铜蓝蛋白、K-F环）"
  },
  "L2": {
    "expected_path": "rare",
    "expected_diagnosis_contains": [
      "Wilson",
      "肝豆"
    ],
    "expected_is_rare_alert": true,
    "expected_confidence_level": [
      "high",
      "medium"
    ],
    "reason": "年轻患者+震颤+铜蓝蛋白降低+K-F环阳性，典型Wilson病"
  }
}
```

**实际结果**:
```json
{
  "success": true,
  "report_summary": {
    "data_completeness_score": null,
    "path": "rare_deep_path",
    "diagnosis": "",
    "confidence_level": "high",
    "is_rare_disease_alert": true
  }
}
```

### CASE-004: 信息完整-自身免疫性肝炎-中年女性

**类别**: 信息完整

**失败原因**: 完整度评分不达标: 预期>=0.8, 实际0.00

**预期结果**:
```json
{
  "L1": {
    "should_trigger_incomplete": false,
    "expected_missing_fields": [],
    "expected_completeness_score": ">=0.8",
    "reason": "关键信息完整，包括自身抗体和免疫球蛋白"
  },
  "L2": {
    "expected_path": "rare",
    "expected_diagnosis_contains": [
      "自身免疫性肝炎",
      "AIH"
    ],
    "expected_is_rare_alert": true,
    "expected_confidence_level": [
      "high",
      "medium"
    ],
    "reason": "女性+高IgG+ANA/SMA阳性+肝功能异常，典型AIH"
  }
}
```

**实际结果**:
```json
{
  "success": true,
  "report_summary": {
    "data_completeness_score": null,
    "path": "rare_deep_path",
    "diagnosis": "",
    "confidence_level": "high",
    "is_rare_disease_alert": true
  }
}
```

### CASE-005: 关键缺失-无肝功能检查

**类别**: 关键信息缺失

**失败原因**: 信息不全触发状态不匹配: 预期True, 实际0; 分诊路径不匹配: 预期包含'uncertain', 实际''; 置信度级别不匹配: 预期['insufficient_data', 'low'], 实际''

**预期结果**:
```json
{
  "L1": {
    "should_trigger_incomplete": true,
    "expected_missing_fields": [
      "ALT",
      "AST",
      "TBil"
    ],
    "expected_completeness_score": "<0.5",
    "reason": "缺少关键肝功能检查（ALT、AST、TBil）"
  },
  "L2": {
    "expected_path": "uncertain",
    "expected_diagnosis_contains": [],
    "expected_is_rare_alert": false,
    "expected_confidence_level": [
      "insufficient_data",
      "low"
    ],
    "reason": "缺少核心检验数据，无法进行准确分诊"
  }
}
```

**实际结果**:
```json
{
  "success": true,
  "report_summary": {
    "data_completeness_score": null,
    "path": null,
    "diagnosis": "",
    "confidence_level": null,
    "is_rare_disease_alert": null
  }
}
```

### CASE-006: 关键缺失-无影像学检查

**类别**: 关键信息缺失

**失败原因**: 信息不全触发状态不匹配: 预期True, 实际0; 分诊路径不匹配: 预期包含'uncertain', 实际''; 置信度级别不匹配: 预期['insufficient_data', 'low'], 实际''

**预期结果**:
```json
{
  "L1": {
    "should_trigger_incomplete": true,
    "expected_missing_fields": [
      "超声",
      "影像学"
    ],
    "expected_completeness_score": "<0.7",
    "reason": "缺少影像学检查结果"
  },
  "L2": {
    "expected_path": "uncertain",
    "expected_diagnosis_contains": [],
    "expected_is_rare_alert": false,
    "expected_confidence_level": [
      "insufficient_data",
      "low"
    ],
    "reason": "缺少影像学评估，分诊置信度降低"
  }
}
```

**实际结果**:
```json
{
  "success": true,
  "report_summary": {
    "data_completeness_score": null,
    "path": null,
    "diagnosis": "酒精性肝病 (ALD)",
    "confidence_level": null,
    "is_rare_disease_alert": null
  }
}
```

### CASE-007: 关键缺失-无年龄性别

**类别**: 关键信息缺失

**失败原因**: 信息不全触发状态不匹配: 预期True, 实际0; 分诊路径不匹配: 预期包含'uncertain', 实际''; 置信度级别不匹配: 预期['insufficient_data', 'low'], 实际''

**预期结果**:
```json
{
  "L1": {
    "should_trigger_incomplete": true,
    "expected_missing_fields": [
      "年龄",
      "性别"
    ],
    "expected_completeness_score": "<0.5",
    "reason": "缺少基本人口学信息（年龄、性别）"
  },
  "L2": {
    "expected_path": "uncertain",
    "expected_diagnosis_contains": [],
    "expected_is_rare_alert": false,
    "expected_confidence_level": [
      "insufficient_data",
      "low"
    ],
    "reason": "缺少关键人口学信息，影响诊断判断"
  }
}
```

**实际结果**:
```json
{
  "success": true,
  "report_summary": {
    "data_completeness_score": null,
    "path": null,
    "diagnosis": "",
    "confidence_level": null,
    "is_rare_disease_alert": null
  }
}
```

### CASE-008: 关键缺失-无主诉

**类别**: 关键信息缺失

**失败原因**: 信息不全触发状态不匹配: 预期True, 实际0; 分诊路径不匹配: 预期包含'uncertain', 实际''; 置信度级别不匹配: 预期['insufficient_data', 'low'], 实际''

**预期结果**:
```json
{
  "L1": {
    "should_trigger_incomplete": true,
    "expected_missing_fields": [
      "主诉"
    ],
    "expected_completeness_score": "<0.7",
    "reason": "缺少主诉信息"
  },
  "L2": {
    "expected_path": "uncertain",
    "expected_diagnosis_contains": [],
    "expected_is_rare_alert": false,
    "expected_confidence_level": [
      "insufficient_data",
      "low"
    ],
    "reason": "缺少主诉，无法了解就诊原因"
  }
}
```

**实际结果**:
```json
{
  "success": true,
  "report_summary": {
    "data_completeness_score": null,
    "path": null,
    "diagnosis": "",
    "confidence_level": null,
    "is_rare_disease_alert": null
  }
}
```

### CASE-009: 非关键缺失-无饮酒史

**类别**: 非关键信息缺失

**失败原因**: 完整度评分不达标: 预期>=0.7, 实际0.00; 分诊路径不匹配: 预期包含'common', 实际''; 诊断关键词不匹配: 预期包含['脂肪肝', 'NAFLD'], 实际'代谢相关脂肪性肝病 (MASLD)'; 置信度级别不匹配: 预期['medium', 'high'], 实际''

**预期结果**:
```json
{
  "L1": {
    "should_trigger_incomplete": false,
    "expected_missing_fields": [],
    "expected_completeness_score": ">=0.7",
    "reason": "关键信息完整，仅缺少饮酒史（非关键）"
  },
  "L2": {
    "expected_path": "common",
    "expected_diagnosis_contains": [
      "脂肪肝",
      "NAFLD"
    ],
    "expected_is_rare_alert": false,
    "expected_confidence_level": [
      "medium",
      "high"
    ],
    "reason": "可进行分诊，但置信度可能因缺少饮酒史而略低"
  }
}
```

**实际结果**:
```json
{
  "success": true,
  "report_summary": {
    "data_completeness_score": null,
    "path": null,
    "diagnosis": "代谢相关脂肪性肝病 (MASLD)",
    "confidence_level": null,
    "is_rare_disease_alert": null
  }
}
```

### CASE-010: 非关键缺失-无家族史

**类别**: 非关键信息缺失

**失败原因**: 完整度评分不达标: 预期>=0.7, 实际0.00

**预期结果**:
```json
{
  "L1": {
    "should_trigger_incomplete": false,
    "expected_missing_fields": [],
    "expected_completeness_score": ">=0.7",
    "reason": "关键信息完整，仅缺少家族史（非关键但有参考价值）"
  },
  "L2": {
    "expected_path": "rare",
    "expected_diagnosis_contains": [
      "Wilson",
      "肝豆"
    ],
    "expected_is_rare_alert": true,
    "expected_confidence_level": [
      "high",
      "medium"
    ],
    "reason": "典型Wilson病表现，家族史缺失不影响诊断"
  }
}
```

**实际结果**:
```json
{
  "success": true,
  "report_summary": {
    "data_completeness_score": null,
    "path": "rare_deep_path",
    "diagnosis": "",
    "confidence_level": "high",
    "is_rare_disease_alert": true
  }
}
```

### CASE-011: 信息完整-病毒性肝炎-中年男性

**类别**: 信息完整

**失败原因**: 完整度评分不达标: 预期>=0.8, 实际0.00; 分诊路径不匹配: 预期包含'common', 实际''; 诊断关键词不匹配: 预期包含['乙肝', '病毒性肝炎', 'HBV'], 实际'慢性乙型肝炎'; 置信度级别不匹配: 预期['high'], 实际''

**预期结果**:
```json
{
  "L1": {
    "should_trigger_incomplete": false,
    "expected_missing_fields": [],
    "expected_completeness_score": ">=0.8",
    "reason": "关键信息完整"
  },
  "L2": {
    "expected_path": "common",
    "expected_diagnosis_contains": [
      "乙肝",
      "病毒性肝炎",
      "HBV"
    ],
    "expected_is_rare_alert": false,
    "expected_confidence_level": [
      "high"
    ],
    "reason": "HBsAg阳性+高病毒载量+肝功能明显异常，典型乙肝活动"
  }
}
```

**实际结果**:
```json
{
  "success": true,
  "report_summary": {
    "data_completeness_score": null,
    "path": null,
    "diagnosis": "慢性乙型肝炎",
    "confidence_level": null,
    "is_rare_disease_alert": null
  }
}
```

### CASE-012: 信息完整-药物性肝损伤

**类别**: 信息完整

**失败原因**: 完整度评分不达标: 预期>=0.8, 实际0.00; 分诊路径不匹配: 预期包含'common', 实际'rare_deep_path'; 罕见病预警状态不匹配: 预期False, 实际True

**预期结果**:
```json
{
  "L1": {
    "should_trigger_incomplete": false,
    "expected_missing_fields": [],
    "expected_completeness_score": ">=0.8",
    "reason": "关键信息完整，有明确用药史"
  },
  "L2": {
    "expected_path": "common",
    "expected_diagnosis_contains": [
      "药物性",
      "DILI"
    ],
    "expected_is_rare_alert": false,
    "expected_confidence_level": [
      "high",
      "medium"
    ],
    "reason": "用药史+肝功能异常+排除其他原因，考虑药物性肝损伤"
  }
}
```

**实际结果**:
```json
{
  "success": true,
  "report_summary": {
    "data_completeness_score": null,
    "path": "rare_deep_path",
    "diagnosis": "",
    "confidence_level": "high",
    "is_rare_disease_alert": true
  }
}
```

### CASE-013: 关键缺失-无病毒标志物

**类别**: 关键信息缺失

**失败原因**: 信息不全触发状态不匹配: 预期True, 实际0; 分诊路径不匹配: 预期包含'uncertain', 实际''; 置信度级别不匹配: 预期['insufficient_data', 'low'], 实际''

**预期结果**:
```json
{
  "L1": {
    "should_trigger_incomplete": true,
    "expected_missing_fields": [
      "HBsAg",
      "病毒标志物"
    ],
    "expected_completeness_score": "<0.7",
    "reason": "缺少病毒性肝炎标志物检查"
  },
  "L2": {
    "expected_path": "uncertain",
    "expected_diagnosis_contains": [],
    "expected_is_rare_alert": false,
    "expected_confidence_level": [
      "insufficient_data",
      "low"
    ],
    "reason": "缺少病毒标志物，无法排除病毒性肝炎"
  }
}
```

**实际结果**:
```json
{
  "success": true,
  "report_summary": {
    "data_completeness_score": null,
    "path": null,
    "diagnosis": "急性病毒性肝炎",
    "confidence_level": null,
    "is_rare_disease_alert": null
  }
}
```

### CASE-014: 信息完整-PBC-中年女性

**类别**: 信息完整

**失败原因**: 完整度评分不达标: 预期>=0.8, 实际0.00

**预期结果**:
```json
{
  "L1": {
    "should_trigger_incomplete": false,
    "expected_missing_fields": [],
    "expected_completeness_score": ">=0.8",
    "reason": "关键信息完整"
  },
  "L2": {
    "expected_path": "rare",
    "expected_diagnosis_contains": [
      "PBC",
      "原发性胆汁性胆管炎"
    ],
    "expected_is_rare_alert": true,
    "expected_confidence_level": [
      "high",
      "medium"
    ],
    "reason": "中年女性+瘙痒+ALP/GGT升高+AMA阳性，典型PBC"
  }
}
```

**实际结果**:
```json
{
  "success": true,
  "report_summary": {
    "data_completeness_score": null,
    "path": "rare_deep_path",
    "diagnosis": "",
    "confidence_level": "high",
    "is_rare_disease_alert": true
  }
}
```

### CASE-015: 信息完整-血色病-中年男性

**类别**: 信息完整

**失败原因**: 完整度评分不达标: 预期>=0.8, 实际0.00

**预期结果**:
```json
{
  "L1": {
    "should_trigger_incomplete": false,
    "expected_missing_fields": [],
    "expected_completeness_score": ">=0.8",
    "reason": "关键信息完整"
  },
  "L2": {
    "expected_path": "rare",
    "expected_diagnosis_contains": [
      "血色病",
      "hemochromatosis"
    ],
    "expected_is_rare_alert": true,
    "expected_confidence_level": [
      "high",
      "medium"
    ],
    "reason": "铁蛋白显著升高+转铁蛋白饱和度高+皮肤色素沉着，典型血色病"
  }
}
```

**实际结果**:
```json
{
  "success": true,
  "report_summary": {
    "data_completeness_score": null,
    "path": "rare_deep_path",
    "diagnosis": "",
    "confidence_level": "high",
    "is_rare_disease_alert": true
  }
}
```

### CASE-016: 非关键缺失-无BMI

**类别**: 非关键信息缺失

**失败原因**: 完整度评分不达标: 预期>=0.7, 实际0.00; 分诊路径不匹配: 预期包含'common', 实际''; 诊断关键词不匹配: 预期包含['脂肪肝'], 实际'代谢相关脂肪性肝病 (MASLD)'; 置信度级别不匹配: 预期['medium', 'high'], 实际''

**预期结果**:
```json
{
  "L1": {
    "should_trigger_incomplete": false,
    "expected_missing_fields": [],
    "expected_completeness_score": ">=0.7",
    "reason": "关键信息完整，BMI为非关键信息"
  },
  "L2": {
    "expected_path": "common",
    "expected_diagnosis_contains": [
      "脂肪肝"
    ],
    "expected_is_rare_alert": false,
    "expected_confidence_level": [
      "medium",
      "high"
    ],
    "reason": "可进行分诊，BMI缺失不影响主要判断"
  }
}
```

**实际结果**:
```json
{
  "success": true,
  "report_summary": {
    "data_completeness_score": null,
    "path": null,
    "diagnosis": "代谢相关脂肪性肝病 (MASLD)",
    "confidence_level": null,
    "is_rare_disease_alert": null
  }
}
```

### CASE-017: 边缘病例-老年患者轻度异常

**类别**: 信息完整

**失败原因**: 完整度评分不达标: 预期>=0.8, 实际0.00; 分诊路径不匹配: 预期包含'common', 实际''; 置信度级别不匹配: 预期['medium', 'low'], 实际''

**预期结果**:
```json
{
  "L1": {
    "should_trigger_incomplete": false,
    "expected_missing_fields": [],
    "expected_completeness_score": ">=0.8",
    "reason": "关键信息完整"
  },
  "L2": {
    "expected_path": "common",
    "expected_diagnosis_contains": [],
    "expected_is_rare_alert": false,
    "expected_confidence_level": [
      "medium",
      "low"
    ],
    "reason": "老年患者，轻度异常，可能需要随访观察"
  }
}
```

**实际结果**:
```json
{
  "success": true,
  "report_summary": {
    "data_completeness_score": null,
    "path": null,
    "diagnosis": "",
    "confidence_level": null,
    "is_rare_disease_alert": null
  }
}
```

### CASE-018: 边缘病例-年轻无症状

**类别**: 信息完整

**失败原因**: 完整度评分不达标: 预期>=0.8, 实际0.00; 分诊路径不匹配: 预期包含'common', 实际''; 置信度级别不匹配: 预期['medium', 'low'], 实际''

**预期结果**:
```json
{
  "L1": {
    "should_trigger_incomplete": false,
    "expected_missing_fields": [],
    "expected_completeness_score": ">=0.8",
    "reason": "关键信息完整"
  },
  "L2": {
    "expected_path": "common",
    "expected_diagnosis_contains": [],
    "expected_is_rare_alert": false,
    "expected_confidence_level": [
      "medium",
      "low"
    ],
    "reason": "年轻女性，轻度异常，可能与药物相关"
  }
}
```

**实际结果**:
```json
{
  "success": true,
  "report_summary": {
    "data_completeness_score": null,
    "path": null,
    "diagnosis": "",
    "confidence_level": null,
    "is_rare_disease_alert": null
  }
}
```

### CASE-019: 关键缺失-多项关键信息缺失

**类别**: 关键信息缺失

**失败原因**: 信息不全触发状态不匹配: 预期True, 实际0; 分诊路径不匹配: 预期包含'uncertain', 实际''; 置信度级别不匹配: 预期['insufficient_data'], 实际''

**预期结果**:
```json
{
  "L1": {
    "should_trigger_incomplete": true,
    "expected_missing_fields": [
      "年龄",
      "性别",
      "AST",
      "TBil",
      "影像学"
    ],
    "expected_completeness_score": "<0.3",
    "reason": "多项关键信息缺失"
  },
  "L2": {
    "expected_path": "uncertain",
    "expected_diagnosis_contains": [],
    "expected_is_rare_alert": false,
    "expected_confidence_level": [
      "insufficient_data"
    ],
    "reason": "信息严重不足，无法进行有效分诊"
  }
}
```

**实际结果**:
```json
{
  "success": true,
  "report_summary": {
    "data_completeness_score": null,
    "path": null,
    "diagnosis": "",
    "confidence_level": null,
    "is_rare_disease_alert": null
  }
}
```

### CASE-020: 信息完整-儿童Wilson病

**类别**: 信息完整

**失败原因**: 完整度评分不达标: 预期>=0.8, 实际0.00

**预期结果**:
```json
{
  "L1": {
    "should_trigger_incomplete": false,
    "expected_missing_fields": [],
    "expected_completeness_score": ">=0.8",
    "reason": "关键信息完整"
  },
  "L2": {
    "expected_path": "rare",
    "expected_diagnosis_contains": [
      "Wilson",
      "肝豆"
    ],
    "expected_is_rare_alert": true,
    "expected_confidence_level": [
      "high"
    ],
    "reason": "儿童+家族史+铜蓝蛋白降低+K-F环阳性，高度怀疑Wilson病"
  }
}
```

**实际结果**:
```json
{
  "success": true,
  "report_summary": {
    "data_completeness_score": null,
    "path": "rare_deep_path",
    "diagnosis": "",
    "confidence_level": "high",
    "is_rare_disease_alert": true
  }
}
```
