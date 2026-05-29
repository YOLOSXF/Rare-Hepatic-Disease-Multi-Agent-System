# 基于 MedGraphRAG 与 MedRAG 的知识图谱构建与检索适配方案

> **参考代码仓库**：
> - MedGraphRAG: [ImprintLab/Medical-Graph-RAG](https://github.com/ImprintLab/Medical-Graph-RAG)（三层图构建 + U-Retrieval + Neo4j/Milvus）
> - MedRAG: [SNOWTEAM2023/MedRAG](https://github.com/SNOWTEAM2023/MedRAG)（KG检索 + 最短路径投票 + FAISS）
>
> **目标系统**：Rare-Hepatic-Disease-Multi-Agent-System
>
> **文档版本**：v1.0 / 2026-05-07

---

## 目录

1. [两个代码仓库的技术方案对比分析](#1-两个代码仓库的技术方案对比分析)
2. [核心可复用设计提取](#2-核心可复用设计提取)
3. [整体适配架构设计](#3-整体适配架构设计)
4. [Phase 1: 知识图谱构建方案](#4-phase-1-知识图谱构建方案)
5. [Phase 2: 知识图谱检索方案](#5-phase-2-知识图谱检索方案)
6. [关键算法实现](#6-关键算法实现)
7. [性能优化策略](#7-性能优化策略)
8. [与现有系统集成方案](#8-与现有系统集成方案)
9. [实施路线图](#9-实施路线图)

---

## 1. 两个代码仓库的技术方案对比分析

### 1.1 图谱构建对比

| 维度 | MedGraphRAG | MedRAG | 对当前系统的启示 |
|------|------------|--------|-----------------|
| **数据源格式** | 自由文本（PDF/TXT）→ LLM提取 | Excel三元组（S-R-O）→ 直接解析 | 当前系统结合两者：YAML规则→结构化三元组 + 指南PDF→LLM提取 |
| **实体识别** | LLM prompt工程（entity_extraction），14种医学实体类型（Disease/Symptom/Treatment/Medication等） | 无NER——实体从Excel的subject/object列直接读取 | **采纳MedGraphRAG**: 指南PDF段落 → LLM提取，YAML规则→直接解析 |
| **关系抽取** | LLM同次调用输出(源实体, 目标实体, 描述, 强度) | Excel的relation列直接映射 | **采纳MedGraphRAG**: LLM提取的描述+强度信息丰富度远超简单关系标签 |
| **图谱存储** | Neo4j（生产） + NetworkX（纳米图） + Milvus（向量） | NetworkX（内存）+ Excel文件（持久化） | **采纳MedGraphRAG**: Neo4j+Milvus生产级方案；当前系统Milvus已配置 |
| **分层架构** | Bottom(词汇) → Middle(指南) → Top(病例)，通过REFERENCE关系连接 | 无分层——单层S-R-O图 | **采纳MedGraphRAG**: 三层架构对应L_vocab/L_source/L_user |
| **文本预处理** | AgenticChunker（命题级语义分块） + run_chunk（Pydantic链） | 正则清洗（去括号/小写/去标点/NLTK分词） | **采纳MedGraphRAG AgenticChunker**: 医学语义分块效果远超简单规则分块 |
| **图谱后处理** | merge_similar_nodes（LLM判断合并） + remove_isolated_nodes | 无后处理 | **采纳MedGraphRAG**: 节点合并去重对医学KG质量至关重要 |
| **LLM用量优化** | 缓存（openai_complete_if_cache）+ 限制输入长度（3000字符）+ GPT-4o-mini | 无优化——全量调用text-embedding-3-large | **采纳MedGraphRAG**: LLM缓存+输入截断+小模型策略 |

### 1.2 图谱检索对比

| 维度 | MedGraphRAG | MedRAG | 对当前系统的启示 |
|------|------------|--------|-----------------|
| **检索策略** | 三层级联检索: 向量→社区报告→文本单元→关系边 | 嵌入相似度→NetworkX最短路径→类别投票 | **融合两者**: 向量粗排 + 图结构精排 |
| **相似度计算** | Milvus COSINE（radius=0.2搜索半径） | sklearn cosine_similarity（阈值>0.5） | **采纳MedGraphRAG**: Milvus已配置，COSINE阈值可调 |
| **嵌入模型** | OpenAI text-embedding-3-large | OpenAI text-embedding-3-large | 与当前BGE-M3方案不冲突——BGE-M3对中文更优 |
| **图遍历** | 1-hop neighbor查询 + edge_degree排序 | nx.shortest_path_length 最短路径投票 | **融合**: 短路径投票（MedRAG）+ 1-hop邻居扩展（MedGraphRAG） |
| **结果排序** | 多级排序: node_degree > relation_counts > order > weight | 投票计数（category_votes）降序 | **采纳MedGraphRAG**: node_degree作为图谱重要性度量是有效的排序信号 |
| **上下文窗口管理** | truncate_list_by_token_size —— 各层级检索结果按token预算截断 | 无窗口管理——直接拼接检索结果 | **采纳MedGraphRAG**: token预算管理避免超出LLM上下文限制 |
| **摘要级检索** | Community Report JSON + Summary Node 两层摘要聚合 | 无摘要层——直接暴露原始三元组 | **借鉴MedGraphRAG**: 对指南段落生成Summary Node |
| **LLM辅助排序** | seq_ret: LLM评估查询与Summary的相似度（very similar/similar/general/not similar） | 无LLM辅助排序 | **可选**: 权衡算力成本，优先用向量+图结构排序 |

### 1.3 关键差异总结

```
MedGraphRAG的核心优势:
  ✅ 生产级三层图架构（词汇→指南→病例）
  ✅ 完整的图谱后处理流水线（合并/清理/摘要）
  ✅ Token预算管理的多级检索管道
  ✅ LLM缓存+输入截断的工程优化生存策略

MedRAG的核心优势:
  ✅ 最短路径投票策略——直观且计算轻量
  ✅ 图→分类的直接映射——简洁高效
  ✅ KG嵌入预计算+持久化——减少重复LLM调用
  ✅ 疾病大类→子类的层级溯源检索

对当前系统的最优策略:
  构建层 → MedGraphRAG的三层Neo4j方案（AgenticChunker+LLM提取+后处理）
  检索层 → MedGraphRAG的级联检索管道(Milvus→Graph→Relation) +
           MedRAG的最短路径投票(疾病子类定位)
  存储层 → MedGraphRAG的Neo4j+Milvus双存储
```

---

## 2. 核心可复用设计提取

### 2.1 从 MedGraphRAG 可直接复用

| 组件 | 源文件 | 复用方式 | 改造点 |
|------|--------|---------|--------|
| `extract_entities_with_description()` | `creat_graph_with_description.py:L33-L130` | 直接移植为 `core/kg_extractor.py` | 修改entity_types为肝病领域;改用通义千问API |
| AgenticChunker | `agentic_chunker.py:L12-L335` | 移植为 `core/kg_chunker.py` | 中文医学文本适配 |
| 三层导入器 | `three_layer_import.py:L17-L263` | 移植为 `core/kg_importer.py` | 三层语义重定义: L_vocab(HPO), L_source(指南PDF), L_user(YAML规则) |
| `create_neo4j_nodes_and_relationships()` | `creat_graph_with_description.py:L133-L308` | 移植为 `core/kg_writer.py` | Cypher语句适配罕见肝病KG Schema |
| `merge_similar_nodes()` | `cleangraph.py` | 移植为 `core/kg_cleaner.py` | 节点相似度阈值调优 |
| Token预算管理 | `_op.py:L596-L639` | 移植为 `core/kg_retriever.py`→`truncate_by_token()` | 适配通义千问token计算 |
| LLM缓存 | `_llm.py`→`openai_complete_if_cache` | 移植为 `core/llm_cache.py` | 适配通义千问API |

### 2.2 从 MedRAG 可直接复用

| 组件 | 源文件 | 复用方式 | 改造点 |
|------|--------|---------|--------|
| `find_closest_category()` | `KG_Retrieve.py:L150-L197` | 移植为 `core/kg_classifier.py` | 类别改为罕见肝病子类(铜代谢/自身免疫/胆汁淤积/代谢性) |
| `compute_shortest_path_length()` | `KG_Retrieve.py:L116-L120` | 移植为 `core/kg_traversal.py`→`shortest_path_vote()` | 使用Neo4j Cypher `shortestPath()` 替代NetworkX |
| KG嵌入预计算+持久化 | `KG_Retrieve.py:L63-L79` | 移植为 `core/kg_embedder.py` | 使用BGE-M3替代text-embedding-3-large |
| KG预处理字典 | `main_MedRAG.py:L47-L65` | 集成到 `core/kg_importer.py` | 作为三层加载的辅助数据格式 |

---

## 3. 整体适配架构设计

### 3.1 总体架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   罕见肝病KG构建与检索系统总架构                                │
│                                                                              │
│  ┌──────────────────────────────────┐  ┌──────────────────────────────────┐  │
│  │        KG构建管道 (Offline)       │  │      KG检索管道 (Online)         │  │
│  └──────────────────────────────────┘  └──────────────────────────────────┘  │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                        数据预处理层                                       │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐    │ │
│  │  │YAML规则  │  │指南PDF   │  │HPO .obo  │  │Orphanet/OMIM API     │    │ │
│  │  │解析器    │  │Chunker   │  │解析器    │  │抓取器                │    │ │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────────┬───────────┘    │ │
│  └───────┼─────────────┼─────────────┼──────────────────┼─────────────────┘ │
│          │             │             │                  │                    │
│          ▼             ▼             ▼                  ▼                    │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                        实体识别与关系抽取层 (借鉴 MedGraphRAG)              │ │
│  │  ┌─────────────────────────────────────────────────────────────────┐    │ │
│  │  │  LLM Entity Extractor (移植 extract_entities_with_description)   │    │ │
│  │  │  Entity Types: Disease, Symptom, LabTest, Imaging, Treatment,    │    │ │
│  │  │                HPO_Term, Guideline, Drug, Anatomy, Biomarker      │    │ │
│  │  │  Output: (entity_name, entity_type, description) +                │    │ │
│  │  │         (source, target, relation_desc, strength)                │    │ │
│  │  └─────────────────────────────────────────────────────────────────┘    │ │
│  │  缓存层: llm_cache (移植 MedGraphRAG openai_complete_if_cache)           │ │
│  └──────────────────────────────────┬──────────────────────────────────────┘ │
│                                     │                                        │
│                                     ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                        图谱后处理层 (借鉴 MedGraphRAG)                     │ │
│  │  ┌───────────────────┐  ┌───────────────────┐  ┌────────────────────┐   │ │
│  │  │ merge_similar_    │  │ remove_isolated_  │  │ generate_community_ │   │ │
│  │  │ nodes (LLM判断)   │  │ nodes             │  │ summaries           │   │ │
│  │  └───────────────────┘  └───────────────────┘  └────────────────────┘   │ │
│  └──────────────────────────────────┬──────────────────────────────────────┘ │
│                                     │                                        │
│                                     ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                        图谱存储层 (借鉴 MedGraphRAG)                       │ │
│  │                                                                          │ │
│  │   ┌─────────────────┐     ┌─────────────────┐    ┌──────────────────┐   │ │
│  │   │ Neo4j (图结构)   │     │ Milvus (向量)    │    │ JSON Snapshots   │   │ │
│  │   │ L_user: YAML★   │     │ L_user实体嵌入  │    │ (版本控制/VCS)   │   │ │
│  │   │ L_source: 指南  │     │ L_source文段嵌入│    │                  │   │ │
│  │   │ L_vocab: HPO术语│     │ L_vocab术语嵌入 │    │                  │   │ │
│  │   └────────┬────────┘     └────────┬────────┘    └──────────────────┘   │ │
│  └────────────┼───────────────────────┼────────────────────────────────────┘ │
│               │                       │                                      │
│  ┌────────────┴───────────────────────┴────────────────────────────────────┐ │
│  │                        图谱检索层 (融合 MedGraphRAG + MedRAG)             │ │
│  │                                                                          │ │
│  │  ① 输入: 患者HPO terms + 异常检验结果                                    │ │
│  │  ② Milvus COSINE → Top-K 候选实体 (借鉴 MedGraphRAG)                    │ │
│  │  ③ Neo4j 1-hop 邻居扩展 → 关系边 (借鉴 MedGraphRAG edge_degree排序)     │ │
│  │  ④ Cypher shortestPath 投票 → 疾病子类 (借鉴 MedRAG 最短路径投票)       │ │
│  │  ⑤ Token截断 → 构建LLM上下文窗口 (借鉴 MedGraphRAG truncate)            │ │
│  │  ⑥ 输出: (候选疾病, 诊断差异特征, 证据溯源链)                           │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                    与LangGraph工作流集成层                                │ │
│  │  L1 → KG异常指标关联    L2 → KG追问推荐                                 │ │
│  │  L3 → KG差异特征注入    L4 → KG替代knowledge_retriever                  │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 模块划分

```
core/
├── kg/
│   ├── __init__.py
│   ├── kg_builder.py         # 离线构建管道主入口
│   ├── kg_chunker.py         # AgenticChunker移植 (文本→语义分块)
│   ├── kg_extractor.py       # LLM实体/关系提取 (移植extract_entities_with_description)
│   ├── kg_importer.py        # 三层架构导入器 (移植ThreeLayerImporter)
│   ├── kg_writer.py          # Neo4j节点/关系写入 (移植create_neo4j_nodes_and_relationships)
│   ├── kg_cleaner.py         # 图谱后处理 (merge_similar_nodes + remove_isolated)
│   ├── kg_embedder.py        # BGE-M3嵌入生成 + Milvus索引
│   ├── kg_retriever.py       # 级联检索管道 (向量→图→关系→投票)
│   ├── kg_classifier.py      # 最短路径投票分类 (移植find_closest_category)
│   ├── kg_traversal.py       # 图遍历工具 (shortest_path + 1-hop neighbor)
│   ├── kg_interface.py       # 统一查询API (对接LangGraph集成)
│   └── kg_schema.py          # 数据类定义 (Entity, Relation, GraphLayer, QueryResult)
│
├── kg_cache.py               # LLM调用缓存 (移植openai_complete_if_cache模式)
└── kg_config.py              # KG系统配置 (Neo4j/Milvus/模型参数/token预算)
```

### 3.3 数据流设计

```
┌───────────────────────────────────────────────────────────────────────────┐
│                          离线构建数据流                                     │
│                                                                            │
│  YAML rules ──→ parse_disease_rules() ──→ L_user_entities ──┐             │
│  HPO .obo   ──→ obonet.parse() ──→ L_vocab_entities ───────┤             │
│  Guidelines ──→ AgenticChunker ──→ chunks ──→ LLM extract ─┤             │
│                 (propositions)       (semantic)   (entities+│             │
│  Orphanet   ──→ API fetch ──→ disease_hpo_pairs ────→      │  relations)  │
│                                                              │             │
│  ┌──────────────────────────────────────────────────────────┘             │
│  │                                                                         │
│  ▼                                                                         │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                  │
│  │ Neo4j Write   │    │ Milvus Index │    │ JSON Snapshot│                  │
│  │ L_user nodes  │    │ BGE-M3 emb   │    │ kg_v2.0.json │                  │
│  │ L_source refs │    │ 1024-dim     │    │              │                  │
│  │ L_vocab terms │    │ COSINE metric│    │              │                  │
│  └──────────────┘    └──────────────┘    └──────────────┘                  │
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                           在线检索数据流                               │  │
│  │                                                                       │  │
│  │  Patient Input ─→ HPO extraction ─→ hpo_ids + lab_abnormalities      │  │
│  │       │                                                               │  │
│  │       ▼                                                               │  │
│  │  ┌─────────────────────────────────────────────┐                      │  │
│  │  │ Stage 1: Vector Search (Milvus)             │                      │  │
│  │  │ query = HPO_terms + lab_text → BGE-M3 emb   │ ← 终态               │  │
│  │  │ top_k = 20, metric = COSINE, radius = 0.2   │                      │  │
│  │  │ → candidate_entity_names[]                  │                      │  │
│  │  └──────────────────┬──────────────────────────┘                      │  │
│  │                     │                                                 │  │
│  │                     ▼                                                 │  │
│  │  ┌─────────────────────────────────────────────┐                      │  │
│  │  │ Stage 2: Graph Expansion (Neo4j)             │                      │  │
│  │  │ 1-hop neighbor: MATCH (n)-[r]-(m) WHERE      │                      │  │
│  │  │   n.name IN candidate_entity_names           │                      │  │
│  │  │ Sort by: r.strength DESC + n.degree DESC      │                      │  │
│  │  │ → expanded_entities + related_diseases        │                      │  │
│  │  └──────────────────┬──────────────────────────┘                      │  │
│  │                     │                                                 │  │
│  │                     ▼                                                 │  │
│  │  ┌─────────────────────────────────────────────┐                      │  │
│  │  │ Stage 3: Category Voting (shortest path)     │                      │  │
│  │  │ 借鉴 MedRAG find_closest_category            │                      │  │
│  │  │ Cypher: shortestPath(symptom, category)       │                      │  │
│  │  │ Vote: category_votes[cat] += 1/distance      │                      │  │
│  │  │ → ranked_disease_categories[]                │                      │  │
│  │  └──────────────────┬──────────────────────────┘                      │  │
│  │                     │                                                 │  │
│  │                     ▼                                                 │  │
│  │  ┌─────────────────────────────────────────────┐                      │  │
│  │  │ Stage 4: Context Assembly                    │                      │  │
│  │  │ truncate_by_token(entities+relations, max)   │                      │  │
│  │  │ → LLM context window                         │                      │  │
│  │  │ → Injection to Agent prompts (L2/L3/L4)     │                      │  │
│  │  └─────────────────────────────────────────────┘                      │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Phase 1: 知识图谱构建方案

### 4.1 数据采集与预处理

#### 4.1.1 数据源标准化

```python
# core/kg_schema.py — 统一数据模型

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

class GraphLayer(Enum):
    L_USER = "l_user"       # YAML规则 → 可更新
    L_SOURCE = "l_source"   # 指南文献 → 固定（版本化）
    L_VOCAB = "l_vocab"     # HPO标准术语 → 固定

class EntityType(Enum):
    DISEASE = "Disease"
    PHENOTYPE = "Phenotype"
    LAB_TEST = "LabTest"
    IMAGING = "Imaging"
    TREATMENT = "Treatment"
    DRUG = "Drug"
    BIOMARKER = "Biomarker"
    GUIDELINE = "Guideline"
    ANATOMY = "Anatomy"

@dataclass
class KGEntity:
    """知识图谱实体 (借鉴 MedGraphRAG entity extraction 输出格式)"""
    entity_id: str                    # UUID
    entity_name: str                  # 标准名（大写）
    entity_type: EntityType
    description: str                  # LLM生成的综合描述
    layer: GraphLayer
    hpo_id: Optional[str] = None      # 仅 L_vocab 层
    source_ref: Optional[str] = None  # L_source 层的来源引用
    embedding: Optional[list] = None  # BGE-M3 1024-dim

@dataclass
class KGRelation:
    """知识图谱关系 (借鉴 MedGraphRAG 的 relationship 五元组)"""
    source_id: str
    target_id: str
    relation_type: str               # has_symptom/has_lab_abnormality/referenced_by等
    description: str                 # LLM生成的关系描述
    strength: float                  # 0-10 关系强度
    layer: GraphLayer
```

#### 4.1.2 文本分块器 — 移植 MedGraphRAG AgenticChunker

```python
# core/kg/kg_chunker.py

class MedicalChunker:
    """
    医学文本语义分块器
    移植自 MedGraphRAG agentic_chunker.py，适配中文医学文本
    
    核心流程:
    1. Proposition Generation: LLM将文本分解为原子命题
    2. Similarity Matching: 每个命题与已有 chunk 的摘要做语义匹配
    3. Dynamic Chunking: 命题归入最相似的 chunk 或新建 chunk
    4. Summary Update: LLM更新每个 chunk 的摘要和标题
    """
    
    def __init__(self, llm_client, embedding_model="BAAI/bge-m3"):
        self.llm = llm_client
        self.embedder = embedding_model
        self.chunks = []  # list of {'id', 'propositions': [], 'title': '', 'summary': ''}
        self.chunk_size_threshold = 5  # 每 chunk 最多命题数
        self.similarity_threshold = 0.65  # 归入已有 chunk 的相似度阈值
    
    async def add_propositions(self, text: str) -> list[str]:
        """LLM将文本分解为原子命题"""
        prompt = f"""将以下医学文本分解为原子命题（每个命题是一句完整的医学陈述）。
只输出命题列表，每行一个命题，不要编号。

文本: {text[:2000]}

原子命题:"""
        response = await self.llm.complete(prompt)
        return [p.strip() for p in response.split('\n') if p.strip()]
    
    async def find_relevant_chunk(self, proposition: str) -> Optional[int]:
        """为命题找到最相关的已有 chunk"""
        prop_emb = await self._embed(proposition)
        
        best_idx = None
        best_score = 0.0
        
        for idx, chunk in enumerate(self.chunks):
            chunk_emb = await self._embed(chunk['summary'])
            score = cosine_similarity([prop_emb], [chunk_emb])[0][0]
            if score > best_score:
                best_score = score
                best_idx = idx
        
        if best_score >= self.similarity_threshold:
            return best_idx
        return None
    
    async def chunk_text(self, text: str, source_id: str) -> list[dict]:
        """主分块方法 — 返回语义连贯的文本块列表"""
        propositions = await self.add_propositions(text)
        
        for prop in propositions:
            chunk_idx = await self.find_relevant_chunk(prop)
            
            if chunk_idx is not None and len(self.chunks[chunk_idx]['propositions']) < self.chunk_size_threshold:
                self.chunks[chunk_idx]['propositions'].append(prop)
                await self._update_chunk_summary(chunk_idx)
            else:
                # 新建 chunk
                new_chunk = {
                    'id': f"{source_id}_chunk_{len(self.chunks)}",
                    'source_id': source_id,
                    'propositions': [prop],
                    'title': await self._generate_title([prop]),
                    'summary': await self._generate_summary([prop]),
                }
                self.chunks.append(new_chunk)
        
        return [
            {'id': c['id'], 'text': ' '.join(c['propositions']),
             'title': c['title'], 'summary': c['summary']}
            for c in self.chunks
        ]
```

### 4.2 实体识别与关系抽取 — 移植 MedGraphRAG LLM Extractor

```python
# core/kg/kg_extractor.py

import re
import asyncio
from typing import List, Tuple
from core.kg.kg_schema import KGEntity, KGRelation

# 移植自 MedGraphRAG nano_graphrag/prompt.py → entity_extraction
MEDICAL_ENTITY_EXTRACTION_PROMPT = """-Goal-
Given a medical text document, identify all medical entities and their relationships.

-Steps-
1. Identify all medical entities. For each entity, extract:
   - entity_name: Standard name, CAPITALIZED
   - entity_type: One of: [{entity_types}]
   - entity_description: Comprehensive clinical description

2. From step 1 entities, identify all *clearly related* pairs.
   For each pair, extract:
   - source_entity: Source entity name
   - target_entity: Target entity name
   - relationship_description: Clinical explanation of the relationship
   - relationship_strength: Score 1-10

Format entity: ("entity"<|><entity_name><|><entity_type><|><entity_description>)
Format relationship: ("relationship"<|><source><|><target><|><description><|><strength>)

Return entities and relationships separated by ##
End with <|COMPLETE|>

-Real Data-
Entity_types: {entity_types}
Text: {input_text}
Output:"""


class KGEntityExtractor:
    """
    LLM驱动的医学实体/关系提取器
    移植自 MedGraphRAG creat_graph_with_description.py → extract_entities_with_description
    
    核心改进:
    - 实体类型特化为罕见肝病领域 (14 → 9种肝病特定类型)
    - 关系描述加入"临床意义"维度
    - 输出直接映射到 KGEntity/KGRelation 数据类
    """
    
    LIVER_ENTITY_TYPES = [
        "LiverDisease",        # Wilson/AIH/PBC/PSC等
        "Phenotype",           # HPO标准术语
        "LabTest",             # 检验项目
        "Imaging",             # 影像学发现
        "Treatment",           # 治疗方案
        "Drug",                # 药物
        "Biomarker",           # 生物标志物
        "ClinicalGuideline",   # 临床指南段落
        "Anatomy",             # 解剖结构
    ]
    
    def __init__(self, llm_client, cache: "LLMCache", model="qwen-plus"):
        self.llm = llm_client
        self.cache = cache
        self.model = model
        self.tuple_delimiter = "<|>"
        self.record_delimiter = "##"
        self.completion_delimiter = "<|COMPLETE|>"
    
    async def extract(self, text: str, layer: str) -> Tuple[List[KGEntity], List[KGRelation]]:
        """从医学文本中提取实体和关系
        
        Args:
            text: 输入的医学文本段落
            layer: 所属图谱层 (l_user/l_source/l_vocab)
        
        Returns:
            (entities, relations) 列表
        """
        # 检查缓存
        cache_key = f"extract_{hash(text)}_{layer}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached
        
        # 构建 prompt
        entity_types_str = ", ".join(self.LIVER_ENTITY_TYPES)
        prompt = MEDICAL_ENTITY_EXTRACTION_PROMPT.format(
            entity_types=entity_types_str,
            input_text=text[:3000],  # 限制输入长度 (借鉴 MedGraphRAG)
        )
        
        # LLM 调用
        response = await self.llm.complete(
            model=self.model,
            prompt=prompt,
            system="You are a medical expert extracting entities and relationships from clinical texts."
        )
        
        # 解析响应 (移植 MedGraphRAG 解析逻辑)
        entities, relations = self._parse_response(response, layer)
        
        # 缓存结果
        await self.cache.set(cache_key, (entities, relations))
        return entities, relations
    
    def _parse_response(self, response: str, layer: str) -> Tuple[List[KGEntity], List[KGRelation]]:
        """移植 MedGraphRAG 的响应解析逻辑 (creat_graph_with_description.py:L80-L129)"""
        entities = []
        relations = []
        
        if not response:
            return entities, relations
        
        records = response.split(self.record_delimiter)
        
        for record in records:
            record = record.strip()
            if not record or self.completion_delimiter in record:
                continue
            
            match = re.search(r'\((.*?)\)', record)
            if not match:
                continue
            
            content = match.group(1)
            attributes = [a.strip().strip('"').strip("'") for a in content.split(self.tuple_delimiter)]
            
            if len(attributes) < 2:
                continue
            
            record_type = attributes[0]
            
            if record_type == "entity" and len(attributes) >= 4:
                entity = KGEntity(
                    entity_id=compute_mdhash_id(attributes[1], prefix="ent-"),
                    entity_name=attributes[1].upper(),
                    entity_type=attributes[2].upper(),
                    description=attributes[3],
                    layer=layer,
                )
                if entity.entity_name:
                    entities.append(entity)
            
            elif record_type == "relationship" and len(attributes) >= 5:
                try:
                    strength = float(attributes[4])
                except ValueError:
                    strength = 5.0  # 默认中等强度
                
                relation = KGRelation(
                    source_id=compute_mdhash_id(attributes[1], prefix="ent-"),
                    target_id=compute_mdhash_id(attributes[2], prefix="ent-"),
                    source_name=attributes[1].upper(),
                    target_name=attributes[2].upper(),
                    relation_type="related_to",  # LLM推断
                    description=attributes[3],
                    strength=strength,
                    layer=layer,
                )
                if relation.source_name and relation.target_name:
                    relations.append(relation)
        
        return entities, relations
```

### 4.3 图谱写入 — Neo4j 持久化

```python
# core/kg/kg_writer.py

from camel.storages import Neo4jGraph  # 借鉴 MedGraphRAG

class KGWriter:
    """
    Neo4j图谱写入器
    移植自 MedGraphRAG creat_graph_with_description.py → create_neo4j_nodes_and_relationships
    """
    
    def __init__(self, neo4j_url: str, neo4j_user: str, neo4j_password: str):
        self.n4j = Neo4jGraph(url=neo4j_url, username=neo4j_user, password=neo4j_password)
    
    def write_entities(self, entities: List[KGEntity], gid: str):
        """批量写入实体节点"""
        for entity in entities:
            query = """
            MERGE (n:%s {entity_id: $entity_id})
            SET n.entity_name = $name,
                n.entity_type = $type,
                n.description = $desc,
                n.layer = $layer,
                n.gid = $gid,
                n.hpo_id = $hpo_id,
                n.source_ref = $source_ref
            """ % entity.entity_type
            
            self.n4j.query(query, {
                'entity_id': entity.entity_id,
                'name': entity.entity_name,
                'type': entity.entity_type,
                'desc': entity.description,
                'layer': entity.layer.value,
                'gid': gid,
                'hpo_id': entity.hpo_id or '',
                'source_ref': entity.source_ref or '',
            })
    
    def write_relations(self, relations: List[KGRelation], gid: str):
        """批量写入关系边"""
        for rel in relations:
            # 动态关系类型 (借鉴 MedGraphRAG Cypher query 构建)
            query = """
            MATCH (a {entity_id: $src_id}), (b {entity_id: $tgt_id})
            MERGE (a)-[r:RELATED_TO {gid: $gid}]->(b)
            SET r.relation_type = $rel_type,
                r.description = $desc,
                r.strength = $strength,
                r.layer = $layer
            """
            self.n4j.query(query, {
                'src_id': rel.source_id,
                'tgt_id': rel.target_id,
                'gid': gid,
                'rel_type': rel.relation_type,
                'desc': rel.description,
                'strength': rel.strength,
                'layer': rel.layer.value,
            })
    
    def create_summary_node(self, content: str, gid: str):
        """创建Summary节点 (借鉴 MedGraphRAG 的 Graph↔Summary双节点设计)"""
        query = """
        CREATE (s:Summary {gid: $gid, content: $content, created_at: datetime()})
        RETURN s
        """
        self.n4j.query(query, {'gid': gid, 'content': content})
    
    def create_reference_link(self, source_gid: str, target_gid: str):
        """创建三层之间的REFERENCE关系 (移植 MedGraphRAG ref_link)"""
        query = """
        MATCH (s:Summary {gid: $src_gid})
        MATCH (t:Summary {gid: $tgt_gid})
        MERGE (s)-[r:REFERENCE]->(t)
        RETURN count(r) as count
        """
        result = self.n4j.query(query, {'src_gid': source_gid, 'tgt_gid': target_gid})
        return result[0]['count'] if result else 0
```

### 4.4 图谱后处理 — 节点合并与清理

```python
# core/kg/kg_cleaner.py

class KGCleaner:
    """
    图谱后处理器
    移植自 MedGraphRAG cleangraph.py → merge_similar_nodes + remove_isolated_nodes
    """
    
    def __init__(self, n4j: Neo4jGraph, llm_client):
        self.n4j = n4j
        self.llm = llm_client
    
    async def merge_similar_nodes(self, similarity_threshold: float = 0.85):
        """LLM辅助合并相似节点 (移植 MedGraphRAG merge_similar_nodes)"""
        # 查找同类型、名称相似的节点对
        query = """
        MATCH (n), (m)
        WHERE n.entity_type = m.entity_type
          AND n.entity_id < m.entity_id
          AND n.layer = m.layer
        RETURN n.entity_name as name1, n.entity_id as id1,
               m.entity_name as name2, m.entity_id as id2
        LIMIT 100
        """
        pairs = self.n4j.query(query)
        
        merge_count = 0
        for pair in pairs:
            # LLM 判断是否应合并 (借鉴 MedGraphRAG 的LLM相似度判断)
            prompt = f"""Are these two medical entities referring to the same concept?
Entity 1: {pair['name1']}
Entity 2: {pair['name2']}

Answer only YES or NO."""
            response = await self.llm.complete(prompt)
            
            if "YES" in response.upper():
                # 合并: 保留 id1, 将 id2 的所有关系迁移到 id1
                self._merge_nodes(pair['id1'], pair['id2'])
                merge_count += 1
        
        return merge_count
    
    def remove_isolated_nodes(self):
        """移除孤立节点 (移植 MedGraphRAG remove_isolated_nodes)"""
        query = """
        MATCH (n)
        WHERE NOT (n)--()
          AND NOT n:Summary
        DETACH DELETE n
        RETURN count(n) as deleted
        """
        result = self.n4j.query(query)
        return result[0]['deleted'] if result else 0
```

---

## 5. Phase 2: 知识图谱检索方案

### 5.1 级联检索管道

```python
# core/kg/kg_retriever.py

from pymilvus import MilvusClient
import numpy as np

class KGCascadeRetriever:
    """
    四级级联检索管道
    融合 MedGraphRAG (_op.py _build_local_query_context) +
         MedRAG (find_closest_category 最短路径投票)
    
    检索路径:
    Stage 1: Milvus COSINE → Top-K 候选实体
    Stage 2: Neo4j 1-hop 邻居 → 扩展关系边
    Stage 3: Cypher shortestPath → 疾病子类投票
    Stage 4: Token预算截断 → LLM上下文窗口
    """
    
    def __init__(self, n4j: Neo4jGraph, milvus: MilvusClient, embedder, config: dict):
        self.n4j = n4j
        self.milvus = milvus
        self.embedder = embedder
        self.top_k = config.get('top_k', 20)
        self.radius = config.get('radius', 0.2)  # MedGraphRAG COSINE阈值
        self.max_tokens = config.get('max_context_tokens', 4000)
    
    async def retrieve(self, patient_hpo_ids: list[str], 
                       lab_abnormalities: list[dict]) -> KGRetrievalResult:
        """主检索入口
        
        Args:
            patient_hpo_ids: 患者HPO ID列表 (已由hpo_extractor提取)
            lab_abnormalities: 异常检验 [{'name': 'Ceruloplasmin', 'value': 0.08, 'direction': 'low'}]
        
        Returns:
            KGRetrievalResult: 结构化检索结果
        """
        # === Stage 1: 向量检索 (借鉴 MedGraphRAG entities_vdb.query) ===
        query_text = self._build_query_text(patient_hpo_ids, lab_abnormalities)
        query_emb = await self.embedder.embed(query_text)
        
        # Milvus COSINE 搜索
        results = self.milvus.search(
            collection_name="kg_entities",
            data=[query_emb],
            limit=self.top_k,
            output_fields=["entity_name", "entity_type", "description", "layer"],
            search_params={"metric_type": "COSINE", "params": {"radius": self.radius}},
        )
        
        candidate_entities = [
            {'entity_name': r['entity']['entity_name'], 
             'distance': r['distance']}
            for r in results[0]
        ]
        
        # === Stage 2: 图扩展 (借鉴 MedGraphRAG 1-hop neighbor + edge_degree) ===
        expanded = await self._expand_graph(candidate_entities)
        
        # === Stage 3: 类别投票 (借鉴 MedRAG shortest_path 投票) ===
        disease_rankings = await self._category_vote(expanded['entity_names'])
        
        # === Stage 4: Token截断 (借鉴 MedGraphRAG truncate_list_by_token_size) ===
        context = self._truncate_context(expanded, disease_rankings)
        
        return KGRetrievalResult(
            candidate_diseases=disease_rankings,
            relevant_entities=context['entities'],
            relevant_relations=context['relations'],
            differential_features=await self._get_differential_features(disease_rankings),
            source_citations=context['citations'],
        )
    
    async def _expand_graph(self, entities: list[dict]) -> dict:
        """Stage 2: 1-hop邻居扩展 (借鉴 MedGraphRAG get_node_edges + edge_degree排序)"""
        entity_names = [e['entity_name'] for e in entities]
        
        # Cypher: 1-hop邻居 + 关系边
        query = """
        MATCH (n)-[r]-(m)
        WHERE n.entity_name IN $names
        RETURN n.entity_name as source, type(r) as rel_type,
               r.description as desc, r.strength as strength,
               m.entity_name as target, m.entity_type as target_type,
               m.description as target_desc,
               size(()-[]->(n)) + size(()-[]->(m)) as degree_sum
        ORDER BY degree_sum DESC, r.strength DESC
        LIMIT 50
        """
        results = self.n4j.query(query, {'names': entity_names})
        
        # 去重 + 组织
        seen_entities = set(entity_names)
        relations = []
        expanded_entities = []
        
        for r in results:
            if r['target'] not in seen_entities:
                seen_entities.add(r['target'])
                expanded_entities.append({
                    'name': r['target'],
                    'type': r['target_type'],
                    'description': r['target_desc'],
                    'degree': r['degree_sum'],
                })
            relations.append({
                'source': r['source'],
                'target': r['target'],
                'type': r['rel_type'],
                'description': r['desc'],
                'strength': r['strength'],
            })
        
        return {
            'entity_names': list(seen_entities),
            'expanded_entities': expanded_entities,
            'relations': relations,
        }
    
    async def _category_vote(self, entity_names: list[str]) -> list[dict]:
        """Stage 3: 最短路径投票 (借鉴 MedRAG find_closest_category)
        
        罕见肝病四大子类:
        - copper_metabolism: Wilson
        - autoimmune_liver: AIH, PBC
        - cholestatic: PSC
        - metabolic_iron: Hemochromatosis, Alpha-1
        """
        categories = [
            'copper_metabolism_disorder',
            'autoimmune_liver_disease',
            'cholestatic_liver_disease', 
            'metabolic_liver_disease',
        ]
        
        category_votes = {cat: 0.0 for cat in categories}
        
        for entity_name in entity_names:
            for cat in categories:
                # Cypher shortestPath
                query = """
                MATCH (start {entity_name: $entity}),
                      (end:LiverDiseaseCategory {category: $cat})
                WITH shortestPath((start)-[*]-(end)) as p
                RETURN length(p) as distance
                LIMIT 1
                """
                result = self.n4j.query(query, {'entity': entity_name, 'cat': cat})
                if result:
                    distance = result[0]['distance']
                    # 借鉴 MedRAG: 距离越短权重越高
                    category_votes[cat] += 1.0 / max(distance, 1)
        
        # 排序
        ranked = sorted(category_votes.items(), key=lambda x: x[1], reverse=True)
        return [
            {'category': cat, 'score': score}
            for cat, score in ranked if score > 0
        ]
```

### 5.2 统一查询API

```python
# core/kg/kg_interface.py

class KGInterface:
    """知识图谱统一查询接口 — 对接 LangGraph 工作流"""
    
    def __init__(self, retriever: KGCascadeRetriever, n4j: Neo4jGraph):
        self.retriever = retriever
        self.n4j = n4j
    
    async def query_by_hpo(self, hpo_ids: list[str]) -> KGRetrievalResult:
        """API 1: HPO→候选疾病查询 (L1/L2调用)"""
        return await self.retriever.retrieve(hpo_ids, [])
    
    async def query_differential(self, disease_a: str, disease_b: str) -> dict:
        """API 2: 诊断差异特征查询 (L3 MDT辩论调用)"""
        query = """
        MATCH (a:Disease {entity_name: $disease_a})-[r1:has_phenotype]->(p:Phenotype)
        WHERE NOT EXISTS {
            MATCH (b:Disease {entity_name: $disease_b})-[r2:has_phenotype]->(p)
        }
        RETURN p.entity_name as unique_feature, p.description as description
        LIMIT 10
        """
        a_unique = self.n4j.query(query, {'disease_a': disease_a, 'disease_b': disease_b})
        
        # 交换查询B的独特特征
        b_unique = self.n4j.query(query, {'disease_a': disease_b, 'disease_b': disease_a})
        
        return {
            f'{disease_a}_unique': a_unique,
            f'{disease_b}_unique': b_unique,
        }
    
    async def query_lab_disease(self, lab_name: str, direction: str) -> list[dict]:
        """API 3: 异常检验→疾病关联 (L1调用)"""
        query = """
        MATCH (d:Disease)-[r:has_lab_abnormality]->(l:LabTest {entity_name: $lab})
        WHERE r.direction = $direction
        RETURN d.entity_name as disease, r.description as evidence
        """
        return self.n4j.query(query, {'lab': lab_name.upper(), 'direction': direction})
    
    async def recommend_questions(self, hpo_ids: list[str], max_q: int = 3) -> list[str]:
        """API 4: 主动追问推荐 (L2 IntelligentTriage调用)"""
        # 先用HPO定位候选疾病子类
        result = await self.retriever.retrieve(hpo_ids, [])
        
        # 检索子类下的L4诊断差异节点
        questions = []
        for disease in result.candidate_diseases[:2]:
            query = """
            MATCH (d:Disease {entity_name: $disease})-[r:diagnosed_by]->(t)
            WHERE t.entity_type IN ['LabTest', 'Imaging', 'Phenotype']
            RETURN t.entity_name as test, r.description as rationale
            LIMIT 3
            """
            tests = self.n4j.query(query, {'disease': disease['category']})
            for t in tests:
                questions.append(f"请确认是否存在: {t['test']}（{t['rationale']}）")
        
        return questions[:max_q]
```

---

## 6. 关键算法实现

### 6.1 LLM缓存算法（移植 MedGraphRAG）

```python
# core/kg_cache.py

import hashlib
import json
import os
from typing import Optional

class LLMCache:
    """
    LLM调用缓存
    移植自 MedGraphRAG nano_graphrag/_llm.py → openai_complete_if_cache
    
    策略:
    - 基于 (model + prompt hash) 生成缓存键
    - JSON文件持久化
    - TTL = 7天 (医学知识短期不变)
    """
    
    def __init__(self, cache_dir: str = ".kg_cache", ttl_days: int = 7):
        self.cache_dir = cache_dir
        self.ttl_seconds = ttl_days * 86400
        os.makedirs(cache_dir, exist_ok=True)
    
    def _cache_key(self, model: str, prompt: str) -> str:
        content = f"{model}|{prompt[:500]}"  # 截断长prompt
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    async def get(self, key: str) -> Optional[dict]:
        cache_file = os.path.join(self.cache_dir, f"{key}.json")
        if os.path.exists(cache_file):
            data = json.load(open(cache_file))
            # TTL 检查
            import time
            if time.time() - data['timestamp'] < self.ttl_seconds:
                return data['value']
        return None
    
    async def set(self, key: str, value):
        cache_file = os.path.join(self.cache_dir, f"{key}.json")
        import time
        json.dump({'timestamp': time.time(), 'value': value}, open(cache_file, 'w'))
```

### 6.2 Token预算截断算法（移植 MedGraphRAG）

```python
# core/kg/kg_retriever.py (continuation)

def truncate_list_by_token_size(
    items: list[dict],
    key: callable,
    max_token_size: int,
    model: str = "qwen-plus",
) -> list[dict]:
    """
    按Token预算截断结果列表
    移植自 MedGraphRAG nano_graphrag/_utils.py
    
    确保检索结果的总token数不超过LLM上下文窗口限制
    """
    result = []
    current_tokens = 0
    
    # 粗略估计: 1 token ≈ 0.75 中文字符, ≈ 2.5 英文字符
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

### 6.3 嵌入向量批量生成与持久化

```python
# core/kg/kg_embedder.py

import numpy as np
from sentence_transformers import SentenceTransformer

class KGEmbedder:
    """
    KG嵌入生成器
    借鉴 MedRAG 的嵌入预计算+持久化策略 (KG_Retrieve.py:L63-L79)
    使用 BGE-M3 替代 text-embedding-3-large (对中文医学文本更优)
    """
    
    def __init__(self, model_name: str = "BAAI/bge-m3", cache_dir: str = ".kg_embeddings"):
        self.model = SentenceTransformer(model_name)
        self.cache_dir = cache_dir
        self.dim = 1024  # BGE-M3 输出维度
        os.makedirs(cache_dir, exist_ok=True)
    
    def generate_embeddings(self, texts: list[str], namespace: str) -> np.ndarray:
        """生成嵌入向量并持久化"""
        cache_path = os.path.join(self.cache_dir, f"{namespace}_embeddings.npy")
        
        # 检查缓存 (借鉴 MedRAG load_embeddings)
        if os.path.exists(cache_path):
            return np.load(cache_path)
        
        # 批量生成
        embeddings = self.model.encode(
            texts,
            batch_size=32,
            show_progress_bar=True,
            normalize_embeddings=True,  # 归一化 → COSINE = Inner Product
        )
        
        # 持久化
        np.save(cache_path, embeddings)
        return embeddings
    
    async def embed(self, text: str) -> list[float]:
        """单文本嵌入"""
        embedding = self.model.encode(
            [text],
            normalize_embeddings=True,
        )
        return embedding[0].tolist()
```

---

## 7. 性能优化策略

### 7.1 构建阶段优化

| 优化项 | 技术方案 | 来源 | 预期效果 |
|--------|---------|------|---------|
| **LLM调用缓存** | SHA256(prompt)→JSON文件缓存 + 7天TTL | MedGraphRAG `openai_complete_if_cache` | 重复文本零LLM调用；构建时间减少40-60% |
| **批量嵌入生成** | SentenceTransformer batch_size=32, normalize | MedRAG embedding预计算 | 嵌入生成吞吐 ~200 text/s |
| **输入截断** | text[:3000] + 后期补全循环 | MedGraphRAG prompt截断 | 长指南PDF ↔ 单次LLM调用 < 3秒 |
| **增量更新** | Δ diff: 仅重新处理变更文件 + MERGE (幂等写入) | — | 指南更新 ↔ 仅重建受影响子图 |
| **并发Neo4j写入** | asyncio.gather 并发写入独立子图 | MedGraphRAG ThreeLayerImporter | 三层层层并行导入 |
| **GPU嵌入生成** | BGE-M3 on CUDA | — | 嵌入生成速度 10x vs CPU |

### 7.2 检索阶段优化

| 优化项 | 技术方案 | 来源 | 预期延迟 |
|--------|---------|------|---------|
| **Milvus向量索引** | IVF_FLAT + nlist=128 (已配置Milvus) | MedGraphRAG MilvusLiteStorge | < 30ms (P95) |
| **预计算嵌入** | 患者HPO terms→嵌入后缓存60分钟 | MedRAG预计算模式 | 重复查询零嵌入生成 |
| **Neo4j查询缓存** | Cypher → LRU cache (最近100个查询) | — | 高频查询 < 5ms |
| **shortestPath剪枝** | maxDepth=5 + 缓存子图 | — | 单次投票 < 20ms |
| **渐进式检索** | Stage 1(向量) → Stage 2(图) → Stage 3(投票) | MedGraphRAG级联 + MedRAG投票 | 逐级缩小候选空间 |
| **异步检索** | async/await 并发执行 Stg1+Stg2+Stg3 | MedGraphRAG asyncio.gather | 三阶段总延迟近似 max(各阶段) |

### 7.3 目标性能指标

| 指标 | 目标值 | 测量方法 |
|------|--------|---------|
| 端到端检索延迟 (P95) | < 200ms | `time.perf_counter()` |
| 向量检索 (Stage 1) | < 30ms | Milvus search latency |
| 图扩展 (Stage 2) | < 50ms | Neo4j query profiling |
| 类别投票 (Stage 3) | < 30ms | Cypher shortestPath profiling |
| 上下文截断 (Stage 4) | < 5ms | Python truncate 耗时 |
| Top-5 疾病召回率 | > 85% | 金标准病例集测试 |

---

## 8. 与现有系统集成方案

### 8.1 LangGraph 工作流集成点

```
当前工作流节点               KG接口调用                    数据注入
─────────────────────────────────────────────────────────────────
L1: _node_preprocessing()  → kg_interface.query_lab_disease() → patient_data
                                (异常检验→疾病关联)
L1: _extract_hpo_terms()   → (HPO提取结果 → _node_triage 传递)

L2: _node_triage()         → kg_interface.recommend_questions() → triage_result
     IntelligentTriage        (HPO→追问推荐)
   
L2: _node_followup()       → kg_interface.query_by_hpo()       → patient_context
                                (HPO→候选疾病初筛)

L3: _node_mdt_debate()     → kg_interface.query_differential() → agent_prompt
     _build_agent_prompt()     (疾病A vs B的差异特征)
                              kg_interface.query_by_hpo()
                                (HPO→扩展证据链)

L4: _node_knowledge()      → kg_retriever.retrieve()          → 替代当前
     knowledge_retriever       (完整级联检索管道)               knowledge_retriever

L5: _node_generate_report()→ kg_interface.query_differential() → report
                                (差异特征→鉴别诊断描述)
```

### 8.2 State 扩展

```python
# core/state_definition.py 新增字段

class KGRetrievalResult(TypedDict):
    """KG检索结果"""
    candidate_diseases: list[dict]     # [{'category': str, 'score': float}]
    relevant_entities: list[dict]      # 相关实体
    relevant_relations: list[dict]     # 相关关系
    differential_features: dict        # 诊断差异特征
    source_citations: list[str]        # 来源引用

class DiagnosticState(TypedDict):
    # ... 现有字段 ...
    
    # 新增 KG 相关字段
    kg_retrieval_result: Annotated[Optional[KGRetrievalResult], operator.set]
    kg_question_recommendations: Annotated[list[str], operator.add]
```

### 8.3 降级策略

```python
# core/kg/kg_interface.py

class KGInterface:
    async def retrieve_with_fallback(self, *args, **kwargs) -> KGRetrievalResult:
        """带降级的检索 — Neo4j不可用时回退到Milvus纯向量检索"""
        try:
            return await self.retriever.retrieve(*args, **kwargs)
        except Neo4jConnectionError:
            logger.warning("Neo4j unavailable, falling back to Milvus-only retrieval")
            return await self._milvus_only_retrieve(*args, **kwargs)
        except Exception as e:
            logger.error(f"KG retrieval failed: {e}, falling back to text retrieval")
            return await self._text_fallback_retrieve(*args, **kwargs)
    
    async def _milvus_only_retrieve(self, hpo_ids, lab_abnormalities):
        """降级: 仅使用 Milvus 向量检索 (无图遍历)"""
        # ... 只执行 Stage 1 向量检索 ...
        pass
    
    async def _text_fallback_retrieve(self, *args, **kwargs):
        """最终降级: 回退到原有 knowledge_retriever 文本检索"""
        # 调用原有 knowledge_retriever 逻辑
        pass
```

---

## 9. 实施路线图

```
Week 1-2: 基础设施搭建
├── Day 1-2: 部署 Neo4j + 配置 Milvus collection
├── Day 3-4: 移植 kg_chunker.py (AgenticChunker)
├── Day 5-6: 移植 kg_extractor.py (LLM实体/关系提取)
├── Day 7-8: 移植 kg_writer.py (Neo4j写入)
├── Day 9-10: 实现 kg_cache.py + kg_embedder.py
└── Day 11-14: 实现 kg_cleaner.py + 端到端构建脚本

Week 3-4: 检索管道实现
├── Day 1-3: 实现 kg_retriever.py (四级级联检索管道)
├── Day 4-5: 实现 kg_classifier.py (最短路径投票)
├── Day 6-7: 实现 kg_interface.py (统一查询API + 降级策略)
├── Day 8-10: 编写单元测试 + 集成测试
└── Day 11-14: 与 LangGraph 工作流集成 + 端到端测试

Week 5-6: 数据灌入与调优
├── Day 1-3: YAML规则 → L_user 层导入
├── Day 4-6: 指南PDF → L_source 层导入
├── Day 7-8: HPO .obo → L_vocab 层导入
├── Day 9-11: 性能调优 (索引参数/缓存策略/并发)
└── Day 12-14: A/B 对比测试 (KG检索 vs 纯文本检索)
```

---

## 依赖性说明

```
kg_chunker.py  ← (独立, 无内部依赖)
kg_cache.py    ← (独立, 无内部依赖)
kg_extractor.py ← kg_cache.py (LLM缓存)
kg_writer.py    ← kg_schema.py
kg_embedder.py  ← (独立, 仅依赖 sentence-transformers)
kg_cleaner.py   ← kg_writer.py
kg_retriever.py ← kg_embedder.py + kg_writer.py
kg_classifier.py ← kg_writer.py
kg_interface.py ← kg_retriever.py + kg_classifier.py + state_definition.py
```

---

*本方案基于对 MedGraphRAG 和 MedRAG 两个开源仓库的完整代码分析，提取了 6 个核心可复用组件和 2 套检索策略，设计了 8 个适配模块。所有核心代码（实体提取器、分块器、级联检索器）均可直接移植，改造点仅在于：领域自适应（肝病实体类型）、LLM API 适配（通义千问）、嵌入模型替换（BGE-M3）。*