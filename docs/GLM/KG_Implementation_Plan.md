# 罕见肝病知识图谱构建实施方案

> **版本**: v4.0  
> **日期**: 2026-05-12  
> **状态**: 待审批  
> **编制依据**: `docs/GLM/KG_Construction_方案.md` v3.0、`docs/DEEPSEEK/KG_Build.md`、`docs/GLM/图谱参考-glm.md`、`docs/architecture/ARCHITECTURE_DESIGN_ANALYSIS.md`  
> **参考代码仓库**: `ImprintLab/Medical-Graph-RAG`(MedGraphRAG) + `SNOWTEAM2023/MedRAG`(MedRAG)  
> **核心约束**: YAML规则未经验证不用于KG构建 | HPO本体文件未下载 | 仅指南PDF为权威数据源  
> **v4.0 更新说明**: 基于对两个参考仓库全部源码的逐行分析，(1) 新增"源码精确映射表"(4.7节)——每个移植组件标注精确源文件路径+函数签名+行号范围+参数说明；(2) 新增"移植操作指南"(4.8节)——开发者可按步骤操作的移植流程；(3) 补充缺失实现细节——关系类型推断逻辑(4.3.6)、并发信号量控制(5.5)、节点合并去重逻辑(4.3.7)、子图检索上下文格式(4.5.3)、Summary节点创建(4.3.8)、跨层REFERENCE链接(4.3.4)、LLM相似度检索(4.5.4)；(4) 修正代码错误——移除Gleaning中的跨仓库import；(5) 整合两份参考文档(图谱参考-glm.md/KG_Build.md)的架构洞察

---

## 目录

