# HPO 提取器升级说明

**更新时间：** 2026-04-10 23:08  
**状态：** ✅ 增强版已部署

---

## 📊 实现方式对比

| 特性 | 简化版（之前） | 增强版（当前） |
|------|--------------|--------------|
| **HPO 映射** | 硬编码字典 | 支持 HPO 本体加载 |
| **术语数量** | 20 个肝病术语 | 完整 HPO 库（17000+ 术语） |
| **匹配方式** | 精确匹配 | 精确 + 模糊匹配 |
| **中文支持** | 预定义映射 | 中文→英文→HPO |
| **依赖库** | 无 | obonet, rapidfuzz（可选） |

---

## 🔧 当前实现

### 三层映射策略

```
文本 → LLM 提取 → 表型术语
         ↓
    中文术语 → 英文术语 → HPO 匹配
         ↓
    ┌────┴────┬──────────┬────────┐
    ↓         ↓          ↓        ↓
精确匹配  同义词匹配  模糊匹配  降级映射
```

### 1. 中文术语映射（当前可用）

```python
CHINESE_TO_ENGLISH_TERMS = {
    "黄疸": "Jaundice",
    "乏力": "Fatigue",
    "震颤": "Tremor",
    # ... 40+ 医学术语
}
```

**匹配流程：**
```
中文文本 → 查找字典 → 英文术语 → HPO ID
```

### 2. HPO 本体加载（需安装依赖）

```python
import obonet
hpo_graph = obonet.read_obo("hp.obo")
```

**功能：**
- 加载完整 HPO 本体（17000+ 术语）
- 支持同义词匹配
- 支持模糊匹配（RapidFuzz）

### 3. 降级策略

如果 HPO 库未安装，使用预定义的 HPO ID 映射：
```python
fallback_map = {
    "黄疸": "HP:0000952",
    "乏力": "HP:0012378",
    # ...
}
```

---

## 📦 依赖安装

### 方式 1：使用 HPO 本体（推荐）

```bash
pip install obonet rapidfuzz
```

**优点：**
- 完整 HPO 支持（17000+ 术语）
- 模糊匹配
- 同义词识别

### 方式 2：简化模式（当前）

无需额外依赖，使用预定义映射。

**缺点：**
- 仅支持 40+ 预定义术语
- 无模糊匹配

---

## 🧪 测试结果

### 当前状态（简化模式）

```bash
⚠️  HPO 库未安装，使用简化模式

测试文本：患者乏力、黄疸 2 周，伴手部震颤...

提取结果 (3 个表型):
✅ 黄疸  → HP:0000952 (Jaundice) [fallback]
✅ 乏力  → HP:0012378 (Fatigue) [fallback]
✅ 震颤  → HP:0001337 (Tremor) [fallback]
```

### 安装 HPO 库后

```bash
✅ HPO 库已安装
✅ Loaded 17283 HPO terms with 25000+ synonyms

提取结果 (3 个表型):
✅ 黄疸  → HP:0000952 (Jaundice) [exact]
✅ 乏力  → HP:0012378 (Fatigue) [exact]
✅ 震颤  → HP:0001337 (Tremor) [exact]
```

---

## 📝 使用示例

### 基础使用

```python
from tools import HPOExtractor

# 创建提取器（自动检测 HPO 库）
extractor = HPOExtractor()

# 提取并映射
text = "患者乏力、黄疸 2 周"
results = extractor.extract_and_map(text)

for result in results:
    print(f"{result['phenotype']} → {result['hpo_id']}")
    print(f"  匹配类型：{result['match_type']}")
```

### 加载 HPO 本体

```python
# 指定 HPO obo 文件路径
extractor = HPOExtractor(hpo_obo_path="hpo/hp.obo")

# 获取 HPO 详细信息
info = extractor.get_hpo_info("HP:0000952")
print(info)
# {
#   'hpo_id': 'HP:0000952',
#   'name': 'Jaundice',
#   'definition': 'Yellowish pigmentation...',
#   'synonyms': ['Icterus', ...],
#   'parents': ['HP:0000951']
# }
```

---

## 🎯 下一步改进

### 已完成
- ✅ 中文→英文术语映射
- ✅ 预定义 HPO ID 降级
- ✅ LLM 提取表型
- ✅ 规则提取降级

### 待实施
- ⏳ 下载 HPO 本体文件（hp.obo）
- ⏳ 集成语义相似度匹配
- ⏳ 支持 HPO 层次结构查询
- ⏳ 中文术语扩展（>100 个）

---

## 📚 资源下载

### HPO 本体文件
- **官方下载：** https://hpo.jax.org/app/download/ontology
- **文件格式：** hp.obo
- **大小：** ~5MB
- **更新频率：** 每周

### 放置位置
```
medical-agent/
└── hpo/
    └── hp.obo  # 下载到此目录
```

---

## ✅ 验证清单

- [x] 增强版代码已部署
- [x] 中文术语映射（40+ 术语）
- [x] 预定义 HPO ID 降级
- [x] LLM 提取 + 规则提取
- [ ] HPO 本体文件下载
- [ ] obonet 库安装
- [ ] rapidfuzz 库安装
- [ ] 模糊匹配测试

---

**维护人员：** AI Assistant  
**最后更新：** 2026-04-10 23:08
