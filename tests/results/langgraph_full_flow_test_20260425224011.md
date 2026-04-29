# LangGraph整体框架流程测试报告

**报告ID**: RPT-LANGGRAPH-FULL-20260425224011
**生成时间**: 2026-04-25T22:40:11.509473

## 测试摘要

| 指标 | 值 |
|------|-----|
| 总测试数 | 20 |
| 通过数 | 8 |
| 失败数 | 12 |
| **总体通过率** | **40.0%** |

## 按类别统计

| 类别 | 总数 | 通过 | 通过率 |
|------|------|------|--------|
| 信息完整 | 11 | 7 | 63.6% |
| 关键信息缺失 | 6 | 0 | 0.0% |
| 非关键信息缺失 | 3 | 1 | 33.3% |

## 失败用例分析

### CASE-005: 关键缺失-无肝功能检查

**类别**: 关键信息缺失

**失败原因**: 信息不全触发状态不匹配: 预期True, 实际0

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
    "data_completeness_score": 0.46,
    "path": "uncertain",
    "diagnosis": "",
    "confidence_level": "insufficient_data",
    "is_rare_disease_alert": false
  }
}
```

### CASE-006: 关键缺失-无影像学检查

**类别**: 关键信息缺失

**失败原因**: 信息不全触发状态不匹配: 预期True, 实际0; 分诊路径不匹配: 预期包含'uncertain', 实际'common'; 置信度级别不匹配: 预期['insufficient_data', 'low'], 实际'medium'

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
    "data_completeness_score": 0.62,
    "path": "common",
    "diagnosis": "酒精性肝病 (ALD)",
    "confidence_level": "medium",
    "is_rare_disease_alert": false
  }
}
```

### CASE-007: 关键缺失-无年龄性别

**类别**: 关键信息缺失

**失败原因**: 信息不全触发状态不匹配: 预期True, 实际0; 完整度评分过高: 预期<0.5, 实际0.61

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
    "data_completeness_score": 0.61,
    "path": "uncertain",
    "diagnosis": "",
    "confidence_level": "insufficient_data",
    "is_rare_disease_alert": false
  }
}
```

### CASE-008: 关键缺失-无主诉

**类别**: 关键信息缺失

**失败原因**: 信息不全触发状态不匹配: 预期True, 实际0

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
    "data_completeness_score": 0.59,
    "path": "uncertain",
    "diagnosis": "",
    "confidence_level": "insufficient_data",
    "is_rare_disease_alert": false
  }
}
```

### CASE-009: 非关键缺失-无饮酒史

**类别**: 非关键信息缺失

**失败原因**: 诊断关键词不匹配: 预期包含['脂肪肝', 'NAFLD'], 实际'代谢相关脂肪性肝病 (MASLD)'

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
    "data_completeness_score": 0.86,
    "path": "common",
    "diagnosis": "代谢相关脂肪性肝病 (MASLD)",
    "confidence_level": "medium",
    "is_rare_disease_alert": false
  }
}
```

### CASE-011: 信息完整-病毒性肝炎-中年男性

**类别**: 信息完整

**失败原因**: 诊断关键词不匹配: 预期包含['乙肝', '病毒性肝炎', 'HBV'], 实际'慢性乙型肝炎'

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
    "data_completeness_score": 0.86,
    "path": "common",
    "diagnosis": "慢性乙型肝炎",
    "confidence_level": "high",
    "is_rare_disease_alert": false
  }
}
```

### CASE-012: 信息完整-药物性肝损伤

**类别**: 信息完整

**失败原因**: 分诊路径不匹配: 预期包含'common', 实际'rare_deep_path'; 罕见病预警状态不匹配: 预期False, 实际True

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
    "data_completeness_score": 0.91,
    "path": "rare_deep_path",
    "diagnosis": "",
    "confidence_level": "high",
    "is_rare_disease_alert": true
  }
}
```

### CASE-013: 关键缺失-无病毒标志物

**类别**: 关键信息缺失

**失败原因**: 信息不全触发状态不匹配: 预期True, 实际0; 分诊路径不匹配: 预期包含'uncertain', 实际'common'; 置信度级别不匹配: 预期['insufficient_data', 'low'], 实际'high'

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
    "data_completeness_score": 0.69,
    "path": "common",
    "diagnosis": "急性病毒性肝炎",
    "confidence_level": "high",
    "is_rare_disease_alert": false
  }
}
```

### CASE-016: 非关键缺失-无BMI

**类别**: 非关键信息缺失

**失败原因**: 诊断关键词不匹配: 预期包含['脂肪肝'], 实际'代谢相关脂肪性肝病 (MASLD)'

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
    "data_completeness_score": 0.77,
    "path": "common",
    "diagnosis": "代谢相关脂肪性肝病 (MASLD)",
    "confidence_level": "medium",
    "is_rare_disease_alert": false
  }
}
```

### CASE-017: 边缘病例-老年患者轻度异常

**类别**: 信息完整

**失败原因**: 分诊路径不匹配: 预期包含'common', 实际'uncertain'; 置信度级别不匹配: 预期['medium', 'low'], 实际'insufficient_data'

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
    "data_completeness_score": 0.86,
    "path": "uncertain",
    "diagnosis": "",
    "confidence_level": "insufficient_data",
    "is_rare_disease_alert": false
  }
}
```

### CASE-018: 边缘病例-年轻无症状

**类别**: 信息完整

**失败原因**: 分诊路径不匹配: 预期包含'common', 实际'uncertain'; 置信度级别不匹配: 预期['medium', 'low'], 实际'insufficient_data'

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
    "data_completeness_score": 0.86,
    "path": "uncertain",
    "diagnosis": "",
    "confidence_level": "insufficient_data",
    "is_rare_disease_alert": false
  }
}
```

### CASE-019: 关键缺失-多项关键信息缺失

**类别**: 关键信息缺失

**失败原因**: 信息不全触发状态不匹配: 预期True, 实际0; 完整度评分过高: 预期<0.3, 实际0.30

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
    "data_completeness_score": 0.3,
    "path": "uncertain",
    "diagnosis": "",
    "confidence_level": "insufficient_data",
    "is_rare_disease_alert": false
  }
}
```
