# 患者病例分诊测试报告

**报告ID**: RPT-PATIENT-CASES-20260425222819
**生成时间**: 2026-04-25T22:28:19.217256

## 测试摘要

| 指标 | 值 |
|------|-----|
| 总测试病例数 | 20 |
| 总体正确数 | 7 |
| **总体正确率** | **35.00%** |
| L1层正确数 | 16 |
| L1层正确率 | 80.00% |
| L2层正确数 | 8 |
| L2层正确率 | 40.00% |
| 总执行时间 | 33.53s |

## 按病例类型统计

| 类型 | 总数 | 正确 | 正确率 |
|------|------|------|--------|
| 信息完整 | 11 | 7 | 63.64% |
| 关键信息缺失 | 6 | 0 | 0.00% |
| 非关键信息缺失 | 3 | 0 | 0.00% |

## 按分诊路径统计

| 分诊路径 | 总数 | 正确 | 正确率 |
|----------|------|------|--------|
| common | 8 | 2 | 25.00% |
| rare | 7 | 6 | 85.71% |
| insufficient_data | 5 | 0 | 0.00% |

## 详细测试结果

### CASE-001: 信息完整-脂肪肝-中年男性 ✅ 通过

**类型**: 信息完整

**患者信息**: 48岁, male, 主诉: 体检发现脂肪肝3个月

#### L1层测试结果

- 状态: ✅
- 预期触发信息不全: False
- 实际触发信息不全: False
- 预期缺失字段: []
- 实际缺失字段: []
- 数据完整度评分: 0.86

#### L2层测试结果

- 状态: ✅
- 预期分诊路径: common
- 实际分诊路径: common
- 预期诊断关键词: ['代谢相关脂肪性肝病', 'MASLD', '脂肪肝']
- 实际诊断: 代谢相关脂肪性肝病 (MASLD)
- 预期罕见病预警: False
- 实际罕见病预警: False
- 预期置信度: ['high', 'medium']
- 实际置信度: high

### CASE-002: 信息完整-酒精性肝病-中年男性 ✅ 通过

**类型**: 信息完整

**患者信息**: 53岁, male, 主诉: 乏力、食欲差2个月

#### L1层测试结果

- 状态: ✅
- 预期触发信息不全: False
- 实际触发信息不全: False
- 预期缺失字段: []
- 实际缺失字段: []
- 数据完整度评分: 0.93

#### L2层测试结果

- 状态: ✅
- 预期分诊路径: common
- 实际分诊路径: common
- 预期诊断关键词: ['酒精', 'ALD']
- 实际诊断: 酒精性肝病 (ALD)
- 预期罕见病预警: False
- 实际罕见病预警: False
- 预期置信度: ['high', 'medium']
- 实际置信度: high

### CASE-003: 信息完整-Wilson病-年轻女性 ✅ 通过

**类型**: 信息完整

**患者信息**: 16岁, female, 主诉: 手抖、肝功能异常半年

#### L1层测试结果

- 状态: ✅
- 预期触发信息不全: False
- 实际触发信息不全: False
- 预期缺失字段: []
- 实际缺失字段: []
- 数据完整度评分: 0.96

#### L2层测试结果

- 状态: ✅
- 预期分诊路径: rare
- 实际分诊路径: rare
- 预期诊断关键词: ['Wilson', '肝豆']
- 实际诊断: Wilson 病（肝豆状核变性）
- 预期罕见病预警: True
- 实际罕见病预警: True
- 预期置信度: ['high', 'medium']
- 实际置信度: high

### CASE-004: 信息完整-自身免疫性肝炎-中年女性 ✅ 通过

**类型**: 信息完整

**患者信息**: 42岁, female, 主诉: 乏力、黄疸2周

#### L1层测试结果

- 状态: ✅
- 预期触发信息不全: False
- 实际触发信息不全: False
- 预期缺失字段: []
- 实际缺失字段: []
- 数据完整度评分: 0.93

#### L2层测试结果

