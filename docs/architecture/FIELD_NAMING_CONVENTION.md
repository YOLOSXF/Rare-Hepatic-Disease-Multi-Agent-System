# 字段命名规范

**生效时间：** 2026-04-10  
**适用范围：** 所有患者数据输入、Agent 输入输出、状态传递

---

## 📐 命名原则

**统一使用小写 + 下划线**（snake_case），避免大小写敏感问题。

---

## 📋 标准字段定义

### 1. 患者基本信息

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `patient_id` | string | 患者 ID | "P001" |
| `age` | int | 年龄 | 45 |
| `gender` | string | 性别 | "male"/"female" |
| `chief_complaint` | string | 主诉 | "乏力、黄疸 2 周" |

### 2. 病史字段

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `history.alcohol_intake` | int | 每周饮酒量 (g) | 50 |
| `history.medication_history` | string | 用药史 | "无特殊用药" |
| `history.liver_disease_history` | string | 既往肝病史 | "脂肪肝 3 年" |
| `history.family_history` | list | 家族史 | ["父亲乙肝"] |
| `history.smoking` | bool | 吸烟史 | true |

### 3. 症状字段

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `symptoms.tremor` | bool | 震颤 | true |
| `symptoms.dysarthria` | bool | 构音障碍 | false |
| `symptoms.jaundice` | bool | 黄疸 | true |
| `symptoms.fatigue` | bool | 乏力 | true |
| `symptoms.pruritus` | bool | 瘙痒 | false |

### 4. 实验室检查（labs）

**统一使用小写，但检验项目缩写保持大写**

| 字段 | 类型 | 说明 | 单位 |
|------|------|------|------|
| `labs.ALT` | float | 谷丙转氨酶 | U/L |
| `labs.AST` | float | 谷草转氨酶 | U/L |
| `labs.TBil` | float | 总胆红素 | μmol/L |
| `labs.DBil` | float | 直接胆红素 | μmol/L |
| `labs.ALP` | float | 碱性磷酸酶 | U/L |
| `labs.GGT` | float | γ-谷氨酰转肽酶 | U/L |
| `labs.Albumin` | float | 白蛋白 | g/L |
| `labs.PT` | float | 凝血酶原时间 | 秒 |
| `labs.INR` | float | 国际标准化比值 | - |
| `labs.Platelet` | float | 血小板 | ×10^9/L |
| `labs.Ceruloplasmin` | float | 铜蓝蛋白 | g/L |
| `labs.IgG` | float | 免疫球蛋白 G | g/L |
| `labs.Ferritin` | float | 铁蛋白 | μg/L |
| `labs.ANA` | string | 抗核抗体 | "positive"/"negative" |
| `labs.SMA` | string | 平滑肌抗体 | "positive"/"negative" |
| `labs.AMA` | string | 抗线粒体抗体 | "positive"/"negative" |
| `labs.HBsAg` | string | 乙肝表面抗原 | "positive"/"negative" |
| `labs.Anti_HCV` | string | 丙肝抗体 | "positive"/"negative" |

### 5. 影像学检查

| 字段 | 类型 | 说明 |
|------|------|------|
| `ultrasound.findings` | string | 超声所见 |
| `ultrasound.impression` | string | 超声印象 |
| `ct.findings` | string | CT 所见 |
| `ct.impression` | string | CT 印象 |
| `mri.findings` | string | MRI 所见 |
| `mri.impression` | string | MRI 印象 |

### 6. 特殊检查

| 字段 | 类型 | 说明 |
|------|------|------|
| `eye_exam.kf_ring` | string | K-F 环 |
| `eye_exam.description` | string | 眼科检查描述 |
| `brain_mri.findings` | string | 脑部 MRI 所见 |
| `brain_mri.impression` | string | 脑部 MRI 印象 |

---

## 🔧 字段映射表（兼容旧格式）

| 旧字段名 | 新字段名 | 处理方式 |
|---------|---------|---------|
| `lab_results` | `labs` | 自动映射 |
| `imaging_results` | `ultrasound`/`ct`/`mri` | 自动映射 |
| `hpi` | `symptoms` | 自动映射 |
| `pmh` | `history` | 自动映射 |
| `physical_exam` | `exam` | 自动映射 |

---

## 📝 使用示例

```python
# ✅ 正确格式
patient_data = {
    "patient_id": "P001",
    "age": 45,
    "gender": "male",
    "chief_complaint": "乏力、黄疸 2 周",
    "history": {
        "alcohol_intake": 50,
        "medication_history": "无特殊用药"
    },
    "symptoms": {
        "jaundice": True,
        "fatigue": True
    },
    "labs": {
        "ALT": 125,
        "AST": 98,
        "TBil": 52.5,
        "Ceruloplasmin": 0.08
    },
    "ultrasound": {
        "findings": "肝脏回声增粗"
    }
}

# ❌ 错误格式（大小写混乱）
patient_data = {
    "lab_results": {...},  # 应改为 labs
    "Ceruloplasmin": 0.08,  # 应在 labs 下
    "KF_Ring": "阳性"  # 应改为 eye_exam.kf_ring
}
```

---

## ⚠️ 注意事项

1. **规则文件中的字段路径** 必须与输入数据一致
2. **Agent 输入输出** 统一使用新规范
3. **向后兼容**：系统会自动映射旧字段到新字段