1. [项目背景与目标](#1-项目背景与目标)
2. [当前状态基线](#2-当前状态基线)
3. [技术架构设计](#3-技术架构设计)
4. [代码级实现细节](#4-代码级实现细节)
5. [工程优化方案](#5-工程优化方案)
6. [实施阶段划分与任务分解](#6-实施阶段划分与任务分解)
7. [各阶段详细任务与时间节点](#7-各阶段详细任务与时间节点)
8. [资源配置](#8-资源配置)
9. [质量控制标准与验收指标](#9-质量控制标准与验收指标)
10. [潜在风险评估及应对措施](#10-潜在风险评估及应对措施)
11. [项目交付物清单](#11-项目交付物清单)
12. [长期演进路径](#12-长期演进路径)

---

## 1. 项目背景与目标

### 1.1 项目背景

罕见肝病多智能体诊断系统（Rare-Hepatic-Disease-Multi-Agent-System）当前采用LangGraph StateGraph五层架构，包含15个节点和7个中间件。系统在知识检索和诊断推理方面存在以下核心问题：

| 问题 | 现状 | 影响 |
|------|------|------|
| **知识检索能力弱** | `knowledge_retriever.py`为空壳实现，`memory_retriever.py`返回占位值 | 无法提供有效的医学知识支撑 |
| **诊断规则硬编码** | `falsification.py`和`guideline_verifier.py`使用if-elif硬编码规则 | 难以扩展、维护成本高 |
| **图权重更新伪实现** | `GraphUpdater`(EWAS)仅操作`Dict[str,float]`，使用`FakeDebateResult` hack | 无实际图推理能力 |
| **数据源未经验证** | YAML规则和内置数据库未经专家审核，存在阈值冲突 | 知识可信度无法保证 |
| **向量检索零实现** | Milvus配置已预留但pymilvus依赖已注释，零数据存储 | 无法进行语义匹配 |

### 1.2 项目目标

#### 总体目标

构建**指南PDF驱动的三层分离+四层诊断知识图谱系统**，以增强级联检索管道为核心，实现从"自然语言症状描述"到"结构化诊断知识"的精准映射，显著提升罕见肝病诊断的准确性和可解释性。

#### 量化目标

| 指标 | 当前基线 | Phase 0-4目标 | 最终目标 |
|------|---------|-------------|---------|
| 疾病覆盖数 | 0种(KG未建) | 1种(Wilson病) | 6种(YAML定义的全部罕见肝病) |
| 诊断特征数 | 0 | ~40个(Wilson病) | ~300个(6种疾病) |
| 指南利用 | 0份 | 2份(Wilson中+英) | 10+份 |
| 知识检索延迟 | N/A | <200ms(P95) | <150ms(P95) |
| 可溯源率 | 0% | 100% | 100% |
| Top-5疾病召回率 | N/A | >85% | >90% |
| 语义匹配命中率 | 0% | >80%(top-1) | >90%(top-1) |

### 1.3 设计原则

1. **指南PDF为唯一权威数据源** — 所有KG知识从指南PDF提取，不经YAML等未验证数据源
2. **LLM提取+人工审核** — LLM负责从PDF中提取结构化知识，人工审核所有数值型阈值
3. **YAML仅作运行时参考** — YAML规则继续用于分诊引擎，不进入KG
4. **HPO本体后续接入** — 本体层标记为待建设，当前用均匀权重替代IC值
5. **预计算优于运行时计算** — 诊断差异边在构建时预计算
6. **渐进式集成** — Feature Flag控制，可随时回退
7. **三级降级** — Neo4j+Milvus → Milvus纯向量 → 文本检索

---

## 2. 当前状态基线

### 2.1 代码库现状（代码验证结果）

| 组件 | 状态 | 说明 |
|------|------|------|
| `core/kg/` 目录 | ❌ 不存在 | 仅有文档规划，无实际代码 |
| `data/guidelines/` PDF | ✅ 存在 | 2份Wilson病PDF + 1份罕见肝病目录docx |
| `GraphUpdater`(EWAS) | ⚠️ 待移除 | 纯内存权重字典操作，无外部图数据库交互，`GraphUpdateResult`数据类定义但未使用 |
| `knowledge_graph_weights` | ⚠️ 待迁移 | `state_definition.py`第254行，类型`Dict[str,float]`，使用`operator.ior`合并 |
| `_node_graph_update` 节点 | ⚠️ 待移除 | `graph_orchestrator.py`第548-565行，通过`FakeDebateResult`桥接调用 |
| Milvus | ❌ 零数据 | `config.yaml`已配置(host:localhost, port:19530)，但pymilvus依赖已注释(requirements.txt第48行)，无连接代码 |
| Neo4j | ❌ 完全缺失 | 无配置、无依赖(requirements.txt无neo4j)、无代码 |
| BGE-M3嵌入 | ❌ 未集成 | 无SentenceTransformer等导入 |
| HPO本体 | ❌ 文件未下载 | hp.obo未部署，hpo_extractor降级运行(20个预定义HPO ID) |
| KG配置段 | ❌ 不存在 | config.yaml中无`knowledge_graph`配置段 |
| KG相关依赖 | ❌ 未添加 | neo4j, pymilvus, sentence-transformers等 |

### 2.2 数据资产现状

| 数据源 | 规模 | 权威性 | KG可用性 |
|--------|------|--------|---------|
| 指南PDF(Wilson病) | 2份(中+英) | **高(权威)** | ✅ 核心数据源 |
| 罕见肝病目录 | 1份docx | 中 | ✅ 辅助EL1/EL2划分 |
| rare_diseases.yaml | 6种疾病 | **低(未验证)** | ❌ 不用于KG构建 |
| rare_disease_db.py | 5种疾病(缺PSC) | 低(未验证) | ❌ 不用于KG构建 |
| guideline_search.py | 4种疾病(缺PSC+α1AT) | 低(可能过时) | ❌ 不用于KG构建 |
| HPO本体(hp.obo) | ~16,000术语 | 高 | ❌ 文件未下载 |

### 2.3 已识别的数据冲突

| 冲突项 | 位置1 | 位置2 | 正确值(指南原文) |
|--------|------|------|----------------|
| 铜蓝蛋白阈值 | rare_diseases.yaml: `< 0.20` | guideline_verifier.py: `< 0.1` | `< 0.20 g/L` |
| EASL指南版本 | evidence_chain.py: `2012` | 实际: `2025` | `2025` |
| 曲恩汀治疗地位 | guideline_search.py: 二线 | EASL-ERN 2025: 一线 | 一线 |

---

## 3. 技术架构设计

### 3.1 三层分离+四层诊断KG架构

```
┌──────────────────────────────────────────────────────────────────────┐
│         指南PDF驱动的三层分离 + 四层诊断KG                              │
│                                                                      │
│  Layer 3: 本体层 (Ontology) — 待建设 [HPO文件未下载]                  │
│  ┌────────────────────────────────────────────────────────────┐     │
│  │  (后续下载hp.obo后接入)                                     │     │
│  │  HPO表型层级树 + IC值 + 标准术语定义                         │     │
│  │  当前替代: 均匀权重(所有特征IC值=1.0)                        │     │
│  └────────────────────────────────────────────────────────────┘     │
│                          │ Triple Linking (后续)                    │
│                          ▼                                         │
│  Layer 2: 文献层 (Literature) — 核心 [指南PDF驱动]                   │
│  ┌────────────────────────────────────────────────────────────┐     │
│  │  四层诊断KG (数据源: 指南PDF → LLM提取 → 人工审核)          │     │
│  │                                                              │     │
│  │  EL1: 疾病大类 (代谢性肝病/自身免疫性肝病/遗传性肝病/...)     │     │
│  │  EL2: 疾病亚类 (铜代谢障碍/铁代谢障碍/自身免疫肝炎组/...)     │     │
│  │  EL3: 具体疾病 (Wilson病/AIH/PBC/血色病/...)                 │     │
│  │  EL4: 诊断特征                                               │     │
│  │  ├── EL4d: 结构化特征 (阈值/条件, 人工审核)                   │     │
│  │  └── EL4a: 鉴别特征 (LLM增强, 定性描述)                      │     │
│  │                                                              │     │
│  │  关系类型 (8种):                                              │     │
│  │  is_a | has_manifestation | has_diagnostic_key                │     │
│  │  differential_from | contradicts | associated_gene            │     │
│  │  guided_by | synonym_of                                       │     │
│  │                                                              │     │
│  │  存储: Neo4j(生产) + Milvus(向量) + JSON Snapshot(版本)       │     │
│  └────────────────────────────────────────────────────────────┘     │
│                          │ Triple Linking                            │
│                          ▼                                         │
│  Layer 1: 患者数据层 (User Data) — 动态 [已有DiagnosticState]        │
│  ┌────────────────────────────────────────────────────────────┐     │
│  │  DiagnosticState: hypotheses + excluded_hypotheses +         │     │
│  │  kg_retrieval_result + patient_data                          │     │
│  └────────────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────────────┘
```

### 3.2 Milvus Collection Schema设计

```python
# Collection: kg_entities
fields = [
    FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
    FieldSchema(name="entity_name", dtype=DataType.VARCHAR, max_length=256),
    FieldSchema(name="entity_type", dtype=DataType.VARCHAR, max_length=64),
    FieldSchema(name="layer", dtype=DataType.VARCHAR, max_length=32),
    FieldSchema(name="description", dtype=DataType.VARCHAR, max_length=2048),
    FieldSchema(name="source_guideline", dtype=DataType.VARCHAR, max_length=256),
    FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=1024),
]
index_params = {
    "metric_type": "COSINE",
    "index_type": "IVF_FLAT",
    "params": {"nlist": 128}
}
```

| 存储内容 | 向量维度 | 嵌入模型 | 用途 | 预估数据量(Wilson病) |
|----------|---------|---------|------|---------------------|
| EL4特征节点嵌入 | 1024-dim | BGE-M3 | 特征节点语义向量 | ~35条 |
| EL3疾病节点嵌入 | 1024-dim | BGE-M3 | 疾病综合描述向量 | ~1条 |
| 指南段落嵌入 | 1024-dim | BGE-M3 | 指南PDF分块段落向量 | ~20条 |

### 3.3 增强级联检索管道设计

```
输入: 患者症状描述 + 异常检验结果 + 分诊提示
    │
    ├── [路径A: 向量语义匹配] (主路径)
    │   症状描述 → BGE-M3嵌入 → Milvus COSINE top_k=20
    │   目标延迟: ~30ms
    │
    └── [路径B: Top-down分诊提示] (可选)
        triage_hint → 映射到EL2亚类 → 缩小EL3候选范围
    │
    ▼
[图扩展] Neo4j 1-hop邻居 → 关系边 + edge_degree排序
    目标延迟: ~50ms
    │
    ▼
[投票排序] 按疾病聚合: score = Σ(match_score × weight)
    weight = 2.0(核心特征) / 1.0(支持特征)
    (当前无IC值，用均匀权重; 后续接入HPO后升级为IC值加权)
    目标延迟: ~35ms
    │
    ▼
[差异KG检索] 查询differential_from边 → 候选疾病间鉴别要点
    目标延迟: ~10ms (预计算)
    │
    ▼
[Token截断+上下文组装] truncate_by_token_size → 构建LLM上下文窗口
    目标延迟: ~10ms
    │
    ▼
输出: KGRetrievalResult
    ├── candidate_diseases: [{name, score, matched_features}]
    ├── diagnostic_differences: [{disease_pair, key_features}]
    ├── relevant_entities: [{name, type, description, source}]
    ├── relevant_relations: [{source, target, type, strength}]
    └── source_citations: [{guideline, section, original_text}]

端到端P95目标: ~135ms
```

### 3.4 三级降级策略

| 降级级别 | 条件 | 可用功能 | 性能影响 |
|----------|------|---------|---------|
| Level 1 | Neo4j+Milvus均可用 | 完整级联检索(向量粗排+图扩展+投票+差异) | 基准 |
| Level 2 | Neo4j不可用，Milvus可用 | Milvus纯向量检索(COSINE top_k)，无图扩展和差异KG | 召回率下降~15% |
| Level 3 | Milvus也不可用 | 原有knowledge_retriever文本检索 | 回退到基线 |

### 3.5 配置层设计

```yaml
# config.yaml 新增配置段
knowledge_graph:
  enabled: false
  engine: "networkx"
  neo4j:
    url: "bolt://localhost:7687"
    username: "neo4j"
    password: "password"
  embedding_model: "BAAI/bge-m3"
  activation:
    similarity_threshold: 0.5
    top_k_diseases: 5
  integration:
    falsification: false
    guideline_verify: false
    info_gap: false
    debate_context: false
```

### 3.6 模块结构与源码映射

```
core/kg/
├── __init__.py
├── kg_schema.py          # 数据类定义
├── kg_builder.py         # 离线构建管道主入口
├── kg_chunker.py         # 医学文本语义分块
│   └── [源] MedGraphRAG agentic_chunker.py → AgenticChunker类
├── kg_extractor.py       # LLM实体/关系提取
│   └── [源] MedGraphRAG nano_graphrag/_op.py → extract_entities()
│   └── [源] MedGraphRAG nano_graphrag/prompt.py → PROMPTS["entity_extraction"]
│   └── [源] MedGraphRAG nano_graphrag/prompt.py → PROMPTS["entiti_continue_extraction"]
│   └── [源] MedGraphRAG nano_graphrag/prompt.py → PROMPTS["entiti_if_loop_extraction"]
├── kg_importer.py        # 四层诊断KG导入器
│   └── [源] MedGraphRAG three_layer_import.py → ThreeLayerImporter类
├── kg_writer.py          # Neo4j节点/关系写入
│   └── [源] MedGraphRAG creat_graph_with_description.py → create_neo4j_nodes_and_relationships()
├── kg_cleaner.py         # 图谱后处理
│   └── [源] MedGraphRAG utils.py → merge_similar_nodes()
│   └── [源] MedGraphRAG cleangraph.py → Neo4jConnection.clean_graph()
├── kg_embedder.py        # BGE-M3嵌入生成 + Milvus索引写入
│   └── [源] MedRAG KG_Retrieve.py → get_symptom_embeddings() (预计算+持久化模式)
│   └── [源] MedGraphRAG nano_graphrag/_storage.py → MilvusLiteStorge (Milvus写入模式)
├── kg_retriever.py       # 增强级联检索管道
│   └── [源] MedGraphRAG nano_graphrag/_op.py → _build_local_query_context()
│   └── [源] MedGraphRAG nano_graphrag/_op.py → _find_most_related_edges_from_entities()
│   └── [源] MedGraphRAG nano_graphrag/_utils.py → truncate_list_by_token_size()
├── kg_classifier.py      # 投票分类
│   └── [源] MedRAG KG_Retrieve.py → find_closest_category()
│   └── [源] MedRAG KG_Retrieve.py → compute_shortest_path_length()
├── kg_differential.py    # 诊断差异KG预计算
│   └── [源] MedRAG main_MedRAG.py → get_additional_info_from_level_2()
├── kg_interface.py       # 统一查询API + 三级降级
│   └── [源] MedGraphRAG retrieve.py → seq_ret() (降级检索模式)
└── kg_validator.py       # 阈值验证+人工审核辅助

core/
├── kg_cache.py           # LLM调用缓存
│   └── [源] MedGraphRAG nano_graphrag/_llm.py → openai_complete_if_cache()
│   └── [源] MedGraphRAG nano_graphrag/_utils.py → compute_args_hash()
└── kg_config.py          # KG系统配置加载
```

---

## 4. 代码级实现细节

### 4.1 LLM Prompt模板

#### 4.1.1 实体/关系提取Prompt（移植自 MedGraphRAG）

**源文件**: `MedGraphRAG/nano_graphrag/prompt.py` → `PROMPTS["entity_extraction"]` (第213-313行)

```python
ENTITY_EXTRACTION_PROMPT = """-Goal-
Given a medical text document about liver disease, identify all medical entities and their relationships.

-Steps-
1. Identify all entities. For each identified entity, extract the following information:
- entity_name: Name of the entity, capitalized
- entity_type: One of the following types: [{entity_types}]
- entity_description: Comprehensive description of the entity's attributes and activities
Format each entity as ("entity"{tuple_delimiter}<entity_name>{tuple_delimiter}<entity_type>{tuple_delimiter}<entity_description>

2. From the entities identified in step 1, identify all pairs of (source_entity, target_entity) that are *clearly related* to each other.
For each pair of related entities, extract the following information:
- source_entity: name of the source entity, as identified in step 1
- target_entity: name of the target entity, as identified in step 1
- relationship_description: explanation as to why you think the source entity and the target entity are related to each other
- relationship_strength: a numeric score indicating strength of the relationship between the source entity and target entity
Format each relationship as ("relationship"{tuple_delimiter}<source_entity>{tuple_delimiter}<target_entity>{tuple_delimiter}<relationship_description>{tuple_delimiter}<relationship_strength>)

3. Return output in Chinese as a single list of all the entities and relationships identified in steps 1 and 2. Use **{record_delimiter}** as the list delimiter.

4. When finished, output {completion_delimiter}

-Real Data-
Entity_types: {entity_types}
Text: {input_text}
Output:"""
```

**适配要点**:
- `entity_types` 替换为肝病领域类型: `LiverDisease, Phenotype, LabTest, Imaging, Treatment, Drug, Biomarker, ClinicalGuideline, Anatomy`
- `tuple_delimiter` = `"<|>"` (沿用MedGraphRAG默认值)
- `record_delimiter` = `"##"` (沿用MedGraphRAG默认值)
- `completion_delimiter` = `"<|COMPLETE|>"` (沿用MedGraphRAG默认值)
- 输出语言改为中文（原文为English，适配中文医学文本）
- 输入截断: `text[:3000]`（参考MedGraphRAG `creat_graph_with_description.py`第69行）

#### 4.1.2 Gleaning继续提取Prompt

**源文件**: `MedGraphRAG/nano_graphrag/prompt.py` → `PROMPTS["entiti_continue_extraction"]` (第334-336行)

```python
GLEANING_CONTINUE_PROMPT = """MANY entities were missed in the last extraction.  Add them below using the same format:
"""
```

#### 4.1.3 Gleaning循环判断Prompt

**源文件**: `MedGraphRAG/nano_graphrag/prompt.py` → `PROMPTS["entiti_if_loop_extraction"]` (第338-340行)

```python
GLEANING_IF_LOOP_PROMPT = """It appears some entities may have still been missed.  Answer YES | NO if there are still entities that need to be added.
"""
```

#### 4.1.4 实体描述摘要Prompt

**源文件**: `MedGraphRAG/nano_graphrag/prompt.py` → `PROMPTS["summarize_entity_descriptions"]` (第317-330行)

```python
ENTITY_SUMMARY_PROMPT = """You are a helpful assistant responsible for generating a comprehensive summary of the data provided below.
Given one or two entities, and a list of descriptions, all related to the same entity or group of entities.
Please concatenate all of these into a single, comprehensive description. Make sure to include information collected from all the descriptions.
If the provided descriptions are contradictory, please resolve the contradictions and provide a single, coherent summary.
Make sure it is written in third person, and include the entity names so we the have full context.

#######
-Data-
Entities: {entity_name}
Description List: {description_list}
#######
Output:
"""
```

### 4.2 响应解析正则与逻辑

#### 4.2.1 实体/关系解析（移植自 MedGraphRAG）

**源文件**: `MedGraphRAG/nano_graphrag/_op.py` → `_handle_single_entity_extraction()` (第81-99行) + `_handle_single_relationship_extraction()` (第102-122行)

```python
import re

TUPLE_DELIMITER = "<|>"
RECORD_DELIMITER = "##"
COMPLETION_DELIMITER = "<|COMPLETE|>"

def parse_extraction_response(response: str) -> dict:
    """解析LLM实体/关系提取响应
    移植自 MedGraphRAG _op.py extract_entities() 第268-296行
    """
    records = split_string_by_multi_markers(
        response,
        [RECORD_DELIMITER, COMPLETION_DELIMITER],
    )

    maybe_nodes = {}
    maybe_edges = {}

    for record in records:
        record_match = re.search(r"\((.*)\)", record)
        if record_match is None:
            continue
        record_content = record_match.group(1)
        record_attributes = split_string_by_multi_markers(
            record_content, [TUPLE_DELIMITER]
        )

        if len(record_attributes) >= 4 and record_attributes[0].strip().strip('"') == "entity":
            entity_name = clean_str(record_attributes[1].upper())
            entity_type = clean_str(record_attributes[2].upper())
            entity_description = clean_str(record_attributes[3])
            if entity_name.strip():
                maybe_nodes[entity_name] = {
                    "entity_name": entity_name,
                    "entity_type": entity_type,
                    "description": entity_description,
                }

        elif len(record_attributes) >= 5 and record_attributes[0].strip().strip('"') == "relationship":
            source = clean_str(record_attributes[1].upper())
            target = clean_str(record_attributes[2].upper())
            description = clean_str(record_attributes[3])
            strength = float(record_attributes[-1]) if is_float_regex(record_attributes[-1]) else 1.0
            if source.strip() and target.strip():
                key = tuple(sorted([source, target]))
                maybe_edges[key] = {
                    "src_id": source,
                    "tgt_id": target,
                    "description": description,
                    "weight": strength,
                }

    return {"entities": maybe_nodes, "relationships": maybe_edges}


def split_string_by_multi_markers(content: str, markers: list[str]) -> list[str]:
    """按多个分隔符分割字符串
    移植自 MedGraphRAG _utils.py 第77-82行
    """
    if not markers:
        return [content]
    results = re.split("|".join(re.escape(marker) for marker in markers), content)
    return [r.strip() for r in results if r.strip()]


def clean_str(input_val) -> str:
    """清理字符串: 去除HTML转义和控制字符
    移植自 MedGraphRAG _utils.py 第94-102行
    """
    import html
    if not isinstance(input_val, str):
        return input_val
    result = html.unescape(input_val.strip())
    return re.sub(r"[\x00-\x1f\x7f-\x9f]", "", result)


def is_float_regex(value: str) -> bool:
    """判断字符串是否为浮点数
    移植自 MedGraphRAG _utils.py 第69-70行
    """
    return bool(re.match(r"^[-+]?[0-9]*\.?[0-9]+$", value))
```

### 4.3 Cypher MERGE语句

#### 4.3.1 实体节点写入（移植自 MedGraphRAG）

**源文件**: `MedGraphRAG/creat_graph_with_description.py` → `create_neo4j_nodes_and_relationships()` 第156-170行

```cypher
-- 实体节点 MERGE 语句 (适配罕见肝病KG Schema)
MERGE (n:`{entity_type}` {id: $id, gid: $gid})
ON CREATE SET
    n.description = $description,
    n.embedding = $embedding,
    n.source = 'nano_graphrag'
ON MATCH SET
    n.description = CASE WHEN n.description IS NULL OR n.description = ''
                         THEN $description
                         ELSE n.description END,
    n.embedding = CASE WHEN n.embedding IS NULL
                       THEN $embedding
                       ELSE n.embedding END
RETURN n
```

**适配改造** — 四层诊断KG节点写入:

```cypher
-- EL1/EL2层级节点
MERGE (n:Entity {id: $id})
ON CREATE SET n.layer = $layer, n.name = $name,
              n.entity_type = $entity_type, n.gid = $gid
RETURN n

-- EL3疾病节点 (含orphacode/omim/gene/inheritance属性)
MERGE (n:Disease {id: $id})
ON CREATE SET n.layer = 'EL3', n.name = $name,
              n.orphacode = $orphacode, n.omim = $omim,
              n.gene = $gene, n.inheritance = $inheritance,
              n.gid = $gid, n.description = $description
ON MATCH SET
    n.description = CASE WHEN n.description IS NULL OR n.description = ''
                         THEN $description ELSE n.description END
RETURN n

-- EL4d结构化特征节点 (含阈值/方向/单位)
MERGE (n:Feature {id: $id})
ON CREATE SET n.layer = 'EL4d', n.name = $name,
              n.field = $field, n.direction = $direction,
              n.threshold = $threshold, n.unit = $unit,
              n.is_core = $is_core, n.gid = $gid,
              n.description = $description
RETURN n

-- EL4a鉴别特征节点
MERGE (n:Feature {id: $id})
ON CREATE SET n.layer = 'EL4a', n.name = $name,
              n.gid = $gid, n.description = $description
RETURN n
```

#### 4.3.2 关系边写入（移植自 MedGraphRAG）

**源文件**: `MedGraphRAG/creat_graph_with_description.py` → `create_neo4j_nodes_and_relationships()` 第204-210行

```cypher
-- 原始关系写入 (MedGraphRAG)
MATCH (a {id: $src, gid: $gid})
MATCH (b {id: $tgt, gid: $gid})
MERGE (a)-[r:`{rel_type}`]->(b)
ON CREATE SET r.description = $description, r.strength = $strength
RETURN r
```

**适配改造** — 8种诊断KG关系:

```cypher
-- is_a 层级关系
MATCH (a:Entity {id: $child_id}), (b:Entity {id: $parent_id})
MERGE (a)-[r:is_a]->(b)
RETURN r

-- has_manifestation 疾病→特征
MATCH (d:Disease {id: $disease_id}), (f:Feature {id: $feature_id})
MERGE (d)-[r:has_manifestation {is_core: $is_core}]->(f)
RETURN r

-- has_diagnostic_key 疾病→核心诊断特征
MATCH (d:Disease {id: $disease_id}), (f:Feature {id: $feature_id})
MERGE (d)-[r:has_diagnostic_key]->(f)
RETURN r

-- differential_from 差异关系 (预计算)
MATCH (d1:Disease {id: $d1_id}), (d2:Disease {id: $d2_id})
MERGE (d1)-[r:differential_from]->(d2)
ON CREATE SET r.key_features = $key_features,
              r.difficulty = $difficulty
RETURN r

-- contradicts 排除关系
MATCH (f:Feature {id: $feature_id}), (d:Disease {id: $disease_id})
MERGE (f)-[r:contradicts {strength: $strength}]->(d)
RETURN r

-- associated_gene 基因关联
MATCH (d:Disease {id: $disease_id}), (g:Gene {id: $gene_id})
MERGE (d)-[r:associated_gene]->(g)
RETURN r

-- guided_by 指南引用
MATCH (d:Disease {id: $disease_id}), (g:ClinicalGuideline {id: $guideline_id})
MERGE (d)-[r:guided_by]->(g)
ON CREATE SET r.section = $section, r.page = $page
RETURN r

-- synonym_of 同义关系
MATCH (a:Entity {id: $id1}), (b:Entity {id: $id2})
MERGE (a)-[r:synonym_of]->(b)
RETURN r
```

#### 4.3.3 批量导入优化（UNWIND）

```cypher
-- 批量节点导入 (参考 MedGraphRAG three_layer_import.py 批量模式)
UNWIND $data AS row
MERGE (n:Entity {id: row.id})
ON CREATE SET n.layer = row.layer, n.name = row.name,
              n.entity_type = row.entity_type,
              n.description = row.description, n.gid = row.gid
RETURN count(*)

-- 批量关系导入
UNWIND $data AS row
MATCH (a:Entity {id: row.source_id})
MATCH (b:Entity {id: row.target_id})
CALL apoc.create.relationship(a, row.relation_type, {
    is_core: row.is_core, score: row.score, strength: row.strength
}, b) YIELD rel
RETURN count(*)
```

#### 4.3.4 跨层REFERENCE链接（移植自 MedGraphRAG）

**源文件**: `MedGraphRAG/utils.py` → `ref_link()` 第206-238行

```cypher
-- 跨层REFERENCE关系 (embedding余弦相似度>0.6)
MATCH (a) WHERE a.gid = $gid1 AND NOT a:Summary
WITH collect(a) AS GraphA
MATCH (b) WHERE b.gid = $gid2 AND NOT b:Summary
WITH GraphA, collect(b) AS GraphB
UNWIND GraphA AS n UNWIND GraphB AS m
WITH n, m, 0.6 AS threshold
WHERE apoc.coll.sort(labels(n)) = apoc.coll.sort(labels(m)) AND n <> m
WITH n, m, threshold,
    gds.similarity.cosine(n.embedding, m.embedding) AS similarity
WHERE similarity > threshold
MERGE (m)-[:REFERENCE]->(n)
RETURN n, m
```

#### 4.3.5 节点合并（移植自 MedGraphRAG）

**源文件**: `MedGraphRAG/utils.py` → `merge_similar_nodes()` 第173-204行

```cypher
-- 相似节点合并 (embedding余弦相似度>0.5)
WITH 0.5 AS threshold
MATCH (n), (m)
WHERE NOT n:Summary AND NOT m:Summary
  AND n.gid = m.gid AND n.gid = $gid AND n<>m
  AND apoc.coll.sort(labels(n)) = apoc.coll.sort(labels(m))
WITH n, m,
    gds.similarity.cosine(n.embedding, m.embedding) AS similarity
WHERE similarity > threshold
WITH head(collect([n,m])) as nodes
CALL apoc.refactor.mergeNodes(nodes, {properties: 'overwrite', mergeRels: true})
YIELD node
RETURN count(*)
```

#### 4.3.6 关系类型推断逻辑（移植自 MedGraphRAG）

**源文件**: `MedGraphRAG/creat_graph_with_description.py` → `create_neo4j_nodes_and_relationships()` 第193-201行

MedGraphRAG原始实现中，LLM提取的关系只有`description`和`strength`，没有显式关系类型。原始代码使用LLM的`description`作为Cypher动态标签。本项目需映射为8种诊断KG关系类型。

```python
RELATION_TYPE_MAP = {
    "is_a": ["属于", "归类", "是一种", "is a", "subtype of", "belongs to"],
    "has_symptom": ["表现为", "症状", "symptom", "presents with", "manifests"],
    "has_diagnostic_key": ["诊断标准", "关键特征", "diagnostic criteria", "key feature"],
    "differential_from": ["鉴别", "区分", "differential", "distinguish", "differentiate"],
    "contradicts": ["排除", "否定", "contradicts", "excludes", "rules out"],
    "associated_gene": ["基因", "突变", "gene", "mutation", "genetic"],
    "guided_by": ["指南", "推荐", "guideline", "recommended", "according to"],
    "synonym_of": ["同义", "又称", "synonym", "also known as", "aka"],
}

def infer_relation_type(description: str, strength: float) -> str:
    """从LLM提取的关系描述推断关系类型
    移植自 MedGraphRAG creat_graph_with_description.py 第193-201行
    原始实现: 直接使用description作为Cypher关系类型标签
    适配改造: 基于关键词匹配映射为8种诊断KG关系类型"""
    desc_lower = description.lower()
    for rel_type, keywords in RELATION_TYPE_MAP.items():
        for kw in keywords:
            if kw in desc_lower:
                return rel_type
    return "related_to"
```

#### 4.3.7 实体去重合并逻辑（移植自 MedGraphRAG）

**源文件**: `MedGraphRAG/nano_graphrag/_op.py` → `_merge_nodes_then_upsert()` 第125-170行 + `_merge_edges_then_upsert()` 第173-218行

核心逻辑: 同名实体合并描述(调用ENTITY_SUMMARY_PROMPT生成合并摘要)→写入图存储; 同对实体关系合并描述+强度取最大值→写入图存储。详见5.2节嵌入预计算持久化中的`_merge_nodes_then_upsert()`和`_merge_edges_then_upsert()`函数。

#### 4.3.8 Summary节点创建（移植自 MedGraphRAG）

**源文件**: `MedGraphRAG/nano_graphrag/_op.py` → `_merge_nodes_then_upsert()` 第148-160行 + `MedGraphRAG/creat_graph_with_description.py` 第175-192行

MedGraphRAG为每个实体创建Summary节点，包含实体的综合描述摘要。本项目需为EL3疾病节点创建Summary节点。

```cypher
-- Summary节点创建
MERGE (s:Summary {id: $summary_id, gid: $gid})
ON CREATE SET s.content = $summary_content, s.embedding = $embedding
RETURN s

-- Summary与实体的关联
MATCH (s:Summary {id: $summary_id}), (e:Entity {entity_name: $entity_name})
WHERE e.gid = $gid
MERGE (s)-[:SUMMARIZES]->(e)
RETURN s, e
```

Summary内容使用`ENTITY_SUMMARY_PROMPT`（见4.1.4节）合并多个描述为一个综合摘要。

### 4.4 Milvus search_params

#### 4.4.1 向量检索参数（移植自 MedGraphRAG）

**源文件**: `MedGraphRAG/nano_graphrag/_storage.py` → `MilvusLiteStorge.query()` 第114-126行

```python
# Milvus COSINE搜索参数 (直接移植 MedGraphRAG)
search_params = {
    "metric_type": "COSINE",
    "params": {"radius": 0.2}  # radius=0.2: 最小相似度阈值
}

# 完整检索调用
results = milvus_client.search(
    collection_name="kg_entities",
    data=[query_embedding],         # BGE-M3 1024-dim 向量
    limit=top_k,                    # 默认 top_k=20
    output_fields=["entity_name", "entity_type", "description", "layer"],
    search_params=search_params,
)

# 结果解析
parsed_results = [
    {
        "entity_name": r["entity"]["entity_name"],
        "entity_type": r["entity"]["entity_type"],
        "description": r["entity"]["description"],
        "layer": r["entity"]["layer"],
        "distance": r["distance"],   # COSINE相似度分数
    }
    for r in results[0]
]
```

**适配改造** — 双路径检索:

```python
# 路径A: 语义模糊匹配 (主路径)
semantic_params = {
    "metric_type": "COSINE",
    "params": {"radius": 0.2, "range_filter": 1.0}  # 0.2 < similarity < 1.0
}

# 路径B: 精确字段匹配 (辅助路径, 不走Milvus, 直接Cypher查询)
# MATCH (f:Feature {field: $field}) WHERE f.direction = $direction ...
```

#### 4.4.2 Milvus Collection创建

**源文件**: `MedGraphRAG/nano_graphrag/_storage.py` → `MilvusLiteStorge.__post_init__()` 第78-89行

```python
# Milvus Collection 创建 (移植 MedGraphRAG 模式)
from pymilvus import MilvusClient, CollectionSchema, FieldSchema, DataType

def create_kg_collection(milvus_client: MilvusClient, collection_name: str, dim: int = 1024):
    if milvus_client.has_collection(collection_name):
        return

    schema = MilvusClient.create_schema(auto_id=True, enable_dynamic_field=False)
    schema.add_field(FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True))
    schema.add_field(FieldSchema(name="entity_name", dtype=DataType.VARCHAR, max_length=256))
    schema.add_field(FieldSchema(name="entity_type", dtype=DataType.VARCHAR, max_length=64))
    schema.add_field(FieldSchema(name="layer", dtype=DataType.VARCHAR, max_length=32))
    schema.add_field(FieldSchema(name="description", dtype=DataType.VARCHAR, max_length=2048))
    schema.add_field(FieldSchema(name="source_guideline", dtype=DataType.VARCHAR, max_length=256))
    schema.add_field(FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dim))

    index_params = milvus_client.prepare_index_params()
    index_params.add_index(
        field_name="embedding",
        index_type="IVF_FLAT",
        metric_type="COSINE",
        params={"nlist": 128}
    )

    milvus_client.create_collection(
        collection_name=collection_name,
        schema=schema,
        index_params=index_params,
    )
```

### 4.5 图扩展Cypher查询

#### 4.5.1 1-hop邻居扩展（移植自 MedGraphRAG）

**源文件**: `MedGraphRAG/nano_graphrag/_op.py` → `_find_most_related_edges_from_entities()` 第562-593行

```cypher
-- 1-hop邻居扩展 + edge_degree排序
MATCH (n)-[r]-(m)
WHERE n.entity_name IN $names
RETURN n.entity_name AS source, type(r) AS rel_type,
       r.description AS desc, r.strength AS strength,
       m.entity_name AS target, m.entity_type AS target_type,
       m.description AS target_desc,
       size(()-[]->(n)) + size(()-[]->(m)) AS degree_sum
ORDER BY degree_sum DESC, r.strength DESC
LIMIT 50
```

#### 4.5.2 最短路径投票（移植自 MedRAG）

**源文件**: `MedRAG/KG_Retrieve.py` → `find_closest_category()` 第150-197行

```python
# NetworkX最短路径投票 (MedRAG原始实现)
def find_closest_category(top_symptoms, categories, top_n):
    category_votes = {category: 0 for category in categories}
    for symptom in top_symptoms:
        if symptom not in G:
            continue
        diagnosis_nodes = get_diagnoses_for_symptom(symptom)
        for diagnosis in diagnosis_nodes:
            min_distance = float('inf')
            closest_category = None
            for category in categories:
                if category not in G:
                    continue
                try:
                    distance = nx.shortest_path_length(G, source=diagnosis, target=category)
                except nx.NetworkXNoPath:
                    distance = float('inf')
                if distance < min_distance:
                    min_distance = distance
                    closest_category = category
            if closest_category:
                category_votes[closest_category] += 1
    sorted_categories = sorted(category_votes.items(), key=lambda x: x[1], reverse=True)
    return [sorted_categories[i][0] for i in range(top_n)]
```

**适配改造** — Neo4j Cypher最短路径:

```cypher
-- Neo4j shortestPath 投票 (适配罕见肝病EL2子类)
MATCH (start {entity_name: $entity})
MATCH (end:Entity {layer: 'EL2', name: $category})
WITH shortestPath((start)-[*]-(end)) AS p
RETURN length(p) AS distance
LIMIT 1
```


#### 4.5.3 子图检索上下文格式（移植自 MedGraphRAG）

**源文件**: `MedGraphRAG/nano_graphrag/_op.py` → `_build_local_query_context()` 第596-687行 + `MedGraphRAG/utils.py` → `ret_context()` 第150-171行

流程: Milvus向量检索→Top-K实体→Neo4j 1-hop扩展→Token截断→格式化输出。输出格式为`-----Entities-----` + `-----Relationships-----` 两段式结构。

#### 4.5.4 LLM相似度降级检索（移植自 MedGraphRAG）

**源文件**: `MedGraphRAG/retrieve.py` → `seq_ret()` 第7-41行

当Neo4j不可用时，使用LLM对实体摘要进行1-10相似度评分，实现降级检索。评分prompt: `Rate the relevance of the following entity to the query on a scale of 1-10.`

### 4.6 源码精确映射表

> **目的**: 开发者打开参考仓库后，可直接定位到具体文件、函数、行号，无需猜测。完整映射表见4.6.1和4.6.2节。

#### 4.6.1 MedGraphRAG 仓库映射

| 目标模块 | 源文件路径 | 函数/类 | 行号范围 | 核心职责 | 关键参数/返回值 |
|---------|-----------|---------|---------|---------|---------------|
| `kg_chunker.py` | `MedGraphRAG/agentic_chunker.py` | `AgenticChunker` | 1-150 | 语义分块 | `chunk()` → `List[Document]`，`threshold=0.5` |
| `kg_extractor.py` | `MedGraphRAG/nano_graphrag/prompt.py` | `PROMPTS["entity_extraction"]` | 213-313 | 实体提取Prompt | 参数: `entity_types`, `tuple_delimiter`, `record_delimiter`, `completion_delimiter`, `input_text` |
| `kg_extractor.py` | `MedGraphRAG/nano_graphrag/prompt.py` | `PROMPTS["entiti_continue_extraction"]` | 334-336 | Gleaning继续Prompt | 固定文本，无参数 |
| `kg_extractor.py` | `MedGraphRAG/nano_graphrag/prompt.py` | `PROMPTS["entiti_if_loop_extraction"]` | 338-340 | Gleaning判断Prompt | 固定文本，返回YES/NO |
| `kg_extractor.py` | `MedGraphRAG/nano_graphrag/prompt.py` | `PROMPTS["summarize_entity_descriptions"]` | 317-330 | 实体描述摘要Prompt | 参数: `entity_name`, `description_list` |
| `kg_extractor.py` | `MedGraphRAG/nano_graphrag/_op.py` | `_process_single_content()` | 244-266 | 单块提取+Gleaning循环 | `max_gleaning`默认1 |
| `kg_extractor.py` | `MedGraphRAG/nano_graphrag/_op.py` | `extract_entities()` | 268-304 | 多块并发提取入口 | `asyncio.gather`并发 |
| `kg_extractor.py` | `MedGraphRAG/nano_graphrag/_op.py` | `_handle_single_entity_extraction()` | 81-99 | 解析单条实体记录 | 输入: `record_attributes`，输出: `dict` |
| `kg_extractor.py` | `MedGraphRAG/nano_graphrag/_op.py` | `_handle_single_relationship_extraction()` | 102-122 | 解析单条关系记录 | 输入: `record_attributes`，输出: `dict` |
| `kg_extractor.py` | `MedGraphRAG/nano_graphrag/_op.py` | `_merge_nodes_then_upsert()` | 125-170 | 实体去重合并+写入 | 参数: `maybe_nodes`, `knowledge_graph_inst` |
| `kg_extractor.py` | `MedGraphRAG/nano_graphrag/_op.py` | `_merge_edges_then_upsert()` | 173-218 | 关系去重合并+写入 | 参数: `maybe_edges`, `knowledge_graph_inst` |
| `kg_writer.py` | `MedGraphRAG/creat_graph_with_description.py` | `create_neo4j_nodes_and_relationships()` | 156-210 | Neo4j节点+关系写入 | MERGE ON CREATE/ON MATCH |
| `kg_writer.py` | `MedGraphRAG/creat_graph_with_description.py` | `extract_entities_with_description()` | 30-100 | 带描述的实体提取 | `entity_types`列表，`text[:3000]`截断 |
| `kg_importer.py` | `MedGraphRAG/three_layer_import.py` | `ThreeLayerImporter` | 17-263 | 三层图导入器 | `import_layer()`方法，逐文件调用 |
| `kg_importer.py` | `MedGraphRAG/three_layer_import.py` | `creat_metagraph_with_description()` | 90-180 | 单层元图构建 | 参数: `file_path`, `layer_name` |
| `kg_cleaner.py` | `MedGraphRAG/utils.py` | `merge_similar_nodes()` | 173-204 | 相似节点合并 | `threshold=0.5`(余弦相似度) |
| `kg_cleaner.py` | `MedGraphRAG/utils.py` | `ref_link()` | 206-238 | 跨层REFERENCE链接 | `threshold=0.6`(余弦相似度) |
| `kg_cleaner.py` | `MedGraphRAG/cleangraph.py` | `Neo4jConnection.clean_graph()` | 50-120 | 图谱清洗 | 去除孤立节点、合并重复 |
| `kg_embedder.py` | `MedGraphRAG/nano_graphrag/_storage.py` | `MilvusLiteStorge` | 65-126 | Milvus向量存储 | `__post_init__`创建Collection，`query()`检索 |
| `kg_retriever.py` | `MedGraphRAG/nano_graphrag/_op.py` | `_build_local_query_context()` | 596-687 | 本地查询上下文构建 | 参数: `query`, `knowledge_graph_inst`, `entities_vdb` |
| `kg_retriever.py` | `MedGraphRAG/nano_graphrag/_op.py` | `_find_most_related_edges_from_entities()` | 562-593 | 1-hop邻居扩展 | Cypher `degree_sum`排序 |
| `kg_interface.py` | `MedGraphRAG/retrieve.py` | `seq_ret()` | 7-41 | LLM相似度降级检索 | LLM评分1-10 |
| `kg_interface.py` | `MedGraphRAG/utils.py` | `ret_context()` | 150-171 | 子图检索上下文 | NetworkX子图遍历 |
| `kg_interface.py` | `MedGraphRAG/utils.py` | `link_context()` | 121-148 | 跨层链接上下文 | REFERENCE关系遍历 |
| `kg_cache.py` | `MedGraphRAG/nano_graphrag/_llm.py` | `openai_complete_if_cache()` | 9-36 | LLM调用缓存 | `hashing_kv`参数，MD5缓存键 |
| `kg_cache.py` | `MedGraphRAG/nano_graphrag/_utils.py` | `compute_args_hash()` | 73-74 | 参数哈希计算 | `hashlib.md5(str((model, messages)))` |
| `kg_cache.py` | `MedGraphRAG/nano_graphrag/_storage.py` | `JsonKVStorage` | 23-62 | JSON文件缓存后端 | `get_by_id()`, `upsert()` |
| 通用工具 | `MedGraphRAG/nano_graphrag/_utils.py` | `pack_user_ass_to_openai_messages()` | 62-66 | 消息对打包 | 交替user/assistant角色 |
| 通用工具 | `MedGraphRAG/nano_graphrag/_utils.py` | `split_string_by_multi_markers()` | 77-82 | 多分隔符分割 | `re.split("\|".join(...))` |
| 通用工具 | `MedGraphRAG/nano_graphrag/_utils.py` | `clean_str()` | 94-102 | 字符串清理 | `html.unescape` + 控制字符去除 |
| 通用工具 | `MedGraphRAG/nano_graphrag/_utils.py` | `is_float_regex()` | 69-70 | 浮点数判断 | 正则`^[-+]?[0-9]*\.?[0-9]+$` |
| 通用工具 | `MedGraphRAG/nano_graphrag/_utils.py` | `truncate_list_by_token_size()` | 35-42 | Token预算截断 | 逐项累加token数 |
| 通用工具 | `MedGraphRAG/nano_graphrag/_utils.py` | `limit_async_func_call()` | 117-136 | 并发信号量 | `asyncio.Semaphore(max_size)` |
| 通用工具 | `MedGraphRAG/nano_graphrag/_op.py` | `chunking_by_token_size()` | 33-51 | 按Token分块 | `max_token_size=1200` |

#### 4.6.2 MedRAG 仓库映射

| 目标模块 | 源文件路径 | 函数/类 | 行号范围 | 核心职责 | 关键参数/返回值 |
|---------|-----------|---------|---------|---------|---------------|
| `kg_classifier.py` | `MedRAG/KG_Retrieve.py` | `find_closest_category()` | 150-197 | 最短路径投票分类 | `top_symptoms`, `categories`, `top_n` |
| `kg_classifier.py` | `MedRAG/KG_Retrieve.py` | `compute_shortest_path_length()` | 116-120 | 最短路径长度计算 | `nx.shortest_path_length` |
| `kg_classifier.py` | `MedRAG/KG_Retrieve.py` | `get_diagnoses_for_symptom()` | 122-148 | 症状→诊断映射 | NetworkX邻居遍历 |
| `kg_classifier.py` | `MedRAG/KG_Retrieve.py` | `get_keyinfo_for_category()` | 200-209 | 类别关键诊断信息 | 提取EL2类别下关键特征 |
| `kg_embedder.py` | `MedRAG/KG_Retrieve.py` | `get_symptom_embeddings()` | 63-79 | 嵌入预计算+持久化 | `.npy`文件缓存，`np.save`/`np.load` |
| `kg_differential.py` | `MedRAG/main_MedRAG.py` | `get_additional_info_from_level_2()` | 92-140 | EL2类别内差异信息 | 合并同类别疾病信息 |
| `kg_differential.py` | `MedRAG/main_MedRAG.py` | `level_3_to_level_2` | 79-89 | 疾病→类别映射字典 | EL3→EL2层级映射 |
| `kg_differential.py` | `MedRAG/main_MedRAG.py` | `get_diagnoses_for_symptom()` | 142-160 | 症状→诊断推理 | NetworkX图遍历 |
| `kg_retriever.py` | `MedRAG/KG_Retrieve.py` | `KG_Retrieve` | 1-210 | KG检索主类 | `__init__`加载NetworkX图+嵌入 |

### 4.7 移植操作指南

> **目的**: 开发者按步骤操作，将参考仓库代码移植到本项目中。

#### 4.7.1 环境准备

```bash
git clone https://github.com/ImprintLab/Medical-Graph-RAG.git /tmp/kg_ref_repos/medgraphrag
git clone https://github.com/SNOWTEAM2023/MedRAG.git /tmp/kg_ref_repos/medrag
mkdir -p core/kg
pip install neo4j pymilvus openai networkx FlagEmbedding
```

#### 4.7.2 逐模块移植步骤

**Step 1: kg_cache.py（LLM调用缓存）— 优先级最高**

```
源文件: MedGraphRAG/nano_graphrag/_llm.py 第9-36行 + _utils.py 第73-74行 + _storage.py 第23-62行
操作: 复制openai_complete_if_cache()+compute_args_hash()+JsonKVStorage
适配: AsyncOpenAI→项目LLM客户端; JsonKVStorage路径→项目配置目录; 增加TTL过期检查
验证: 同一prompt调用两次，第二次命中缓存
```

**Step 2: kg_chunker.py（医学文本语义分块）**

```
源文件: MedGraphRAG/agentic_chunker.py 第1-150行
操作: 复制AgenticChunker类
适配: OpenAI embedding→BGE-M3; threshold=0.5→中文医学文本适配; Document→项目数据结构
验证: 指南PDF文本→语义分块结果
```

**Step 3: kg_extractor.py（LLM实体/关系提取）— 核心模块**

```
源文件: prompt.py 第213-313行 + _op.py 第81-304行 + _utils.py 第62-102行
操作: 复制PROMPTS+解析函数+去重合并+提取主流程+工具函数
适配: entity_types→肝病领域; 输出语言→中文; LLM调用→kg_cache.py; 图存储→kg_writer.py; 向量存储→kg_embedder.py
验证: 指南PDF文本→实体和关系列表
```

**Step 4: kg_writer.py（Neo4j节点/关系写入）**

```
源文件: MedGraphRAG/creat_graph_with_description.py 第156-210行
操作: 复制create_neo4j_nodes_and_relationships()+MERGE Cypher语句
适配: 通用entity_type→罕见肝病KG Schema; 通用关系→8种诊断KG关系; 增加UNWIND批量导入
验证: 测试实体和关系写入Neo4j，验证MERGE幂等性
```

**Step 5-11**: kg_importer.py、kg_cleaner.py、kg_embedder.py、kg_retriever.py、kg_classifier.py、kg_differential.py、kg_interface.py（详见4.7.2节映射表中的源文件路径和行号范围）

#### 4.7.3 移植注意事项

1. **不要直接import参考仓库**: 所有移植代码应复制到项目 `core/kg/` 目录
2. **LLM客户端统一**: 所有LLM调用必须通过 `kg_cache.py` 的缓存函数
3. **图存储统一**: 所有Neo4j操作必须通过 `kg_writer.py`
4. **向量存储统一**: 所有Milvus操作必须通过 `kg_embedder.py`
5. **配置外部化**: 所有阈值参数应从 `kg_config.py` 读取
6. **中文适配**: Prompt输出语言改为中文，Token估算使用中文系数（0.75字/token）

---

## 5. 工程优化方案

### 5.1 LLM调用缓存（移植自 MedGraphRAG）

**源文件**: `MedGraphRAG/nano_graphrag/_llm.py` → `openai_complete_if_cache()` 第9-36行

**核心机制**: 基于 `(model, messages)` 的MD5哈希生成缓存键，命中时直接返回缓存结果，未命中时调用LLM并写入缓存。

```python
import hashlib
import json
import os
import time
from typing import Optional

class LLMCache:
    """
    LLM调用缓存
    移植自 MedGraphRAG nano_graphrag/_llm.py → openai_complete_if_cache()
    + nano_graphrag/_utils.py → compute_args_hash()

    缓存策略:
    - 缓存键: MD5(model + messages_json) → 参考compute_args_hash()
    - 存储: JSON文件持久化 (参考MedGraphRAG JsonKVStorage)
    - TTL: 7天 (医学知识短期不变)
    """

    def __init__(self, cache_dir: str = ".kg_cache", ttl_days: int = 7):
        self.cache_dir = cache_dir
        self.ttl_seconds = ttl_days * 86400
        os.makedirs(cache_dir, exist_ok=True)

    @staticmethod
    def compute_args_hash(model: str, messages: list) -> str:
        """计算参数哈希
        移植自 MedGraphRAG _utils.py compute_args_hash() 第73-74行
        """
        return hashlib.md5(str((model, messages)).encode()).hexdigest()

    async def get_or_call(
        self,
        model: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        history_messages: Optional[list] = None,
        llm_func: callable = None,
        **kwargs,
    ) -> str:
        """缓存优先的LLM调用
        移植自 MedGraphRAG _llm.py openai_complete_if_cache() 第9-36行
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history_messages:
            messages.extend(history_messages)
        messages.append({"role": "user", "content": prompt})

        args_hash = self.compute_args_hash(model, messages)
        cache_file = os.path.join(self.cache_dir, f"{args_hash}.json")

        # 缓存命中检查
        if os.path.exists(cache_file):
            data = json.load(open(cache_file))
            if time.time() - data["timestamp"] < self.ttl_seconds:
                return data["return"]

        # 缓存未命中，调用LLM
        if llm_func is None:
            raise ValueError("llm_func is required when cache misses")

        response = await llm_func(model=model, messages=messages, **kwargs)
        response_text = response.choices[0].message.content

        # 写入缓存
        json.dump(
            {"return": response_text, "model": model, "timestamp": time.time()},
            open(cache_file, "w"),
        )
        return response_text
```

**预期效果**: 重复文本零LLM调用；构建时间减少40-60%；LLM API成本降低50%+

### 5.2 嵌入预计算持久化（移植自 MedRAG）

**源文件**: `MedRAG/KG_Retrieve.py` → `get_symptom_embeddings()` 第63-79行

**核心机制**: 首次生成嵌入后保存为`.npy`文件，后续加载直接读取，避免重复调用嵌入API。

```python
import numpy as np
import os
from tqdm import tqdm
from sentence_transformers import SentenceTransformer

class KGEmbedder:
    """
    KG嵌入生成器
    移植自 MedRAG KG_Retrieve.py → get_symptom_embeddings() 第63-79行

    预计算+持久化策略:
    - 首次: 批量生成嵌入 → 保存为 .npy 文件
    - 后续: 直接加载 .npy 文件，零嵌入开销
    - 使用 BGE-M3 替代 text-embedding-3-large (对中文医学文本更优)
    """

    def __init__(self, model_name: str = "BAAI/bge-m3", cache_dir: str = ".kg_embeddings"):
        self.model = SentenceTransformer(model_name)
        self.cache_dir = cache_dir
        self.dim = 1024
        os.makedirs(cache_dir, exist_ok=True)

    def generate_embeddings(self, texts: list[str], namespace: str) -> np.ndarray:
        """生成嵌入向量并持久化
        移植自 MedRAG KG_Retrieve.py get_symptom_embeddings() 第63-79行

        Args:
            texts: 待嵌入文本列表
            namespace: 命名空间 (如 'el4_features', 'el3_diseases', 'guideline_chunks')
        """
        cache_path = os.path.join(self.cache_dir, f"{namespace}_embeddings.npy")

        # 检查缓存 (参考 MedRAG load_embeddings)
        if os.path.exists(cache_path):
            print(f"load existing embeddings from {cache_path}...")
            return np.load(cache_path)

        # 批量生成
        print(f"generate new embeddings for {len(texts)} texts...")
        embeddings = self.model.encode(
            texts,
            batch_size=32,
            show_progress_bar=True,
            normalize_embeddings=True,  # 归一化 → COSINE = Inner Product
        )

        # 持久化 (参考 MedRAG np.save)
        np.save(cache_path, embeddings)
        return embeddings

    async def embed(self, text: str) -> list[float]:
        """单文本嵌入 (在线查询时使用)"""
        embedding = self.model.encode([text], normalize_embeddings=True)
        return embedding[0].tolist()
```

**预期效果**: 查询时零嵌入生成开销；构建阶段嵌入吞吐~200 text/s；重复构建零API调用

### 5.3 Gleaning补全循环（移植自 MedGraphRAG）

**源文件**: `MedGraphRAG/nano_graphrag/_op.py` → `extract_entities()` 第244-266行

**核心机制**: 首次提取后，通过多轮对话让LLM补充遗漏的实体/关系，每轮结束后询问是否还需要继续。

```python
async def extract_with_gleaning(
    text: str,
    llm_func: callable,
    entity_extract_prompt: str,
    max_gleaning: int = 1,
) -> str:
    """
    带Gleaning补全的实体/关系提取
    移植自 MedGraphRAG _op.py extract_entities() 第244-266行

    Gleaning循环流程:
    1. 首次提取: entity_extract_prompt → LLM → final_result
    2. 构建 history (user+assistant消息对)
    3. Gleaning循环 (max_gleaning轮):
       a. continue_prompt → LLM → glean_result
       b. final_result += glean_result
       c. if_loop_prompt → LLM → YES/NO
       d. 如果NO或最后一轮，退出循环
    4. 返回合并后的 final_result

    Args:
        text: 输入文本
        llm_func: LLM调用函数 (带缓存)
        entity_extract_prompt: 实体提取prompt模板
        max_gleaning: 最大Gleaning轮数 (默认1轮，控制成本)
    """
    # 第1次提取
    from MedGraphRAG.nano_graphrag._utils import pack_user_ass_to_openai_messages

    context_base = dict(
        tuple_delimiter="<|>",
        record_delimiter="##",
        completion_delimiter="<|COMPLETE|>",
        entity_types=",".join(LIVER_ENTITY_TYPES),
    )

    hint_prompt = entity_extract_prompt.format(**context_base, input_text=text)
    final_result = await llm_func(hint_prompt)

    # 构建 history 用于多轮对话
    history = pack_user_ass_to_openai_messages(hint_prompt, final_result)

    # Gleaning 循环
    continue_prompt = "MANY entities were missed in the last extraction. Add them below using the same format:\n"
    if_loop_prompt = "It appears some entities may have still been missed. Answer YES | NO if there are still entities that need to be added.\n"

    for now_glean_index in range(max_gleaning):
        # 继续提取
        glean_result = await llm_func(continue_prompt, history_messages=history)
        history += pack_user_ass_to_openai_messages(continue_prompt, glean_result)
        final_result += glean_result

        # 如果是最后一次迭代，直接退出
        if now_glean_index == max_gleaning - 1:
            break

        # 询问是否还需要继续
        if_loop_result = await llm_func(if_loop_prompt, history_messages=history)
        if_loop_result = if_loop_result.strip().strip('"').strip("'").lower()
        if if_loop_result != "yes":
            break

    return final_result


def pack_user_ass_to_openai_messages(*args: str) -> list[dict]:
    """将交替的user/assistant消息打包为OpenAI格式
    移植自 MedGraphRAG _utils.py pack_user_ass_to_openai_messages() 第62-66行
    """
    roles = ["user", "assistant"]
    return [
        {"role": roles[i % 2], "content": content}
        for i, content in enumerate(args)
    ]
```

**参数控制**:
- `max_gleaning = 1`: 默认1轮Gleaning（控制LLM调用成本）
- 每轮Gleaning增加2次LLM调用（continue + if_loop）
- 预期增量: Gleaning补充>5%实体/关系

### 5.4 Token预算截断（移植自 MedGraphRAG）

**源文件**: `MedGraphRAG/nano_graphrag/_utils.py` → `truncate_list_by_token_size()` 第35-42行

```python
def truncate_list_by_token_size(
    items: list[dict],
    key: callable,
    max_token_size: int,
) -> list[dict]:
    """按Token预算截断结果列表
    移植自 MedGraphRAG _utils.py truncate_list_by_token_size() 第35-42行

    确保检索结果的总token数不超过LLM上下文窗口限制
    适配: 中文token估算 ≈ 0.75字/token
    """
    result = []
    current_tokens = 0

    def estimate_tokens(text: str) -> int:
        if not text:
            return 0
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        others = len(text) - chinese_chars
        return int(chinese_chars / 0.75 + others / 2.5)

    for item in items:
        item_tokens = estimate_tokens(key(item))
        if current_tokens + item_tokens > max_token_size:
            break
        result.append(item)
        current_tokens += item_tokens

    return result
```

### 5.5 并发提取优化（移植自 MedGraphRAG）

**源文件**: `MedGraphRAG/nano_graphrag/_op.py` → `extract_entities()` 第302-304行 + `MedGraphRAG/nano_graphrag/_utils.py` → `limit_async_func_call()` 第117-136行

```python
def limit_async_func_call(max_size: int):
    """限制最大并发协程数 - 移植自 MedGraphRAG _utils.py limit_async_func_call() 第117-136行
    用法: limited_llm = limit_async_func_call(16)(llm_func)"""
    import asyncio
    semaphore = asyncio.Semaphore(max_size)
    async def wrapper(*args, **kwargs):
        async with semaphore:
            return await kwargs.get("_func", args[0])(*args[1:], **{k: v for k, v in kwargs.items() if k != "_func"})
    return wrapper

# 并发处理多个文本块 (移植 MedGraphRAG _op.py extract_entities() 第302-304行)
limited_llm = limit_async_func_call(16)(llm_func)
results = await asyncio.gather(*[_process_single_content(chunk) for chunk in chunks])
```

### 5.6 优化效果汇总

| 优化项 | 技术方案 | 源仓库/文件/函数 | 预期效果 |
|--------|---------|----------------|---------|
| **LLM调用缓存** | MD5(model+messages)→JSON文件 | MedGraphRAG `_llm.py`→`openai_complete_if_cache()` | 重复文本零LLM调用；成本降低50%+ |
| **嵌入预计算持久化** | .npy文件缓存 | MedRAG `KG_Retrieve.py`→`get_symptom_embeddings()` | 查询零嵌入开销；重复构建零API调用 |
| **Gleaning补全** | 多轮对话+if_loop判断 | MedGraphRAG `_op.py`→`extract_entities()` L244-266 | 实体/关系增量>5% |
| **Token预算截断** | 逐项累加token→截断 | MedGraphRAG `_utils.py`→`truncate_list_by_token_size()` | 避免超出LLM上下文限制 |
| **并发提取** | asyncio.gather+信号量 | MedGraphRAG `_op.py`→`extract_entities()` L302-304 + `_utils.py`→`limit_async_func_call()` L117-136 | 多块并行处理，避免API限流 |
| **输入截断** | text[:3000] | MedGraphRAG `creat_graph_with_description.py` L69 | 单次LLM调用<3秒 |
| **批量Neo4j写入** | UNWIND批量Cypher | MedGraphRAG `three_layer_import.py` | 10x写入速度 |
| **幂等写入** | MERGE ON CREATE/ON MATCH | MedGraphRAG `creat_graph_with_description.py` L156-170 | 支持增量更新 |
| **实体去重合并** | 同名实体描述合并+LLM摘要 | MedGraphRAG `_op.py`→`_merge_nodes_then_upsert()` L125-170 | 消除重复实体，合并描述 |
| **关系去重合并** | 同对实体关系合并+强度取最大 | MedGraphRAG `_op.py`→`_merge_edges_then_upsert()` L173-218 | 消除重复关系，保留最强关联 |
| **关系类型推断** | 关键词匹配→8种诊断KG关系 | MedGraphRAG `creat_graph_with_description.py` L193-201 | LLM描述→结构化关系类型 |
| **LLM降级检索** | LLM相似度评分1-10 | MedGraphRAG `retrieve.py`→`seq_ret()` L7-41 | Neo4j不可用时仍可检索 |

---

## 6. 实施阶段划分与任务分解

### 6.1 总体路线图

```
Phase 0 (1周): 架构清理
    │
    ▼
Phase 1 (2周): 指南PDF数据提取
    │
    ▼
Phase 2 (2周): 图谱构建
    │
    ▼
Phase 3 (2周): 检索引擎
    │
    ▼
Phase 4 (2周): 系统集成
    │
    ▼
总计: 9周
```

### 6.2 阶段依赖关系

```
Phase 0 ──────→ Phase 1a ──────→ Phase 1b
(架构清理)       (基础设施+工具)    (PDF知识抽取+人工审核)
                                       │
                                       ▼
                                Phase 2a ──────→ Phase 2b ──────→ Phase 2c
                                (四层KG构建)     (向量索引+嵌入)   (差异KG+构建入口)
                                       │
                                       ▼
                                Phase 3a ──────→ Phase 3b
                                (级联检索管道)   (投票分类+统一API+降级)
                                       │
                                       ▼
                                Phase 4a ──────→ Phase 4b
                                (工作流集成)     (端到端测试+验收)
```

---

## 7. 各阶段详细任务与时间节点

### Phase 0: 架构清理（Week 1）

**目标**: 移除现有EWAS伪实现，为KG系统腾出架构空间

| # | 任务 | 具体工作 | 产出物 | 验收标准 |
|---|------|---------|--------|---------|
| 0.1 | 移除GraphUpdater | 删除`core/medical_middleware/graph_updater.py`；移除`__init__.py`中的导出 | 代码删除 | 全代码库无GraphUpdater引用 |
| 0.2 | 移除graph_update节点 | 从`graph_orchestrator.py`删除`_node_graph_update`节点(第548-565行)和相关边 | 代码修改 | 工作流中无graph_update节点 |
| 0.3 | 迁移kg_weights字段 | 将`knowledge_graph_weights`(state_definition.py第254行)功能归入`hypotheses.confidence`；删除State中的`knowledge_graph_weights`字段 | state_definition.py修改 | 旧字段无引用，MDTFinalReport同步更新 |
| 0.4 | 清理API依赖 | 移除`api/dependencies.py`中的`GraphUpdater()`实例化 | 代码修改 | API启动无报错 |
| 0.5 | 清理falsification引用 | 移除`falsification.py`中对`graph_updater.suppress_disease()`的调用 | 代码修改 | 证伪流程正常工作 |
| 0.6 | 回归测试 | 运行现有测试套件，确保移除后系统功能正常 | 测试报告 | 所有现有测试通过 |
| 0.7 | 新增KG配置段 | 在`config.yaml`中新增`knowledge_graph`配置段(enabled=false, engine=networkx) | 配置文件 | 配置加载正常，enabled=false时系统行为不变 |

**里程碑M0**: GraphUpdater移除完成，现有测试全部通过，KG配置段就绪

---

### Phase 1: 指南PDF数据提取（Week 2-3）

#### Phase 1a: 基础设施搭建与工具实现（Week 2前半）

| # | 任务 | 具体工作 | 产出物 | 验收标准 |
|---|------|---------|--------|---------|
| 1a.1 | 安装KG依赖 | 取消注释`pymilvus`(requirements.txt第48行)；新增`neo4j`, `sentence-transformers`, `PyMuPDF`, `obonet`, `rapidfuzz`到requirements.txt | requirements.txt | pip install成功 |
| 1a.2 | 实现kg_schema.py | 定义`KGEntity`(name/type/layer/description/source/properties), `KGRelation`(source/target/type/strength/properties), `EntityType`(EL3/EL4d/EL4a/Guideline/Gene), `KGRetrievalResult`(candidate_diseases/diagnostic_differences/relevant_entities/relevant_relations/source_citations)等数据类 | core/kg/kg_schema.py | 数据类可实例化，类型检查通过 |
| 1a.3 | 实现kg_config.py | KG系统配置加载，从config.yaml读取knowledge_graph段，提供Neo4j/Milvus/嵌入模型/激活参数等配置项 | core/kg_config.py | 配置正确加载，默认值合理 |
| 1a.4 | 实现kg_cache.py | **移植MedGraphRAG `nano_graphrag/_llm.py`→`openai_complete_if_cache()`(第9-36行)** + **`_utils.py`→`compute_args_hash()`(第73-74行)**: MD5(model+messages)哈希→JSON文件缓存+7天TTL | core/kg_cache.py | 缓存命中/未命中逻辑正确 |
| 1a.5 | 部署Neo4j | Docker部署Neo4j Community 5.x，配置4GB内存，设置密码 | Neo4j实例 | bolt://localhost:7687可连接 |
| 1a.6 | 启动Milvus | Docker启动Milvus Standalone，创建`kg_entities` Collection(按3.2节Schema+4.4.2节创建代码) | Milvus实例 | localhost:19530可连接，Collection已创建 |
| 1a.7 | 验证BGE-M3 | 下载BGE-M3模型(BAAI/bge-m3)，验证1024-dim嵌入生成 | 模型文件 | 1024-dim向量生成正常，中文医学文本嵌入质量验证 |

#### Phase 1b: 指南PDF知识抽取与人工审核（Week 2后半-Week 3）

| # | 任务 | 具体工作 | 产出物 | 验收标准 |
|---|------|---------|--------|---------|
| 1b.1 | 实现kg_chunker.py | **移植MedGraphRAG `agentic_chunker.py`→`AgenticChunker`类(第12-335行)**: 适配中文医学文本→章节标题识别+段落语义分块+表格结构保留。核心改造: LLM改为通义千问API，分块prompt中文化 | core/kg/kg_chunker.py | Wilson指南PDF正确分块，章节边界准确 |
| 1b.2 | 实现kg_extractor.py | **移植MedGraphRAG `nano_graphrag/_op.py`→`extract_entities()`(第221-334行)** + **`nano_graphrag/prompt.py`→`PROMPTS["entity_extraction"]`(第213-313行)**: LLM实体/关系提取管道。核心改造: entity_types替换为肝病领域9种类型(见4.1.1节)，输出语言改为中文，集成kg_cache缓存 | core/kg/kg_extractor.py | 提取实体+关系列表，Gleaning>5%增量 |
| 1b.3 | 实现kg_validator.py | 阈值验证+人工审核辅助：数值型阈值自动标记confidence(high/medium/low)，生成审核清单 | core/kg/kg_validator.py | 审核清单可导出，confidence自动标记 |
| 1b.4 | 解析Wilson中文指南 | PyMuPDF解析→章节分割→LLM提取(使用4.1.1节prompt模板)→Gleaning补充(使用5.3节循环逻辑) | 提取结果JSON | 实体数>25，关系数>30 |
| 1b.5 | 解析Wilson英文指南 | 同上流程，补充EASL-ERN 2025新增内容(游离铜>20μg/dL、曲恩汀一线等) | 提取结果JSON | 新增实体>10 |
| 1b.6 | 提取结果合并去重 | 合并中英文提取结果，消除重复实体(如"铜蓝蛋白降低"/"ceruloplasmin decreased"归一化) | 合并后JSON | 去重后实体数>35 |
| 1b.7 | 数值型阈值审核 | 肝病专家逐条审核所有数值型阈值(铜蓝蛋白<0.20g/L、24h尿铜>100μg等)，与指南原文比对 | 审核报告 | 阈值0冲突 |
| 1b.8 | 关系正确性审核 | 审核实体间关系的正确性和完整性 | 审核报告 | 关系准确率>95% |
| 1b.9 | confidence标记 | 标记每条知识的confidence: high(与指南原文完全一致)/medium(LLM推断需确认)/low(模糊描述) | 标记结果 | 仅confidence=high的阈值入图 |
| 1b.10 | YAML交叉参考 | LLM提取结果与YAML规则比对，记录差异(以指南PDF为准) | 差异报告 | 差异项已记录(铜蓝蛋白阈值、EASL版本、曲恩汀地位) |
| 1b.11 | EL1/EL2层级划分 | 参考罕见肝病目录，确定疾病大类(≥4类)和亚类(≥6亚类) | 层级定义 | EL1≥4类，EL2≥6亚类 |
| 1b.12 | 产出审核后JSON | 最终审核后的Wilson病实体/关系JSON | data/kg/wilson_verified.json | JSON格式校验通过，阈值0冲突 |

**里程碑M1**: Wilson病KG数据提取完成，审核后JSON阈值0冲突，confidence=high占比>90%

---

### Phase 2: 图谱构建（Week 4-5）

#### Phase 2a: 四层KG构建（Week 4前半）

| # | 任务 | 具体工作 | 产出物 | 验收标准 |
|---|------|---------|--------|---------|
| 2a.1 | 实现kg_importer.py | **移植MedGraphRAG `three_layer_import.py`→`ThreeLayerImporter`类(第17-263行)**: 四层诊断KG导入器。核心改造: 三层语义重定义(EL1/EL2/EL3/EL4)，支持8种关系类型 | core/kg/kg_importer.py | 四层节点正确创建，8种关系类型支持 |
| 2a.2 | 实现kg_writer.py | **移植MedGraphRAG `creat_graph_with_description.py`→`create_neo4j_nodes_and_relationships()`(第133-223行)**: Neo4j节点/关系写入。核心改造: Cypher语句适配罕见肝病KG Schema(见4.3.1-4.3.3节)，UNWIND批量导入优化 | core/kg/kg_writer.py | Neo4j写入成功，支持幂等重入 |
| 2a.3 | 导入Wilson病KG | 将审核后JSON导入Neo4j，创建EL1-EL4节点+8种关系 | Neo4j图数据 | 节点>30，关系>50，属性完整 |
| 2a.4 | 实现kg_cleaner.py | **移植MedGraphRAG `utils.py`→`merge_similar_nodes()`(第173-204行)** + **`cleangraph.py`→`Neo4jConnection.clean_graph()`**: 图谱后处理。核心改造: 节点相似度阈值调优(0.5→0.85)，LLM辅助合并判断 | core/kg/kg_cleaner.py | 无孤立节点，无重复实体 |

#### Phase 2b: 向量索引构建（Week 4后半）

| # | 任务 | 具体工作 | 产出物 | 验收标准 |
|---|------|---------|--------|---------|
| 2b.1 | 实现kg_embedder.py | **移植MedRAG `KG_Retrieve.py`→`get_symptom_embeddings()`(第63-79行)**: 嵌入预计算+持久化。**移植MedGraphRAG `nano_graphrag/_storage.py`→`MilvusLiteStorge.upsert()`(第91-112行)**: Milvus写入模式。核心改造: BGE-M3替代text-embedding-3-large，1024-dim，COSINE度量 | core/kg/kg_embedder.py | Milvus索引创建成功，COSINE度量 |
| 2b.2 | 生成EL4特征嵌入 | 对所有EL4d/EL4a节点生成1024-dim向量，包含entity_name+description | Milvus数据 | Wilson病特征嵌入>35条 |
| 2b.3 | 生成EL3疾病嵌入 | 对Wilson病节点生成综合描述向量(疾病名+核心特征摘要) | Milvus数据 | 疾病嵌入>1条 |
| 2b.4 | 生成指南段落嵌入 | 对指南PDF分块段落生成向量，包含source_guideline字段 | Milvus数据 | 段落嵌入>20条 |
| 2b.5 | 嵌入质量验证 | 验证同义实体相似度>0.8(如"铜蓝蛋白降低"≈"ceruloplasmin decreased")，异义实体相似度<0.5 | 验证报告 | 同义>0.8，异义<0.5 |

#### Phase 2c: 差异KG预计算与构建入口（Week 5）

| # | 任务 | 具体工作 | 产出物 | 验收标准 |
|---|------|---------|--------|---------|
| 2c.1 | 实现kg_differential.py | **移植MedRAG `main_MedRAG.py`→`get_additional_info_from_level_2()`(第92-140行)**: 诊断差异KG预计算。核心改造: 同EL2下疾病间differential_from边计算，包含key_features列表和difficulty评级 | core/kg/kg_differential.py | 差异边正确计算 |
| 2c.2 | 计算Wilson差异边 | Wilson病 vs AIH(4个鉴别点:铜蓝蛋白/K-F环/自身抗体/尿铜) / 血色病(3个鉴别点:铜蓝蛋白/铁代谢/基因) / PBC(鉴别点) | 差异边数据 | 差异边≥3条 |
| 2c.3 | 实现contradicts边 | 排除诊断关系：如铜蓝蛋白≥0.20g/L contradicts Wilson病(strength=strong) | contradicts边 | 排除边≥1条 |
| 2c.4 | 实现kg_builder.py | 离线构建管道主入口：串联chunker→extractor→validator→importer→writer→embedder→differential→cleaner | core/kg/kg_builder.py | 端到端构建成功，支持增量更新 |
| 2c.5 | JSON Snapshot | 生成版本快照(data/kg/snapshot_v1.json)，包含所有节点/关系/属性，便于版本控制和diff | data/kg/snapshot_v1.json | 快照完整，可反序列化 |
| 2c.6 | 构建验证 | Cypher查询验证节点数、关系数、属性完整性、Triple Linking覆盖率 | 验证报告 | 节点>30，关系>50，属性完整，Triple Linking 100% |

**里程碑M2**: Wilson病KG构建完成，Neo4j节点>30，关系>50，Milvus索引就绪，嵌入质量达标

---

### Phase 3: 检索引擎（Week 6-7）

#### Phase 3a: 级联检索管道（Week 6）

| # | 任务 | 具体工作 | 产出物 | 验收标准 |
|---|------|---------|--------|---------|
| 3a.1 | 实现kg_retriever.py | **移植MedGraphRAG `nano_graphrag/_op.py`→`_build_local_query_context()`(第596-687行)**: 级联检索管道。**移植MedGraphRAG `nano_graphrag/_op.py`→`_find_most_related_edges_from_entities()`(第562-593行)**: 图扩展。**移植MedGraphRAG `nano_graphrag/_utils.py`→`truncate_list_by_token_size()`(第35-42行)**: Token截断。核心改造: 四级管道(Milvus粗排→Neo4j图扩展→投票排序→差异注入+Token截断) | core/kg/kg_retriever.py | 管道端到端运行 |
| 3a.2 | Stage 1: 向量粗排 | Milvus COSINE搜索(参数见4.4.1节): top_k=20, radius=0.2，返回匹配的EL4特征节点 | 粗排模块 | 延迟<30ms，Wilson病相关实体命中率>80% |
| 3a.3 | Stage 2: 图扩展 | **移植MedGraphRAG `nano_graphrag/_op.py`→`_find_most_related_edges_from_entities()`(第562-593行)**: Neo4j 1-hop邻居扩展+edge_degree排序，从EL4向上遍历到EL3/EL2/EL1 | 图扩展模块 | 延迟<50ms，正确关联EL4→EL3 |
| 3a.4 | 双路径检索入口 | 路径A: 语义模糊匹配(BGE-M3嵌入→Milvus)；路径B: Top-down分诊提示(triage_hint→EL2→EL3) | 双路径模块 | 路径A为主，路径B可选 |

#### Phase 3b: 投票分类、统一API与降级（Week 7）

| # | 任务 | 具体工作 | 产出物 | 验收标准 |
|---|------|---------|--------|---------|
| 3b.1 | 实现kg_classifier.py | **移植MedRAG `KG_Retrieve.py`→`find_closest_category()`(第150-197行)** + **`compute_shortest_path_length()`(第116-120行)**: 投票分类。核心改造: 类别改为罕见肝病子类(铜代谢/自身免疫/胆汁淤积/代谢性)，NetworkX→Neo4j Cypher shortestPath | core/kg/kg_classifier.py | Wilson病top-1命中率>80% |
| 3b.2 | 特征权重实现 | EL4d核心特征(is_core=true, weight=2.0) vs 支持特征(is_core=false, weight=1.0) | 权重逻辑 | 铜蓝蛋白<0.20g/L权重2.0，震颤权重1.0 |
| 3b.3 | 实现kg_interface.py | 统一查询API+三级降级策略(3.4节)，对外暴露`retrieve(query, patient_data) → KGRetrievalResult` | core/kg/kg_interface.py | API可调用，降级逻辑正确 |
| 3b.4 | 降级策略实现 | Level1: Neo4j+Milvus完整检索; Level2: Milvus纯向量检索; Level3: 原有knowledge_retriever文本检索 | 降级逻辑 | Neo4j断开后系统仍可运行，自动降级到Level2 |
| 3b.5 | 检索延迟优化 | 缓存热门查询+异步嵌入生成+Milvus批量搜索 | 优化代码 | P95<200ms |
| 3b.6 | 嵌入质量调优 | 调整BGE-M3参数+验证中文医学文本嵌入效果，必要时调整IVF_FLAT nlist参数 | 调优报告 | top-1命中率>80% |
| 3b.7 | 检索基准测试 | 使用Wilson病典型病例测试检索质量 | 基准报告 | 召回率>85%，P95<200ms |

**里程碑M3**: 检索引擎完成，端到端P95<200ms，Wilson病top-1命中率>80%，三级降级正常

---

### Phase 4: 系统集成（Week 8-9）

#### Phase 4a: LangGraph工作流集成（Week 8前半）

| # | 任务 | 具体工作 | 产出物 | 验收标准 |
|---|------|---------|--------|---------|
| 4a.1 | State字段扩展 | 新增`kg_retrieval_result`(KGRetrievalResult)、`kg_question_recommendations`(List[str])字段到DiagnosticState | state_definition.py | 字段定义正确，向后兼容 |
| 4a.2 | Feature Flag集成 | config.yaml中knowledge_graph.enabled控制KG开关，每个集成点检查enabled状态 | 配置+代码 | enabled=false时行为与集成前完全一致 |
| 4a.3 | 预处理节点集成 | `_node_preprocessing`中新增KG激活调用：当enabled=true时调用kg_interface.retrieve() | graph_orchestrator.py | KG激活正常，结果写入State |
| 4a.4 | MDT辩论注入 | `_node_mdt_debate`中注入KG差异上下文(diagnostic_differences)到Agent prompt | graph_orchestrator.py | 辩论含差异信息，Feature Flag可控 |

#### Phase 4b: 工具层替换与端到端测试（Week 8后半-Week 9）

| # | 任务 | 具体工作 | 产出物 | 验收标准 |
|---|------|---------|--------|---------|
| 4b.1 | 替换FalsificationEngine | KG contradicts关系替代硬编码if-elif规则，保留原有逻辑作为降级方案 | falsification.py修改 | 证伪逻辑正确，降级回退正常 |
| 4b.2 | 替换GuidelineVerifier | KG guided_by关系替代硬编码字典，保留原有逻辑作为降级方案 | guideline_verifier.py修改 | 指南验证正确，降级回退正常 |
| 4b.3 | 替换InformationGapAssessor | KG IC值/度中心性→追问优先级，保留原有逻辑作为降级方案 | information_gap_assessor.py修改 | 追问推荐合理 |
| 4b.4 | 端到端测试 | 完整诊断流程测试：预处理→分诊→MDT辩论→证伪→指南验证→报告 | 测试报告 | 全流程无报错 |
| 4b.5 | A/B对比测试 | KG检索 vs 原有knowledge_retriever文本检索对比，使用Wilson病典型病例 | 对比报告 | KG方案准确率提升 |
| 4b.6 | 降级测试 | Neo4j/Milvus故障注入，验证三级降级策略(Level1→Level2→Level3) | 降级测试报告 | 三级降级均正常，无系统崩溃 |
| 4b.7 | Feature Flag回归测试 | enabled=false时系统行为与KG集成前完全一致 | 回归测试报告 | 无回归Bug |
| 4b.8 | 性能基准测试 | 端到端延迟、检索质量、内存占用 | 性能报告 | P95<200ms，内存增量<500MB |
| 4b.9 | 文档更新 | 更新README、API文档、架构文档 | 文档 | 文档与代码一致 |

**里程碑M4**: 系统集成完成，Feature Flag可切换，所有测试通过，性能达标

---

## 8. 资源配置

### 8.1 人力资源

| 角色 | 人数 | 技能要求 | 参与阶段 | 工作量 |
|------|------|---------|---------|--------|
| **全栈开发** | 1人 | Python+Neo4j+Milvus+LangGraph+LLM API | Phase 0-4全程 | 9周×100% |
| **肝病专家** | 1人 | 肝病临床诊断经验 | Phase 1b(审核) | 4-6小时 |
| **测试工程师** | 0.5人 | 自动化测试+性能测试 | Phase 4b | 1周×50% |

### 8.2 技术资源

| 资源 | 规格 | 用途 | 获取方式 | 前置条件 |
|------|------|------|---------|---------|
| **GPU** | 1×A100(40GB) 或 CPU替代 | BGE-M3嵌入生成 | 本地/云服务器 | CPU可用但慢3-5× |
| **Neo4j** | Community 5.x, 4GB内存 | 图结构存储 | Docker部署 | Docker环境 |
| **Milvus** | Standalone | 向量索引存储 | Docker部署 | Docker环境 |
| **LLM API** | 通义千问 qwen-plus | 实体/关系提取 | DashScope API | API Key |
| **BGE-M3模型** | BAAI/bge-m3 (~2.2GB) | 语义嵌入生成(1024-dim) | HuggingFace下载 | 网络访问 |

### 8.3 工具链

| 工具 | 用途 | 安装方式 | 阶段 |
|------|------|---------|------|
| PyMuPDF | 指南PDF解析+章节分割 | pip install PyMuPDF | Phase 1a |
| neo4j (Python driver) | Neo4j连接+Cypher执行 | pip install neo4j | Phase 1a |
| pymilvus | Milvus连接+向量操作 | 取消注释requirements.txt第48行 | Phase 1a |
| sentence-transformers | BGE-M3嵌入生成 | pip install sentence-transformers | Phase 1a |
| obonet | HPO本体加载(后续Phase 6) | pip install obonet | Phase 6 |
| rapidfuzz | 模糊匹配(后续) | pip install rapidfuzz | Phase 6 |
| NetworkX | 开发阶段图存储(已依赖) | 已在requirements.txt | Phase 0 |

### 8.4 存储需求

| 存储类型 | 容量 | 内容 | 说明 |
|----------|------|------|------|
| Neo4j数据 | ~500MB | Wilson病节点+关系+属性 | Community版单机 |
| Milvus索引 | ~200MB | Wilson病嵌入向量(1024-dim×~80条) | IVF_FLAT索引 |
| JSON Snapshot | ~50KB | 版本快照(文本) | 压缩后更小 |
| BGE-M3模型 | ~2.2GB | 嵌入模型文件 | 首次下载后缓存 |
| LLM缓存 | ~10MB | kg_cache JSON文件 | 按需增长 |
| 嵌入缓存 | ~5MB | .npy嵌入持久化文件 | 按需增长 |
| **合计** | **~3GB** | 仅Wilson病 | GPU内存另需~4GB |

### 8.5 成本估算

| 项目 | 数量 | 单价 | 小计 | 说明 |
|------|------|------|------|------|
| LLM API调用 | ~80次(Wilson病) | ~¥0.25/次 | ~¥20 | 首次提取+Gleaning补充(缓存后重复免费) |
| GPU使用 | 9周(可CPU替代) | — | ¥0-500 | CPU替代时免费但慢 |
| Neo4j | Community免费 | — | ¥0 | Docker自部署 |
| Milvus | Standalone免费 | — | ¥0 | Docker自部署 |
| **合计** | | | **¥20-520** | 极低成本 |

---

## 9. 质量控制标准与验收指标

### 9.1 数据质量标准

| 质量维度 | 标准 | 验证方法 | 不合格处理 |
|----------|------|---------|-----------|
| **阈值精确性** | 所有数值型阈值与指南原文100%一致 | 逐条人工比对 | 标记confidence=low，重新提取或人工修正 |
| **实体完整性** | Wilson病核心诊断特征覆盖率>95% | 与Leipzig评分标准对照 | 补充遗漏特征 |
| **关系正确性** | 关系类型和方向准确率>95% | 抽样审核(≥20条) | 修正错误关系 |
| **Triple Linking** | 每个EL4节点关联指南原文段落(source_guideline+section+page) | 抽样验证(≥10条) | 补充缺失链接 |
| **去重率** | 无重复实体和关系 | Cypher去重查询 | 合并重复项 |
| **孤立节点率** | 孤立节点数=0 | Cypher孤立节点查询 | 删除或关联孤立节点 |
| **confidence分布** | confidence=high占比>90% | 统计分析 | 重新审核medium/low项 |

### 9.2 检索质量标准

| 指标 | 标准 | 测试方法 | 不合格处理 |
|------|------|---------|-----------|
| **Top-1命中率** | >80%(Wilson病典型病例) | 标准测试用例(9.4节) | 调整嵌入参数或检索策略 |
| **Top-5召回率** | >85% | 标准测试用例 | 扩大top_k或优化图扩展 |
| **语义匹配质量** | 同义实体相似度>0.8，异义<0.5 | 嵌入质量验证 | 调整BGE-M3参数或微调 |
| **差异KG完整性** | Wilson病vs AIH/血色病/PBC差异边≥3条 | Cypher查询 | 补充差异边 |
| **端到端延迟** | P95<200ms | 性能基准测试(100次查询) | 启用缓存/异步/降级 |
| **各级Stage延迟** | Stage1<30ms, Stage2<50ms, Stage3<35ms, Stage4<10ms | 分阶段计时 | 优化对应Stage |

### 9.3 系统集成验收标准

| # | 验收项 | 标准 | 测试方法 | 不合格处理 |
|---|--------|------|---------|-----------|
| 1 | GraphUpdater移除 | graph_update节点不存在，全代码库无GraphUpdater引用 | 代码审查+grep搜索 | 继续清理 |
| 2 | Wilson病KG完整性 | EL1-EL4节点+8种关系正确创建 | Cypher查询验证 | 修正缺失节点/关系 |
| 3 | 阈值精确性 | 所有数值型阈值与指南原文一致 | 逐条比对 | 重新审核修正 |
| 4 | Triple Linking | 每个EL4节点关联指南原文段落 | 抽样验证(≥10条) | 补充链接 |
| 5 | Milvus索引 | Wilson病相关查询top-1命中率>80% | 嵌入质量测试 | 调整嵌入参数 |
| 6 | 检索延迟 | P95<200ms | 性能基准(100次查询) | 优化或降级 |
| 7 | 降级策略 | Neo4j断开后系统仍可运行(Level2)，Milvus断开后回退(Level3) | 故障注入测试 | 修复降级逻辑 |
| 8 | Feature Flag | enabled=false时行为与集成前完全一致 | A/B对比测试 | 修复Flag逻辑 |
| 9 | 回归测试 | 所有现有测试通过 | 测试套件 | 修复回归Bug |
| 10 | 内存增量 | KG模块内存占用增量<500MB | 内存监控 | 优化内存使用 |

### 9.4 激活基准测试用例

| 用例名 | 患者特征 | 预期Top疾病 | 最低激活分数 | 预期差异KG |
|--------|---------|------------|-------------|-----------|
| Wilson病典型 | 震颤、黄疸、铜蓝蛋白0.08g/L、K-F环阳性 | wilson_disease | 0.7 | vs AIH(4点), vs 血色病(3点) |
| Wilson病非典型 | 仅铜蓝蛋白0.15g/L+ALT升高 | wilson_disease | 0.4 | vs AIH(4点) |
| Wilson vs AIH鉴别 | 黄疸+ALT升高+年轻女性+ANA阳性 | wilson_disease + aih | — | 4个鉴别点 |
| 排除Wilson | 铜蓝蛋白0.35g/L+ANA阳性 | aih(非wilson) | contradicts触发 | 铜蓝蛋白≥0.20g/L contradicts Wilson |
| 语义匹配测试 | "铜蓝蛋白偏低" | 匹配EL4d:铜蓝蛋白降低 | 相似度>0.8 | — |
| 口语化表述测试 | "眼睛有铜环" | 匹配EL4d:K-F环阳性 | 相似度>0.7 | — |

---

## 10. 潜在风险评估及应对措施

### 10.1 风险矩阵

| # | 风险 | 概率 | 影响 | 严重度 | 应对措施 | 监控指标 |
|---|------|------|------|--------|---------|---------|
| R1 | LLM提取的医学阈值不准确 | 高 | 高 | **严重** | 人工审核所有数值型阈值；Triple Linking溯源指南原文；confidence分级标记 | confidence=high占比 |
| R2 | 仅Wilson病有指南PDF，KG覆盖不足 | 高 | 中 | **重要** | 先构建Wilson病KG原型验证；后续逐步补充其他疾病指南 | 疾病覆盖数 |
| R3 | Neo4j部署和运维成本 | 中 | 中 | **重要** | 开发阶段用NetworkX(engine=networkx)，生产阶段再迁移Neo4j | Neo4j连接成功率 |
| R4 | Milvus向量索引质量(中文医学文本) | 中 | 中 | **重要** | BGE-M3对中文优化；构建时验证嵌入质量(同义>0.8,异义<0.5)；调整IVF_FLAT参数 | top-1命中率 |
| R5 | 四层KG层级划分不合理 | 中 | 中 | **重要** | 参考罕见肝病目录辅助划分；支持动态调整；专家确认 | EL1/EL2层级数 |
| R6 | HPO本体未下载，无法计算IC值 | 中 | 低 | **一般** | 当前用均匀权重(IC值=1.0)替代；后续下载HPO后升级为IC值加权 | IC值来源标记 |
| R7 | 检索延迟超出预期(>500ms) | 低 | 高 | **重要** | 三级降级策略；异步检索；缓存热门查询；分Stage优化 | P95延迟 |
| R8 | 与现有系统集成引入回归Bug | 中 | 高 | **严重** | Feature Flag渐进式替换；完整测试覆盖；降级路径保留 | 回归测试通过率 |
| R9 | BGE-M3模型对医学专业术语嵌入质量不足 | 中 | 中 | **重要** | 构建时验证嵌入质量；必要时微调或替换模型(如PubMedBERT) | 同义/异义相似度 |
| R10 | 人工审核资源不足(肝病专家时间有限) | 中 | 高 | **严重** | 优先审核核心阈值(is_core=true)；非核心阈值标记待审核；kg_validator自动生成审核清单 | 审核完成率 |
| R11 | Milvus/Neo4j Docker部署环境问题 | 中 | 中 | **重要** | 提前验证Docker环境；准备docker-compose.yml；NetworkX降级方案 | 服务启动成功率 |
| R12 | LLM API调用成本超预期或服务不稳定 | 低 | 中 | **一般** | kg_cache缓存避免重复调用；控制Gleaning轮数(1轮)；准备备用API | API调用次数/成本 |

### 10.2 关键风险详细应对

#### R1: LLM提取的医学阈值不准确

```
应对策略:
1. 三级审核机制:
   ├── LLM自动验证: 提取结果与指南原文自动比对(PyMuPDF原文定位)
   ├── 数值型阈值强制审核: 所有含数值的实体必须人工确认
   └── confidence分级: high(直接入图) / medium(待确认) / low(待重提取)

2. Triple Linking溯源:
   每个阈值节点关联指南原文段落:
   {
       "value": 0.20, "unit": "g/L", "operator": "<",
       "source": {
           "guideline": "CMA_Wilson_2022",
           "section": "4. 实验室检查", "page": 5,
           "original_text": "血清铜蓝蛋白 < 0.20 g/L"
       },
       "confidence": "high", "verified_by": "人工审核"
   }

3. YAML交叉参考(仅参考,不作为权威):
   LLM提取的阈值与YAML比对，不一致时以指南PDF为准，记录差异
   已知冲突: 铜蓝蛋白阈值(YAML<0.20 vs guideline_verifier<0.1)
```

#### R8: 系统集成引入回归Bug

```
应对策略:
1. Feature Flag控制:
   knowledge_graph.enabled = false  → 系统行为与集成前完全一致
   knowledge_graph.enabled = true   → 启用KG功能
   每个集成点(falsification/guideline_verify/info_gap/debate)独立Flag

2. 渐进式替换:
   Phase 4b中每个替换均保留原有逻辑作为降级方案:
   falsification: KG contradicts → 降级到原有if-elif
   guideline_verify: KG guided_by → 降级到原有硬编码字典
   info_gap: KG IC值/度中心性 → 降级到原有InformationGapAssessor

3. 完整测试覆盖:
   每个Phase结束运行回归测试套件
   Phase 4b专门进行A/B对比和降级测试
   Feature Flag测试: enabled=false时行为完全一致
```

#### R10: 人工审核资源不足

```
应对策略:
1. 优先级排序:
   ├── P0(必须审核): is_core=true的数值型阈值(铜蓝蛋白/K-F环/尿铜/肝铜/ATP7B)
   ├── P1(建议审核): is_core=false的数值型阈值
   └── P2(可后续审核): 定性描述型知识(EL4a)

2. kg_validator辅助:
   ├── 自动生成审核清单(按优先级排序)
   ├── 自动标注confidence(与指南原文自动比对)
   └── 差异高亮(LLM提取值 vs 指南原文)

3. 审核时间估算:
   Wilson病核心阈值: ~10条 × 3分钟/条 = ~30分钟
   Wilson病全部阈值: ~35条 × 3分钟/条 = ~2小时
   总计: 4-6小时(含关系审核)
```

#### R11: Docker部署环境问题

```
应对策略:
1. 提前验证:
   Phase 1a中优先部署Neo4j和Milvus Docker容器
   验证Docker版本、内存限制、网络配置

2. 降级方案:
   Neo4j不可用 → 使用NetworkX(engine=networkx)作为图存储
   Milvus不可用 → 使用FAISS本地向量索引(无需Docker)

3. docker-compose.yml:
   提前编写统一的docker-compose.yml，包含Neo4j+Milvus服务定义
```

---

## 11. 项目交付物清单

### 11.1 代码交付物

| # | 交付物 | 路径 | 阶段 | 源码映射 | 验收标准 |
|---|--------|------|------|---------|---------|
| 1 | KG数据类定义 | `core/kg/kg_schema.py` | Phase 1a | — | 数据类可实例化，类型检查通过 |
| 2 | KG配置模块 | `core/kg_config.py` | Phase 1a | — | 配置正确加载，默认值合理 |
| 3 | LLM调用缓存 | `core/kg_cache.py` | Phase 1a | MedGraphRAG `_llm.py`→`openai_complete_if_cache()` | 缓存命中/未命中逻辑正确 |
| 4 | 医学文本语义分块 | `core/kg/kg_chunker.py` | Phase 1b | MedGraphRAG `agentic_chunker.py`→`AgenticChunker` | Wilson指南PDF正确分块 |
| 5 | LLM实体/关系提取 | `core/kg/kg_extractor.py` | Phase 1b | MedGraphRAG `_op.py`→`extract_entities()` + `prompt.py`→`PROMPTS["entity_extraction"]` | 提取实体+关系列表，Gleaning>5%增量 |
| 6 | 阈值验证+审核辅助 | `core/kg/kg_validator.py` | Phase 1b | — | 审核清单可导出，confidence自动标记 |
| 7 | 四层KG导入器 | `core/kg/kg_importer.py` | Phase 2a | MedGraphRAG `three_layer_import.py`→`ThreeLayerImporter` | 四层节点正确创建，8种关系支持 |
| 8 | Neo4j写入模块 | `core/kg/kg_writer.py` | Phase 2a | MedGraphRAG `creat_graph_with_description.py`→`create_neo4j_nodes_and_relationships()` | 写入成功，支持幂等重入 |
| 9 | 图谱后处理 | `core/kg/kg_cleaner.py` | Phase 2a | MedGraphRAG `utils.py`→`merge_similar_nodes()` | 无孤立节点，无重复实体 |
| 10 | BGE-M3嵌入+Milvus索引 | `core/kg/kg_embedder.py` | Phase 2b | MedRAG `KG_Retrieve.py`→`get_symptom_embeddings()` + MedGraphRAG `_storage.py`→`MilvusLiteStorge` | Milvus索引创建成功，COSINE度量 |
| 11 | 诊断差异KG预计算 | `core/kg/kg_differential.py` | Phase 2c | MedRAG `main_MedRAG.py`→`get_additional_info_from_level_2()` | 差异边正确计算，≥3条 |
| 12 | 离线构建管道主入口 | `core/kg/kg_builder.py` | Phase 2c | — | 端到端构建成功，支持增量更新 |
| 13 | 级联检索管道 | `core/kg/kg_retriever.py` | Phase 3a | MedGraphRAG `_op.py`→`_build_local_query_context()` + `_find_most_related_edges_from_entities()` | 四级管道端到端运行 |
| 14 | 投票分类 | `core/kg/kg_classifier.py` | Phase 3b | MedRAG `KG_Retrieve.py`→`find_closest_category()` + `compute_shortest_path_length()` | Wilson病top-1命中率>80% |
| 15 | 统一查询API+降级 | `core/kg/kg_interface.py` | Phase 3b | MedGraphRAG `retrieve.py`→`seq_ret()` | API可调用，三级降级正常 |
| 16 | 修改后的graph_orchestrator.py | `core/graph_orchestrator.py` | Phase 4a | — | KG激活正常，Feature Flag可控 |
| 17 | 修改后的state_definition.py | `core/state_definition.py` | Phase 4a | — | 新增字段正确，向后兼容 |
| 18 | 修改后的falsification.py | `core/medical_middleware/falsification.py` | Phase 4b | — | KG contradicts替换，降级正常 |
| 19 | 修改后的guideline_verifier.py | `core/medical_middleware/guideline_verifier.py` | Phase 4b | — | KG guided_by替换，降级正常 |
| 20 | 更新的config.yaml | `config.yaml` | Phase 0+4 | — | knowledge_graph配置段完整 |
| 21 | 更新的requirements.txt | `requirements.txt` | Phase 1a | — | pymilvus取消注释，neo4j等新增 |
| 22 | docker-compose.yml | `docker-compose.yml` | Phase 1a | — | Neo4j+Milvus服务定义 |

### 11.2 数据交付物

| # | 交付物 | 路径 | 阶段 | 验收标准 |
|---|--------|------|------|---------|
| 1 | Wilson病审核后实体/关系JSON | `data/kg/wilson_verified.json` | Phase 1b | JSON格式校验通过，阈值0冲突 |
| 2 | 审核差异报告 | `data/kg/audit_diff_report.json` | Phase 1b | 差异项已记录(铜蓝蛋白/EASL版本/曲恩汀) |
| 3 | Neo4j图数据(Wilson病) | Neo4j实例 | Phase 2a | 节点>30，关系>50，属性完整 |
| 4 | Milvus向量索引(Wilson病) | Milvus实例 | Phase 2b | kg_entities Collection，嵌入>80条 |
| 5 | KG版本快照 | `data/kg/snapshot_v1.json` | Phase 2c | 快照完整，可反序列化 |
| 6 | LLM缓存文件 | `.kg_cache/` | Phase 1b+ | 缓存命中时零LLM调用 |
| 7 | 嵌入持久化文件 | `.kg_embeddings/` | Phase 2b | .npy文件可加载 |

### 11.3 文档交付物

| # | 交付物 | 阶段 | 验收标准 |
|---|--------|------|---------|
| 1 | 阈值审核报告 | Phase 1b | 覆盖所有数值型阈值，标注confidence |
| 2 | 嵌入质量验证报告 | Phase 2b | 同义>0.8，异义<0.5 |
| 3 | 构建验证报告 | Phase 2c | 节点>30，关系>50，Triple Linking 100% |
| 4 | 检索基准测试报告 | Phase 3b | 召回率>85%，P95<200ms |
| 5 | A/B对比测试报告 | Phase 4b | KG方案准确率提升 |
| 6 | 降级测试报告 | Phase 4b | 三级降级均正常 |
| 7 | 性能基准报告 | Phase 4b | P95<200ms，内存增量<500MB |
| 8 | 更新的README和API文档 | Phase 4b | 文档与代码一致 |

### 11.4 里程碑交付物

| 里程碑 | 时间 | 交付物 | 验收标准 |
|--------|------|--------|---------|
| M0: 架构清理完成 | Week 1 | GraphUpdater移除+测试通过+KG配置段 | 全代码库无GraphUpdater引用，测试通过 |
| M1: 数据提取完成 | Week 3 | 审核后JSON+审核报告+差异报告 | 阈值0冲突，confidence=high占比>90% |
| M2: KG构建完成 | Week 5 | Neo4j图+Milvus索引+JSON快照+构建验证报告 | 节点>30，关系>50，嵌入质量达标 |
| M3: 检索引擎完成 | Week 7 | 检索管道+基准测试报告 | P95<200ms，top-1命中率>80%，三级降级正常 |
| M4: 系统集成完成 | Week 9 | 集成后系统+A/B报告+降级报告+性能报告 | Feature Flag可切换，所有测试通过 |

---

## 12. 长期演进路径

### 12.1 Phase 5: 多疾病KG扩展（Week 10-15，后续）

```
当前(Phase 0-4): Wilson病KG + 级联检索
    │
    ▼ 补充指南PDF后
扩展Phase 5: 多疾病KG
    ├── 补充AIH指南PDF → AIH KG节点+差异边
    ├── 补充PBC指南PDF → PBC KG节点+差异边
    ├── 补充血色病指南PDF → 血色病KG节点+差异边
    ├── 补充α1-抗胰蛋白酶缺乏症指南PDF → KG节点
    ├── 补充PSC指南PDF → KG节点(需同步补充rare_disease_db和guideline_search)
    │
    ▼ 每新增一种疾病指南:
    1. PyMuPDF解析 → 章节分割
    2. LLM实体/关系提取(使用4.1.1节prompt) → Gleaning补充(使用5.3节循环)
    3. 人工审核阈值(使用kg_validator)
    4. 创建EL3节点 + EL4特征 + 差异边(使用kg_differential)
    5. 更新Milvus向量索引(使用kg_embedder预计算持久化)
    6. LLM缓存自动生效(使用kg_cache)
    增量成本: ~4小时/疾病(含人工审核)
```

### 12.2 Phase 6: HPO本体层接入（后续）

```
    ▼ 下载HPO文件后
扩展Phase 6: HPO本体层接入
    ├── 下载hp.obo + phenotype.hpoa
    ├── Layer 3本体层建设
    ├── IC值计算 → 替代均匀权重(当前IC值=1.0)
    ├── 标准术语映射 → 提升检索精度
    ├── HPO嵌入索引 → 语义匹配增强
    └── REFERENCE跨层链接 → Triple Linking完整化
```

### 12.3 Phase 7: YAML规则融合（可选，需专家验证后）

```
    ▼ 专家验证YAML后
扩展Phase 7: YAML规则融合(可选)
    ├── 经专家验证的YAML规则 → 可作为EL4d补充数据源
    ├── 未验证规则 → 继续仅作运行时参考
    └── 提升KG覆盖度
```

### 12.4 Phase 8: 高级功能（长期）

```
    ▼ KG基础稳定后
扩展Phase 8: 高级功能
    ├── GNN消息传递图推理
    ├── 跨模态病例检索
    ├── Orphanet/OMIM API实时集成
    └── LLM肝病SFT微调
```

---

*本方案v3.0基于对 MedGraphRAG (`ImprintLab/Medical-Graph-RAG`) 和 MedRAG (`SNOWTEAM2023/MedRAG`) 两个开源仓库的完整代码分析，补充了以下关键内容：(1) 代码级实现细节——LLM prompt模板(4.1节)、响应解析正则(4.2节)、Cypher MERGE语句(4.3节)、Milvus search_params(4.4节)；(2) 关键工程优化——LLM调用缓存(5.1节)、嵌入预计算持久化(5.2节)、Gleaning补全循环(5.3节)、Token预算截断(5.4节)、并发提取(5.5节)；(3) 每个模块的源仓库/源文件/源函数/行号映射(3.6节+11.1节)。核心约束不变：YAML规则未经验证不用于KG构建、HPO本体文件未下载、仅指南PDF为权威数据源。Phase 0-4总计9周，以Wilson病为原型验证完整KG构建流程，后续按Phase 5-8路径逐步扩展。*