- 状态: ✅
- 预期分诊路径: rare
- 实际分诊路径: rare
- 预期诊断关键词: ['自身免疫性肝炎', 'AIH']
- 实际诊断: 自身免疫性肝炎 (AIH)
- 预期罕见病预警: True
- 实际罕见病预警: True
- 预期置信度: ['high', 'medium']
- 实际置信度: high

### CASE-005: 关键缺失-无肝功能检查 ❌ 失败

**类型**: 关键信息缺失

**患者信息**: 35岁, male, 主诉: 体检发现肝脏问题

#### L1层测试结果

- 状态: ✅
- 预期触发信息不全: True
- 实际触发信息不全: True
- 预期缺失字段: ['ALT', 'AST', 'TBil']
- 实际缺失字段: ['TBil（肝功能）', 'AST（肝功能）', 'ALT（肝功能）']
- 数据完整度评分: 0.42

#### L2层测试结果

- 状态: ❌
- 预期分诊路径: uncertain
- 实际分诊路径: common
- 预期诊断关键词: []
- 实际诊断: 代谢相关脂肪性肝病 (MASLD)
- 预期罕见病预警: False
- 实际罕见病预警: False
- 预期置信度: ['insufficient_data', 'low']
- 实际置信度: medium

- **差异详情**: `{"path_mismatch": {"expected": "uncertain", "actual": "common"}, "confidence_mismatch": {"expected": ["insufficient_data", "low"], "actual": "medium"}}`

### CASE-006: 关键缺失-无影像学检查 ❌ 失败

**类型**: 关键信息缺失

**患者信息**: 55岁, male, 主诉: 腹胀、乏力1个月

#### L1层测试结果

- 状态: ✅
- 预期触发信息不全: True
- 实际触发信息不全: True
- 预期缺失字段: ['超声', '影像学']
- 实际缺失字段: ['腹部影像学（超声/CT/MRI）']
- 数据完整度评分: 0.58

#### L2层测试结果

- 状态: ❌
- 预期分诊路径: uncertain
- 实际分诊路径: common
- 预期诊断关键词: []
- 实际诊断: 酒精性肝病 (ALD)
- 预期罕见病预警: False
- 实际罕见病预警: False
- 预期置信度: ['insufficient_data', 'low']
- 实际置信度: medium

- **差异详情**: `{"path_mismatch": {"expected": "uncertain", "actual": "common"}, "confidence_mismatch": {"expected": ["insufficient_data", "low"], "actual": "medium"}}`

### CASE-007: 关键缺失-无年龄性别 ❌ 失败

**类型**: 关键信息缺失

**患者信息**: None岁, None, 主诉: 肝功能异常

#### L1层测试结果

- 状态: ❌
- 预期触发信息不全: True
- 实际触发信息不全: True
- 预期缺失字段: ['年龄', '性别']
- 实际缺失字段: ['饮酒史', '性别', '年龄', '用药史']
- 数据完整度评分: 0.50

- **差异详情**: `{"score_above_threshold": {"expected": "<0.5", "actual": 0.5}}`

#### L2层测试结果

- 状态: ❌
- 预期分诊路径: uncertain
- 实际分诊路径: insufficient_data
- 预期诊断关键词: []
- 实际诊断: 
- 预期罕见病预警: False
- 实际罕见病预警: False
- 预期置信度: ['insufficient_data', 'low']
- 实际置信度: insufficient_data

- **差异详情**: `{"path_mismatch": {"expected": "uncertain", "actual": "insufficient_data"}}`

### CASE-008: 关键缺失-无主诉 ❌ 失败

**类型**: 关键信息缺失

**患者信息**: 40岁, female, 主诉: None

#### L1层测试结果

- 状态: ✅
- 预期触发信息不全: True
- 实际触发信息不全: True
- 预期缺失字段: ['主诉']
- 实际缺失字段: ['主诉', '用药史']
- 数据完整度评分: 0.52

#### L2层测试结果

