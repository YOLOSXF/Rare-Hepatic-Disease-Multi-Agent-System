# 工具模块使用指南

**更新时间：** 2026-04-10  
**状态：** ✅ 已完成

---

## 📁 工具模块结构

```
tools/
├── __init__.py                  # 模块导出
├── hpo_extractor.py             # HPO 术语提取器 ✅
├── adaptive_classifier.py       # 自适应分类器 ✅
├── guideline_search.py          # 指南搜索（待实现）
├── pubmed_search.py             # PubMed 搜索（待实现）
├── web_search.py                # Web 搜索（待实现）
└── rare_disease_db.py           # 罕见病数据库（待实现）
```

---

## 🔧 可用工具

### 1. HPOExtractor（HPO 术语提取器）

**用途：** 从病历文本提取表型术语并映射到 HPO 代码

**导入：**
```python
from tools import HPOExtractor
```

**使用示例：**
```python
# 创建提取器
extractor = HPOExtractor()

# 从文本提取
text = "患者乏力、黄疸 2 周，伴手部震颤"
phenotypes = extractor.extract_phenotypes(text)
print(phenotypes)  # ['乏力', '黄疸', '震颤']

# 提取并映射到 HPO
results = extractor.extract_and_map(text)
for result in results:
    print(f"{result['phenotype']} → {result['hpo_id']}")
# 乏力 → HP:0012378
# 黄疸 → HP:0000952
# 震颤 → HP:0001337

# 从结构化数据提取
patient_data = {
    "symptoms": {"tremor": True, "jaundice": True},
    "chief_complaint": "乏力 2 周"
}
results = extractor.extract_from_structured_data(patient_data)
```

**方法说明：**
| 方法 | 说明 | 返回值 |
|------|------|--------|
| `extract_phenotypes(text)` | 从文本提取表型 | `List[str]` |
| `map_to_hpo(phenotypes)` | 映射到 HPO 代码 | `List[Dict]` |
| `extract_and_map(text)` | 提取 + 映射一站式 | `List[Dict]` |
| `extract_from_structured_data(data)` | 从结构化数据提取 | `List[Dict]` |

**参考项目：** DeepRare `hpo_extractor.py`

---

### 2. AdaptiveCaseClassifier（自适应病例分类器）

**用途：** 根据病历复杂度自动分为简单/中等/复杂

**导入：**
```python
from tools import AdaptiveCaseClassifier
```

**使用示例：**
```python
# 创建分类器
classifier = AdaptiveCaseClassifier()

# 分类病历
patient_data = {
    "age": 23,
    "gender": "male",
    "chief_complaint": "乏力、黄疸 2 周，伴震颤",
    "symptoms": {
        "tremor": True,
        "jaundice": True,
        "fatigue": True,
        "dysarthria": True
    },
    "labs": {
        "ALT": 125,
        "AST": 98,
        "TBil": 52.5
    }
}

result = classifier.classify(patient_data)
print(f"分类：{result['complexity']}")
print(f"置信度：{result['confidence']}")
print(f"推荐路径：{result['recommended_track']}")
```

**输出示例：**
```
分类：复杂
置信度：0.8
推荐路径：rare_track
```

**分类标准：**
| 分类 | 特征 | 推荐路径 |
|------|------|---------|
| **简单** | 症状≤3 个，检验异常<2 项 | common_track |
| **中等** | 症状 4-5 个，检验异常 2-3 项 | common_track |
| **复杂** | 症状≥6 个，检验异常≥4 项 | rare_track/uncertain_track |

**方法说明：**
| 方法 | 说明 | 返回值 |
|------|------|--------|
| `classify(patient_data)` | 分类病历 | `Dict` |
| `_extract_features(patient_data)` | 提取特征 | `Dict` |
| `_classify_with_llm(features, data, llm)` | LLM 分类 | `Dict` |
| `_classify_with_rules(features)` | 规则分类 | `Dict` |

**参考项目：** HEAL `0910-adaptive framework.py`

---

## 🔧 在编排器中使用

### 在 LangGraph 中使用 HPO 提取器

```python
from core.langgraph_orchestrator import LangGraphOrchestrator
from tools import HPOExtractor

# 创建编排器和提取器
orchestrator = LangGraphOrchestrator(rules_dir="rules")
hpo_extractor = HPOExtractor()

# 在预处理节点使用
patient_text = "患者乏力、黄疸 2 周..."
hpo_results = hpo_extractor.extract_and_map(patient_text)

# 添加到患者数据
patient_data["hpo_terms"] = hpo_results

# 执行诊断
report = await orchestrator.run_diagnosis(patient_data)
```

### 在分诊中使用自适应分类器

```python
from core.triage import IntelligentTriage
from tools import AdaptiveCaseClassifier

# 创建分诊器和分类器
triage = IntelligentTriage(rules_dir="rules")
classifier = AdaptiveCaseClassifier()

# 先分类
classification = classifier.classify(patient_data)

# 根据分类选择分诊策略
if classification["complexity"] == "简单":
    # 快速分诊
    result = await triage.quick_triage(patient_data)
elif classification["complexity"] == "复杂":
    # 深度分诊
    result = await triage.deep_triage(patient_data)
else:
    # 标准分诊
    result = await triage.triage(patient_data)
```

---

## 📦 依赖安装

```bash
# 核心依赖
pip install langchain langchain-community langchain-openai

# 环境变量支持
pip install python-dotenv
```

---

## 🧪 测试工具模块

### 测试 HPO 提取器
```bash
cd /home/user/agent/medical-agent
source /home/admin/miniconda3/bin/activate shenxf
python tools/hpo_extractor.py
```

### 测试自适应分类器
```bash
cd /home/user/agent/medical-agent
source /home/admin/miniconda3/bin/activate shenxf
python tools/adaptive_classifier.py
```

### 测试导入
```bash
python -c "from tools import HPOExtractor, AdaptiveCaseClassifier; print('✅ 导入成功')"
```

---

## 📊 工具模块架构

```
┌─────────────────────────────────────────┐
│  tools/ 工具模块                         │
├─────────────────────────────────────────┤
│                                         │
│  ┌─────────────────┐  ┌──────────────┐ │
│  │ HPOExtractor    │  │ Adaptive     │ │
│  │                 │  │ Classifier   │ │
│  │ • 表型提取      │  │              │ │
│  │ • HPO 映射       │  │ • 简单/中等/  │ │
│  │ • LLM + 规则     │  │   复杂分类    │ │
│  └─────────────────┘  └──────────────┘ │
│                                         │
│  预留接口：                             │
│  • GuidelineSearch (指南搜索)           │
│  • PubMedSearch (文献检索)              │
│  • WebSearch (Web 检索)                 │
│  • RareDiseaseDB (罕见病数据库)         │
└─────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────┐
│  core/ 核心模块                          │
│  • llm_client.py (LLM 客户端)            │
│  • triage.py (分诊)                      │
│  • langgraph_orchestrator.py (编排)     │
└─────────────────────────────────────────┘
```

---

## ✅ 验证清单

- [x] HPO 提取器在 tools/目录
- [x] 自适应分类器在 tools/目录
- [x] tools/__init__.py 更新
- [x] 导入测试通过
- [x] 功能测试通过
- [x] 文档完善

---

## 📚 参考文档

- `tests/TOOLS_TEST_REPORT.md` - 工具模块测试报告
- `docs/PHASE1_SUMMARY.md` - 阶段 1 实施总结
- `docs/ENV_CONFIG_GUIDE.md` - 环境变量配置指南

---

**维护人员：** AI Assistant  
**最后更新：** 2026-04-10