- 状态: ❌
- 预期分诊路径: uncertain
- 实际分诊路径: insufficient_data
- 预期诊断关键词: []
- 实际诊断: 
- 预期罕见病预警: False
- 实际罕见病预警: False
- 预期置信度: ['insufficient_data', 'low']
- 实际置信度: insufficient_data

- **差异详情**: `{"path_mismatch": {"expected": "uncertain", "actual": "insufficient_data"}}`

### CASE-009: 非关键缺失-无饮酒史 ❌ 失败

**类型**: 非关键信息缺失

**患者信息**: 50岁, male, 主诉: 体检发现肝功能异常

#### L1层测试结果

- 状态: ❌
- 预期触发信息不全: False
- 实际触发信息不全: True
- 预期缺失字段: []
- 实际缺失字段: ['饮酒史']
- 数据完整度评分: 0.79

- **差异详情**: `{"trigger_mismatch": {"expected": false, "actual": true}}`

#### L2层测试结果

- 状态: ❌
- 预期分诊路径: common
- 实际分诊路径: common
- 预期诊断关键词: ['脂肪肝', 'NAFLD']
- 实际诊断: 代谢相关脂肪性肝病 (MASLD)
- 预期罕见病预警: False
- 实际罕见病预警: False
- 预期置信度: ['medium', 'high']
- 实际置信度: medium

- **差异详情**: `{"diagnosis_mismatch": {"expected_keywords": ["脂肪肝", "NAFLD"], "actual_diagnosis": "代谢相关脂肪性肝病 (MASLD)"}}`

### CASE-010: 非关键缺失-无家族史 ❌ 失败

**类型**: 非关键信息缺失

**患者信息**: 22岁, male, 主诉: 震颤伴肝功能异常

#### L1层测试结果

- 状态: ❌
- 预期触发信息不全: False
- 实际触发信息不全: True
- 预期缺失字段: []
- 实际缺失字段: ['TBil（肝功能）']
- 数据完整度评分: 0.70

- **差异详情**: `{"trigger_mismatch": {"expected": false, "actual": true}}`

#### L2层测试结果

- 状态: ✅
- 预期分诊路径: rare
- 实际分诊路径: rare
- 预期诊断关键词: ['Wilson', '肝豆']
- 实际诊断: Wilson 病（肝豆状核变性）
- 预期罕见病预警: True
- 实际罕见病预警: True
- 预期置信度: ['high', 'medium']
- 实际置信度: high

### CASE-011: 信息完整-病毒性肝炎-中年男性 ❌ 失败

**类型**: 信息完整

**患者信息**: 38岁, male, 主诉: 乏力、食欲减退2周

#### L1层测试结果

- 状态: ✅
- 预期触发信息不全: False
- 实际触发信息不全: False
- 预期缺失字段: []
- 实际缺失字段: []
- 数据完整度评分: 0.86

#### L2层测试结果

- 状态: ❌
- 预期分诊路径: common
- 实际分诊路径: common
- 预期诊断关键词: ['乙肝', '病毒性肝炎', 'HBV']
- 实际诊断: 慢性乙型肝炎
- 预期罕见病预警: False
- 实际罕见病预警: False
- 预期置信度: ['high']
- 实际置信度: high

- **差异详情**: `{"diagnosis_mismatch": {"expected_keywords": ["乙肝", "病毒性肝炎", "HBV"], "actual_diagnosis": "慢性乙型肝炎"}}`

### CASE-012: 信息完整-药物性肝损伤 ❌ 失败

**类型**: 信息完整

**患者信息**: 45岁, female, 主诉: 服用中药后出现黄疸1周

#### L1层测试结果

- 状态: ✅
- 预期触发信息不全: False
- 实际触发信息不全: False
- 预期缺失字段: []
- 实际缺失字段: []
- 数据完整度评分: 0.88

#### L2层测试结果

- 状态: ❌
- 预期分诊路径: common
- 实际分诊路径: rare
- 预期诊断关键词: ['药物性', 'DILI']
- 实际诊断: 原发性胆汁性胆管炎 (PBC)
- 预期罕见病预警: False
- 实际罕见病预警: True
- 预期置信度: ['high', 'medium']
- 实际置信度: high

- **差异详情**: `{"path_mismatch": {"expected": "common", "actual": "rare"}, "diagnosis_mismatch": {"expected_keywords": ["药物性", "DILI"], "actual_diagnosis": "原发性胆汁性胆管炎 (PBC)"}, "rare_alert_mismatch": {"expected": false, "actual": true}}`

### CASE-013: 关键缺失-无病毒标志物 ❌ 失败

**类型**: 关键信息缺失

**患者信息**: 42岁, male, 主诉: 乏力、肝功能异常

#### L1层测试结果

- 状态: ❌
- 预期触发信息不全: True
- 实际触发信息不全: True
- 预期缺失字段: ['HBsAg', '病毒标志物']
- 实际缺失字段: []
- 数据完整度评分: 0.66

- **差异详情**: `{"missing_field_mismatch": ["HBsAg", "病毒标志物"]}`

#### L2层测试结果

- 状态: ❌
- 预期分诊路径: uncertain
- 实际分诊路径: common
- 预期诊断关键词: []
- 实际诊断: 急性病毒性肝炎
- 预期罕见病预警: False
- 实际罕见病预警: False
- 预期置信度: ['insufficient_data', 'low']
- 实际置信度: high

- **差异详情**: `{"path_mismatch": {"expected": "uncertain", "actual": "common"}, "confidence_mismatch": {"expected": ["insufficient_data", "low"], "actual": "high"}}`

### CASE-014: 信息完整-PBC-中年女性 ✅ 通过

**类型**: 信息完整

**患者信息**: 55岁, female, 主诉: 皮肤瘙痒、乏力半年

#### L1层测试结果

- 状态: ✅
- 预期触发信息不全: False
- 实际触发信息不全: False
- 预期缺失字段: []
- 实际缺失字段: []
- 数据完整度评分: 0.80

#### L2层测试结果

- 状态: ✅
- 预期分诊路径: rare
- 实际分诊路径: rare
- 预期诊断关键词: ['PBC', '原发性胆汁性胆管炎']
- 实际诊断: 原发性胆汁性胆管炎 (PBC)
- 预期罕见病预警: True
- 实际罕见病预警: True
- 预期置信度: ['high', 'medium']
- 实际置信度: high

### CASE-015: 信息完整-血色病-中年男性 ✅ 通过

**类型**: 信息完整

**患者信息**: 52岁, male, 主诉: 皮肤变黑、乏力、关节痛2年

#### L1层测试结果

- 状态: ✅
- 预期触发信息不全: False
- 实际触发信息不全: False
- 预期缺失字段: []
- 实际缺失字段: []
- 数据完整度评分: 0.84

#### L2层测试结果

- 状态: ✅
- 预期分诊路径: rare
- 实际分诊路径: rare
- 预期诊断关键词: ['血色病', 'hemochromatosis']
- 实际诊断: 遗传性血色病
- 预期罕见病预警: True
- 实际罕见病预警: True
- 预期置信度: ['high', 'medium']
- 实际置信度: high

### CASE-016: 非关键缺失-无BMI ❌ 失败

**类型**: 非关键信息缺失

**患者信息**: 50岁, female, 主诉: 体检发现肝功能异常

#### L1层测试结果

- 状态: ✅
- 预期触发信息不全: False
- 实际触发信息不全: False
- 预期缺失字段: []
- 实际缺失字段: []
- 数据完整度评分: 0.73

#### L2层测试结果

- 状态: ❌
- 预期分诊路径: common
- 实际分诊路径: common
- 预期诊断关键词: ['脂肪肝']
- 实际诊断: 代谢相关脂肪性肝病 (MASLD)
- 预期罕见病预警: False
- 实际罕见病预警: False
- 预期置信度: ['medium', 'high']
- 实际置信度: medium

- **差异详情**: `{"diagnosis_mismatch": {"expected_keywords": ["脂肪肝"], "actual_diagnosis": "代谢相关脂肪性肝病 (MASLD)"}}`

### CASE-017: 边缘病例-老年患者轻度异常 ❌ 失败

**类型**: 信息完整

**患者信息**: 72岁, male, 主诉: 体检发现肝功能轻度异常

#### L1层测试结果

- 状态: ✅
- 预期触发信息不全: False
- 实际触发信息不全: False
- 预期缺失字段: []
- 实际缺失字段: []
- 数据完整度评分: 0.82

#### L2层测试结果

- 状态: ❌
- 预期分诊路径: common
- 实际分诊路径: insufficient_data
- 预期诊断关键词: []
- 实际诊断: 
- 预期罕见病预警: False
- 实际罕见病预警: False
- 预期置信度: ['medium', 'low']
- 实际置信度: insufficient_data

- **差异详情**: `{"path_mismatch": {"expected": "common", "actual": "insufficient_data"}, "confidence_mismatch": {"expected": ["medium", "low"], "actual": "insufficient_data"}}`

### CASE-018: 边缘病例-年轻无症状 ❌ 失败

**类型**: 信息完整

**患者信息**: 25岁, female, 主诉: 体检发现转氨酶升高

#### L1层测试结果

- 状态: ✅
- 预期触发信息不全: False
- 实际触发信息不全: False
- 预期缺失字段: []
- 实际缺失字段: []
- 数据完整度评分: 0.82

#### L2层测试结果

- 状态: ❌
- 预期分诊路径: common
- 实际分诊路径: insufficient_data
- 预期诊断关键词: []
- 实际诊断: 
- 预期罕见病预警: False
- 实际罕见病预警: False
- 预期置信度: ['medium', 'low']
- 实际置信度: insufficient_data

- **差异详情**: `{"path_mismatch": {"expected": "common", "actual": "insufficient_data"}, "confidence_mismatch": {"expected": ["medium", "low"], "actual": "insufficient_data"}}`

### CASE-019: 关键缺失-多项关键信息缺失 ❌ 失败

**类型**: 关键信息缺失

**患者信息**: None岁, None, 主诉: 不舒服

#### L1层测试结果

- 状态: ✅
- 预期触发信息不全: True
- 实际触发信息不全: True
- 预期缺失字段: ['年龄', '性别', 'AST', 'TBil', '影像学']
- 实际缺失字段: ['性别', '饮酒史', '用药史', 'TBil（肝功能）', 'AST（肝功能）', '腹部影像学（超声/CT/MRI）', '年龄']
- 数据完整度评分: 0.18

#### L2层测试结果

- 状态: ❌
- 预期分诊路径: uncertain
- 实际分诊路径: insufficient_data
- 预期诊断关键词: []
- 实际诊断: 
- 预期罕见病预警: False
- 实际罕见病预警: False
- 预期置信度: ['insufficient_data']
- 实际置信度: insufficient_data

- **差异详情**: `{"path_mismatch": {"expected": "uncertain", "actual": "insufficient_data"}}`

### CASE-020: 信息完整-儿童Wilson病 ✅ 通过

**类型**: 信息完整

**患者信息**: 10岁, male, 主诉: 肝功能异常、学习成绩下降

#### L1层测试结果

- 状态: ✅
- 预期触发信息不全: False
- 实际触发信息不全: False
- 预期缺失字段: []
- 实际缺失字段: []
- 数据完整度评分: 0.82

#### L2层测试结果

- 状态: ✅
- 预期分诊路径: rare
- 实际分诊路径: rare
- 预期诊断关键词: ['Wilson', '肝豆']
- 实际诊断: Wilson 病（肝豆状核变性）
- 预期罕见病预警: True
- 实际罕见病预警: True
- 预期置信度: ['high']
- 实际置信度: high
