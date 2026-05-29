# 知识图谱构建与检索适配方案

> **版本**: v1.0  
> **日期**: 2026-05-07  
> **基于**: MedGraphRAG (ImprintLab) + MedRAG (SNOWTEAM2023) 代码仓库深度分析  
> **适配目标**: Rare-Hepatic-Disease-Multi-Agent-System

---

## 一、两个仓库核心技术方案对比

### 1.1 图谱构建对比

| 维度 | MedGraphRAG (P5) | MedRAG (P3) | 当前系统适配选择 |
|------|------------------|-------------|-----------------|
| **数据源** | 非结构化文本（病历、指南、词典） | 半结构化Excel（DDXPlus三元组） | ✅ 结构化YAML + 半结构化PDF + HPO本体 |
| **实体识别** | LLM抽取 + Gleaning补充 + 正则解析 | Excel预定义（无LLM抽取） | ✅ LLM抽取(PDF) + 规则提取(YAML) + 本体映射(HPO) |
| **关系抽取** | LLM抽取 + 关键词推断(TREATS/CAUSES等) | Excel预定义(is_a/has_keyinfo/症状关系) | ✅ LLM抽取(鉴别特征) + 预定义关系(8种) |
| **层级结构** | 三层(Bottom词典/Middle指南/Top病例) | 四层(EL1大类/EL2亚类/EL3疾病/EL4特征) | ✅ 融合: 三层分离 + 四层诊断KG |
| **跨层链接** | REFERENCE关系(embedding余弦>0.6) | is_a层次关系 + 症状关系 | ✅ Triple Linking + is_a + contradicts |
| **节点合并** | GDS余弦相似度>0.5/0.6 + apoc.mergeNodes | 无（预定义无重复） | ✅ 疾病名称聚类 + 人工审核 |
| **存储** | Neo4j + NetworkX + Milvus | NetworkX + Excel | ✅ NetworkX(开发) → Neo4j(生产) |
| **社区检测** | Leiden层次聚类 | 无 | ❌ 不需要（节点<500，社区检测无意义） |

### 1.2 图谱检索对比

| 维度 | MedGraphRAG (P5) | MedRAG (P3) | 当前系统适配选择 |
|------|------------------|-------------|-----------------|
| **检索策略** | U-Retrieval(Top→Middle→Bottom→Middle→Top) | Bottom-up(EL4→EL3→EL1投票) | ✅ U-Retrieval + Bottom-up融合 |
| **子图定位** | LLM逐一比较Summary | 最短路径投票 | ✅ 嵌入相似度 + 分诊提示(Top-down) |
| **特征匹配** | Summary节点语义匹配 | 嵌入cosine相似度>0.5 | ✅ 嵌入匹配 + 规则字段匹配(双路径) |
| **差异检索** | 无 | has_keyinfo + 三元组合并 | ✅ differential_from边 + contradicts边 |
| **结果排序** | LLM评分(0-4分) | 投票数排序 | ✅ 激活分数(嵌入权重×IC值) |
| **LLM生成** | 两阶段(子图内→跨层精炼) | 单阶段(q+d_r+K→A) | ✅ 两阶段(子图内检索→差异KG精炼) |
| **EHR检索** | 无 | FAISS IndexFlatIP | ❌ 暂不需要(无大量病例) |

### 1.3 适配决策矩阵

```
┌──────────────────────────────────────────────────────────────────────┐
│                    技术方案适配决策                                     │
│                                                                      │
│  来自MedGraphRAG(P5):                                                │
│  ✅ 三层图分离架构 (Bottom/Middle/Top → 本体/文献/患者)               │
│  ✅ U-Retrieval检索策略 (Top-down + Bottom-up + 跨层引用)            │
│  ✅ REFERENCE跨层链接 (embedding余弦相似度)                           │
│  ✅ 两阶段LLM生成 (子图内→跨层精炼)                                  │
│  ✅ Triple Linking ([entity, source, definition])                    │
│  ✅ Entity Gleaning (LLM补充抽取)                                    │
│  ❌ Leiden社区检测 (节点<500不需要)                                   │
│  ❌ Agentic Chunking (无大量非结构化文本)                             │
│  ❌ LLM逐一比较Summary (效率低，改用嵌入)                             │
│                                                                      │
│  来自MedRAG(P3):                                                     │
│  ✅ 四层诊断KG (EL1→EL4)                                             │
│  ✅ Bottom-up投票机制 (EL4→EL3→EL1)                                  │
│  ✅ 诊断差异KG (同EL2下疾病鉴别特征提取)                              │
│  ✅ 可辨识度评分 σ(e) = (n-1)/deg(e)                                 │
│  ✅ 三元组合并生成自然语言 (subject relation obj1, obj2)              │
│  ✅ 表征分解 (多维度特征分别匹配)                                     │
│  ❌ FAISS EHR检索 (无大量病例)                                        │
│  ❌ text-embedding-3-large (改用BGE-M3本地模型)                      │
│  ❌ 固定相似度阈值0.5 (改用自适应阈值)                                │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 二、知识图谱构建方案

### 2.1 整体架构：三层分离 + 四层诊断KG

融合MedGraphRAG的三层分离和MedRAG的四层诊断KG：

```
┌──────────────────────────────────────────────────────────────────────┐
│              三层分离 + 四层诊断KG 融合架构                            │
│                                                                      │
│  Layer 3: 本体层 (Ontology) — 固定 [参考P5 Bottom层]                 │
│  ┌────────────────────────────────────────────────────────────┐     │
│  │  HPO本体 (hp.obo)                                          │     │
│  │  ├── 表型层级树 (is_a关系)                                  │     │
│  │  ├── IC值预计算 (phenotype.hpoa)                            │     │
│  │  └── 标准术语定义 (name + definition + synonyms)            │     │
│  │                                                            │     │
│  │  存储: NetworkX只读图 + JSON缓存                            │     │
│  └────────────────────────────────────────────────────────────┘     │
│                          │ Triple Linking (HPO ID)                  │
│                          ▼                                         │
│  Layer 2: 文献层 (Literature) — 固定 [参考P5 Middle层 + P3四层KG]   │
│  ┌────────────────────────────────────────────────────────────┐     │
│  │  四层诊断KG                                                 │     │
│  │  ├── EL1: 疾病大类 (代谢性/自身免疫性/遗传性/胆汁淤积/获得性) │     │
│  │  ├── EL2: 疾病亚类 (铜代谢/铁代谢/蛋白代谢/...)              │     │
│  │  ├── EL3: 具体疾病 (Wilson/AIH/血色病/PBC/...)              │     │
│  │  └── EL4: 诊断特征                                          │     │
│  │       ├── EL4d: 结构化特征 (检验阈值/症状/影像)              │     │
│  │       └── EL4a: 鉴别特征 (LLM增强, 参考P3 has_keyinfo)      │     │
│  │                                                            │     │
│  │  关系类型 (8种):                                            │     │
│  │  is_a | has_manifestation | has_diagnostic_key              │     │
│  │  differential_from | contradicts | associated_gene          │     │
│  │  guided_by | synonym_of                                     │     │
│  │                                                            │     │
│  │  存储: NetworkX(开发) → Neo4j(生产)                         │     │
│  └────────────────────────────────────────────────────────────┘     │
│                          │ Triple Linking (field→patient_data)      │
│                          ▼                                         │
│  Layer 1: 患者数据层 (User Data) — 动态 [参考P5 Top层]              │
│  ┌────────────────────────────────────────────────────────────┐     │
│  │  当前诊断会话状态 (DiagnosticState)                          │     │
│  │  ├── hypotheses (假设列表 + confidence)                     │     │
│  │  ├── excluded_hypotheses (已排除假设)                       │     │
│  │  ├── graph_activation (KG激活结果)                          │     │
│  │  └── patient_data (患者原始数据)                            │     │
│  │                                                            │     │
│  │  存储: LangGraph State (内存, 会话级)                       │     │
│  └────────────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.2 数据提取流程

#### 2.2.1 多源数据提取管道

```
┌─────────────────────────────────────────────────────────────────────┐
│                    数据提取管道（参考P5+P3融合）                      │
│                                                                     │
│  数据源A: YAML规则 (结构化)                                          │
│  ┌──────────────────┐                                               │
│  │ rare_diseases.yaml│──→ 规则解析器 ──→ EL3疾病 + EL4d特征          │
│  │ common_diseases.yaml│   (字段: name, core_rules, supporting_rules)│
│  └──────────────────┘                                               │
│         │                                                           │
│         │ 合并去重 (Wilson病6处→1处)                                 │
│         ▼                                                           │
│  数据源B: 内置数据库 (结构化)                                        │
│  ┌──────────────────┐                                               │
│  │ rare_disease_db   │──→ 数据提取器 ──→ EL3元数据 + EL4d补充       │
│  │ guideline_search  │   (orpha_id, omim_id, gene, key_symptoms)    │
│  │ evidence_chain    │                                               │
│  │ reflection_engine │                                               │
│  └──────────────────┘                                               │
│         │                                                           │
│         │ 阈值冲突解决 (以source.original_text为准)                  │
│         ▼                                                           │
│  数据源C: PDF指南 (非结构化) [参考P5 LLM抽取]                       │
│  ┌──────────────────┐                                               │
│  │ AASLD/EASL指南PDF │──→ PyMuPDF解析 ──→ 章节分割                  │
│  └──────────────────┘       │                                       │
│                             ▼                                       │
│                      LLM结构化提取 [参考P5 entity_extraction]        │
│                      ├── 首次抽取 (entity + relationship)           │
│                      ├── Gleaning补充 (1轮) [参考P5 Gleaning]       │
│                      └── 自动验证 (ExtractionValidator)             │
│                             │                                       │
│                             ▼                                       │
│                      EL4a鉴别特征 + guided_by关系 + 指南引用         │
│         │                                                           │
│         │ Triple Linking关联                                        │
│         ▼                                                           │
│  数据源D: HPO本体 (标准) [参考P3 EL4预处理]                          │
│  ┌──────────────────┐                                               │
│  │ hp.obo            │──→ obonet加载 ──→ 表型层级树 + IC值          │
│  │ phenotype.hpoa    │   (preprocess_text: 去括号/下划线/标点)       │
│  └──────────────────┘                                               │
│                                                                     │
│  最终产出: 统一JSON (兼容Neo4j CSV导入格式)                          │
└─────────────────────────────────────────────────────────────────────┘
```

#### 2.2.2 LLM实体抽取实现（参考P5 nano-graphrag）

```python
class MedicalEntityExtractor:
    """医学实体抽取器（参考MedGraphRAG entity_extraction + Gleaning）"""

    ENTITY_TYPES = [
        "Disease", "Symptom", "LabFinding", "ImagingFinding",
        "Gene", "Medication", "DiagnosticCriteria", "ClinicalGuideline"
    ]

    TUPLE_DELIMITER = "<|>"
    RECORD_DELIMITER = "##"
    COMPLETION_MARKER = "<|COMPLETE|>"

    def __init__(self, llm_client, max_gleaning: int = 1):
        self.llm = llm_client
        self.max_gleaning = max_gleaning

    async def extract(self, text: str, source_id: str) -> Dict:
        entities = []
        relationships = []

        prompt = self._build_extraction_prompt(text)
        result = await self._call_llm(prompt)
        parsed = self._parse_result(result)
        entities.extend(parsed["entities"])
        relationships.extend(parsed["relationships"])

        for _ in range(self.max_gleaning):
            continue_prompt = self._build_gleaning_prompt(result)
            glean_result = await self._call_llm(continue_prompt)
            glean_parsed = self._parse_result(glean_result)
            entities.extend(glean_parsed["entities"])
            relationships.extend(glean_parsed["relationships"])

            loop_prompt = self._build_loop_prompt(glean_result)
            loop_result = await self._call_llm(loop_prompt)
            if "NO" in loop_result.upper():
                break
            result = glean_result

        return {
            "source_id": source_id,
            "entities": self._merge_entities(entities),
            "relationships": self._merge_relationships(relationships)
        }

    def _build_extraction_prompt(self, text: str) -> str:
        return f"""-Goal-
Given a medical text document about liver disease, identify all entities and relationships.

-Entity Types-
{', '.join(self.ENTITY_TYPES)}

-Steps-
1. Identify all entities from the text using this format:
("entity"{self.TUPLE_DELIMITER}<entity_name>{self.TUPLE_DELIMITER}<entity_type>{self.TUPLE_DELIMITER}<entity_description>)
2. Identify all relationships between entities:
("relationship"{self.TUPLE_DELIMITER}<source_entity>{self.TUPLE_DELIMITER}<target_entity>{self.TUPLE_DELIMITER}<relationship_description>{self.TUPLE_DELIMITER}<relationship_strength:STRONG|MODERATE|WEAK>)
3. For diagnostic criteria, preserve exact numerical thresholds and units.
4. Return output using {self.RECORD_DELIMITER} as delimiter between records.
5. When finished, output {self.COMPLETION_MARKER}

-Real Data-
Text: {text}
Output:"""

    def _parse_result(self, result: str) -> Dict:
        entities = []
        relationships = []
        for record in result.split(self.RECORD_DELIMITER):
            record = record.strip()
            if self.COMPLETION_MARKER in record:
                break
            parts = [p.strip() for p in record.split(self.TUPLE_DELIMITER)]
            if len(parts) >= 4 and parts[0] == '"entity"':
                entities.append({
                    "name": parts[1].strip('"'),
                    "type": parts[2].strip('"'),
                    "description": parts[3].strip('"')
                })
            elif len(parts) >= 5 and parts[0] == '"relationship"':
                relationships.append({
                    "source": parts[1].strip('"'),
                    "target": parts[2].strip('"'),
                    "description": parts[3].strip('"'),
                    "strength": parts[4].strip('"')
                })
        return {"entities": entities, "relationships": relationships}

    def _merge_entities(self, entities: List[Dict]) -> List[Dict]:
        merged = {}
        for e in entities:
            key = (e["name"].lower(), e["type"])
            if key in merged:
                merged[key]["description"] += f" <SEP> {e['description']}"
            else:
                merged[key] = e.copy()
        return list(merged.values())
```

#### 2.2.3 诊断差异KG构建（参考P3 MedRAG）

```python
class DiagnosticDifferenceBuilder:
    """诊断差异KG构建器（参考MedRAG has_keyinfo + 三元组合并）"""

    def build(self, kg: nx.DiGraph) -> List[Dict]:
        diffs = []
        l2_nodes = [n for n, d in kg.nodes(data=True) if d.get("layer") == "EL2"]

        for l2 in l2_nodes:
            l3_children = list(kg.successors(l2))
            if len(l3_children) < 2:
                continue

            for i, d1 in enumerate(l3_children):
                for d2 in l3_children[i + 1:]:
                    diff = self._compute_pairwise_diff(kg, d1, d2, l2)
                    if diff["discriminability_score"] > 0:
                        diffs.append(diff)
                        kg.add_edge(d1, d2, relation="differential_from",
                                    key_features=diff["key_features"],
                                    difficulty=diff["difficulty"])

        return diffs

    def _compute_pairwise_diff(self, kg: nx.DiGraph, d1: str, d2: str, l2: str) -> Dict:
        features_d1 = self._get_features(kg, d1)
        features_d2 = self._get_features(kg, d2)

        d1_fields = {v["field"]: v for v in features_d1.values() if "field" in v}
        d2_fields = {v["field"]: v for v in features_d2.values() if "field" in v}

        shared = set(d1_fields.keys()) & set(d2_fields.keys())
        direction_diffs = []
        for field in shared:
            d1_dir = d1_fields[field].get("direction", "")
            d2_dir = d2_fields[field].get("direction", "")
            if d1_dir != d2_dir:
                direction_diffs.append({
                    "field": field,
                    "d1_direction": d1_dir,
                    "d2_direction": d2_dir,
                    "discriminability": "high"
                })

        unique_d1 = set(d1_fields.keys()) - set(d2_fields.keys())
        unique_d2 = set(d2_fields.keys()) - set(d1_fields.keys())

        key_features = []
        for dd in direction_diffs:
            key_features.append(f"{dd['field']}: {dd['d1_direction']} vs {dd['d2_direction']}")
        for f in unique_d1:
            key_features.append(f"{f}: 仅{kg.nodes[d1].get('name', d1)}")
        for f in unique_d2:
            key_features.append(f"{f}: 仅{kg.nodes[d2].get('name', d2)}")

        score = len(unique_d1) + len(unique_d2) + len(direction_diffs) * 2
        difficulty = "easy" if score >= 4 else "moderate" if score >= 2 else "hard"

        return {
            "disease_pair": [d1, d2],
            "parent_l2": l2,
            "unique_to_d1": list(unique_d1),
            "unique_to_d2": list(unique_d2),
            "shared_with_direction_diff": direction_diffs,
            "key_features": key_features,
            "discriminability_score": score,
            "difficulty": difficulty
        }

    def _get_features(self, kg: nx.DiGraph, disease: str) -> Dict:
        features = {}
        for successor in kg.successors(disease):
            edge_data = kg.get_edge_data(disease, successor)
            if edge_data and edge_data.get("relation") in ("has_manifestation", "has_diagnostic_key"):
                features[successor] = kg.nodes[successor]
        return features
```

### 2.3 图谱存储结构

#### 2.3.1 NetworkX存储（开发阶段）

```python
class LayeredDiagnosticKG:
    """三层分离的诊断知识图谱"""

    def __init__(self):
        self.ontology_graph = nx.DiGraph()
        self.literature_graph = nx.DiGraph()
        self.cross_layer_links = []
        self._l4_embedding_index = None
        self._l4_ids = None
        self._l4_embeddings = None

    def save(self, path: str) -> None:
        nx.write_graphml(self.ontology_graph, f"{path}/ontology.graphml")
        nx.write_graphml(self.literature_graph, f"{path}/literature.graphml")
        with open(f"{path}/cross_links.json", "w") as f:
            json.dump(self.cross_layer_links, f, ensure_ascii=False, indent=2)

    def load(self, path: str) -> None:
        self.ontology_graph = nx.read_graphml(f"{path}/ontology.graphml")
        self.literature_graph = nx.read_graphml(f"{path}/literature.graphml")
        with open(f"{path}/cross_links.json", "r") as f:
            self.cross_layer_links = json.load(f)

    def export_neo4j_csv(self, output_dir: str) -> None:
        import csv
        G = self.literature_graph
        with open(f"{output_dir}/nodes.csv", "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["id:ID", "layer", "name", "hpo_id", "ic_value",
                             "field", "direction", "threshold", "unit", ":LABEL"])
            for node, data in G.nodes(data=True):
                writer.writerow([
                    node, data.get("layer", ""), data.get("name", ""),
                    data.get("hpo_id", ""), data.get("ic_value", ""),
                    data.get("field", ""), data.get("direction", ""),
                    data.get("threshold", ""), data.get("unit", ""),
                    data.get("layer", "Unknown")
                ])

        with open(f"{output_dir}/edges.csv", "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([":START_ID", ":END_ID", "relation",
                             "is_core", "score", "strength", ":TYPE"])
            for u, v, data in G.edges(data=True):
                writer.writerow([
                    u, v, data.get("relation", ""),
                    data.get("is_core", ""), data.get("score", ""),
                    data.get("strength", ""), data.get("relation", "")
                ])
```

#### 2.3.2 Neo4j存储（生产阶段）

参考MedGraphRAG的Neo4j schema设计：

```cypher
-- 约束与索引
CREATE CONSTRAINT entity_id IF NOT EXISTS
FOR (n:Entity) REQUIRE n.id IS UNIQUE;

CREATE INDEX entity_layer IF NOT EXISTS
FOR (n:Entity) ON (n.layer);

CREATE INDEX entity_hpo IF NOT EXISTS
FOR (n:Entity) ON (n.hpo_id);

CREATE INDEX entity_gid IF NOT EXISTS
FOR (n:Entity) ON (n.gid);

-- 节点导入
UNWIND $data AS row
MERGE (n:Entity {id: row.id})
ON CREATE SET n.layer = row.layer, n.name = row.name,
              n.hpo_id = row.hpo_id, n.ic_value = row.ic_value,
              n.field = row.field, n.direction = row.direction,
              n.threshold = row.threshold, n.unit = row.unit,
              n.gid = row.gid, n.embedding = row.embedding
WITH n, row
CALL apoc.create.addLabels(n, [row.layer]) YIELD node
RETURN count(*)

-- 关系导入
UNWIND $data AS row
MATCH (a:Entity {id: row.source})
MATCH (b:Entity {id: row.target})
CALL apoc.create.relationship(a, row.relation, {
    is_core: row.is_core, score: row.score, strength: row.strength
}, b) YIELD rel
RETURN count(*)

-- 跨层REFERENCE链接（参考P5 ref_link）
MATCH (a:Entity) WHERE a.gid = $gid1 AND a.layer = 'EL4d'
WITH collect(a) AS GraphA
MATCH (b:Entity) WHERE a.gid = $gid2 AND b.layer STARTS WITH 'HP'
WITH GraphA, collect(b) AS GraphB
UNWIND GraphA AS n UNWIND GraphB AS m
WITH n, m, gds.similarity.cosine(n.embedding, m.embedding) AS sim
WHERE sim > 0.6
MERGE (n)-[:REFERENCE]->(m)
```

---

## 三、知识图谱检索方案

### 3.1 U-Retrieval + Bottom-up 融合检索

融合MedGraphRAG的U-Retrieval和MedRAG的Bottom-up投票机制：

```
┌──────────────────────────────────────────────────────────────────────┐
│           U-Retrieval + Bottom-up 融合检索流程                        │
│                                                                      │
│  输入: 患者数据 + 分诊提示                                           │
│    │                                                                 │
│    ├── [Top-down路径] (参考P5 U-Retrieval Step 2)                    │
│    │   分诊提示 → 映射到EL2亚类 → 缩小EL3候选范围                    │
│    │   例: "rare_metabolic" → copper_metabolism → [Wilson, 血色病]   │
│    │                                                                 │
│    ├── [Bottom-up路径] (参考P3 find_closest_category)                │
│    │   患者特征 → 嵌入匹配EL4d → 沿边找到EL3 → 投票确定EL2          │
│    │   例: "铜蓝蛋白↓" → EL4d匹配 → Wilson病(3票) → 代谢性肝病     │
│    │                                                                 │
│    └── [交叉验证]                                                    │
│        Top-down ∩ Bottom-up → 确定候选EL3疾病集合                   │
│        若交集为空 → 以Bottom-up为准（分诊可能误判）                  │
│    │                                                                 │
│    ▼                                                                 │
│  [子图内检索] (参考P5 ret_context)                                   │
│    提取候选EL3疾病的所有EL4特征三元组                                │
│    格式: "Wilson病 has_manifestation 铜蓝蛋白↓(核心)"                │
│    │                                                                 │
│    ▼                                                                 │
│  [差异KG检索] (参考P3 get_additional_info_from_level_2)              │
│    提取同EL2下候选疾病的differential_from边                          │
│    合并三元组: "Wilson病 铜蓝蛋白↓, 血色病 铁蛋白↑"                  │
│    │                                                                 │
│    ▼                                                                 │
│  [跨层引用] (参考P5 link_context)                                    │
│    EL4d → REFERENCE → HPO本体定义                                    │
│    EL3 → guided_by → 指南引用                                        │
│    │                                                                 │
│    ▼                                                                 │
│  [两阶段LLM生成] (参考P5 get_response)                               │
│    阶段一: 子图内上下文 + 差异KG → 初步诊断推理                      │
│    阶段二: 跨层引用(指南+HPO定义) → 精炼诊断 + 溯源引用              │
└──────────────────────────────────────────────────────────────────────┘
```

### 3.2 KGActivationEngine核心实现

```python
class KGActivationEngine:
    """KG激活引擎 — U-Retrieval + Bottom-up融合"""

    def __init__(self, kg: LayeredDiagnosticKG, embedding_model: str = "BAAI/bge-m3"):
        self.kg = kg
        self.embedder = SentenceTransformer(embedding_model)
        self._build_feature_index()
        self._build_summary_index()

    def _build_feature_index(self) -> None:
        G = self.kg.literature_graph
        l4_nodes = [(n, d) for n, d in G.nodes(data=True) if d.get("layer") == "EL4d"]
        self._l4_ids = [n for n, _ in l4_nodes]
        descriptions = [d.get("name", n) for n, d in l4_nodes]
        self._l4_embeddings = self.embedder.encode(descriptions, normalize_embeddings=True)

    def _build_summary_index(self) -> None:
        G = self.kg.literature_graph
        self._l2_summaries = {}
        for node, data in G.nodes(data=True):
            if data.get("layer") == "EL2":
                children = list(G.successors(node))
                child_names = [G.nodes[c].get("name", c) for c in children]
                self._l2_summaries[node] = f"{data.get('name', node)}: {', '.join(child_names)}"

        self._l2_ids = list(self._l2_summaries.keys())
        self._l2_embeddings = self.embedder.encode(
            list(self._l2_summaries.values()), normalize_embeddings=True
        )

    def activate(
        self,
        patient_features: Dict[str, Any],
        triage_hint: Optional[str] = None,
        top_k_diseases: int = 5,
        similarity_threshold: float = 0.5
    ) -> Dict:
        """
        执行U-Retrieval + Bottom-up融合检索

        patient_features: {
            "symptoms": ["黄疸", "震颤"],
            "labs": {"ceruloplasmin": 0.08},
            "imaging": {"kf_ring": "positive"},
            ...
        }
        triage_hint: 分诊结果提示 (如 "rare_metabolic")
        """
        candidate_diseases = None

        # === Top-down: 分诊提示→EL2→候选EL3 ===
        if triage_hint:
            l2_node = self._map_triage_to_l2(triage_hint)
            if l2_node:
                G = self.kg.literature_graph
                candidate_diseases = set(G.successors(l2_node))

        # === Bottom-up: 患者特征→EL4d→EL3 ===
        matched_l4 = self._match_features_bottom_up(
            patient_features, similarity_threshold, candidate_diseases
        )

        # === 汇总激活结果 ===
        activated_diseases = self._aggregate_by_disease(matched_l4)

        # === 提取诊断差异 ===
        disease_ids = [d["disease"] for d in activated_diseases[:top_k_diseases]]
        diffs = self._get_diagnostic_differences(disease_ids)

        # === 提取子图内上下文 ===
        subgraph_context = self._get_subgraph_context(disease_ids)

        # === 跨层引用 ===
        cross_layer_refs = self._get_cross_layer_references(matched_l4)

        return {
            "activated_diseases": sorted(
                activated_diseases, key=lambda x: x["activation_score"], reverse=True
            )[:top_k_diseases],
            "diagnostic_differences": diffs,
            "subgraph_context": subgraph_context,
            "cross_layer_references": cross_layer_refs,
            "activation_paths": self._trace_paths(activated_diseases)
        }

    def _match_features_bottom_up(
        self,
        patient_features: Dict,
        threshold: float,
        candidate_diseases: Optional[Set[str]] = None
    ) -> List[Dict]:
        """Bottom-up特征匹配（参考P3 find_top_n_similar_symptoms）"""
        G = self.kg.literature_graph
        matched = []

        # 路径1: 规则字段精确匹配（高优先级）
        for field_path, value in self._flatten_patient_data(patient_features):
            for l4_id in self._l4_ids:
                node_data = G.nodes[l4_id]
                if node_data.get("field") == field_path:
                    if self._check_threshold_match(value, node_data):
                        parent_l3 = self._get_parent_l3(l4_id)
                        if candidate_diseases and parent_l3 not in candidate_diseases:
                            continue
                        matched.append({
                            "match_type": "exact_field",
                            "query_field": field_path,
                            "query_value": value,
                            "matched_node": l4_id,
                            "matched_l3": parent_l3,
                            "score": 1.0
                        })

        # 路径2: 嵌入语义匹配（补充路径）
        text_features = self._extract_text_features(patient_features)
        if text_features:
            feature_embs = self.embedder.encode(text_features, normalize_embeddings=True)
            similarities = cosine_similarity(feature_embs, self._l4_embeddings)

            for i, feature in enumerate(text_features):
                top_indices = similarities[i].argsort()[-5:][::-1]
                for idx in top_indices:
                    score = float(similarities[i][idx])
                    if score >= threshold:
                        l4_node = self._l4_ids[idx]
                        parent_l3 = self._get_parent_l3(l4_node)
                        if candidate_diseases and parent_l3 not in candidate_diseases:
                            continue
                        matched.append({
                            "match_type": "embedding",
                            "query_feature": feature,
                            "matched_node": l4_node,
                            "matched_l3": parent_l3,
                            "score": score
                        })

        return matched

    def _aggregate_by_disease(self, matched_l4: List[Dict]) -> List[Dict]:
        """按疾病聚合激活分数（参考P3投票机制 + IC值加权）"""
        G = self.kg.literature_graph
        disease_scores = {}

        for match in matched_l4:
            disease = match["matched_l3"]
            if disease not in disease_scores:
                disease_scores[disease] = {
                    "disease": disease,
                    "name": G.nodes[disease].get("name", disease),
                    "activation_score": 0.0,
                    "matched_features": [],
                    "vote_count": 0
                }

            l4_node = match["matched_node"]
            ic_value = G.nodes[l4_node].get("ic_value", 1.0)
            is_core = False
            edge_data = G.get_edge_data(disease, l4_node)
            if edge_data:
                is_core = edge_data.get("is_core", False)

            weight = 2.0 if is_core else 1.0
            score_contribution = match["score"] * weight * min(ic_value, 5.0) / 5.0

            disease_scores[disease]["activation_score"] += score_contribution
            disease_scores[disease]["matched_features"].append(match)
            disease_scores[disease]["vote_count"] += 1

        return list(disease_scores.values())

    def _map_triage_to_l2(self, triage_hint: str) -> Optional[str]:
        """将分诊提示映射到EL2节点"""
        mapping = {
            "rare_metabolic": "copper_metabolism",
            "rare_autoimmune": "autoimmune_hepatitis_group",
            "rare_cholestatic": "biliary_autoimmune",
            "rare_genetic": "genetic_storage",
            "common_acquired": "common_acquired",
        }
        return mapping.get(triage_hint)

    def _get_diagnostic_differences(self, disease_ids: List[str]) -> List[Dict]:
        """获取诊断差异（参考P3 get_additional_info_from_level_2）"""
        G = self.kg.literature_graph
        diffs = []

        for i, d1 in enumerate(disease_ids):
            for d2 in disease_ids[i + 1:]:
                edge_data = G.get_edge_data(d1, d2)
                if edge_data and edge_data.get("relation") == "differential_from":
                    diffs.append({
                        "disease_pair": [d1, d2],
                        "key_features": edge_data.get("key_features", []),
                        "difficulty": edge_data.get("difficulty", "moderate")
                    })

                edge_data_rev = G.get_edge_data(d2, d1)
                if edge_data_rev and edge_data_rev.get("relation") == "differential_from":
                    diffs.append({
                        "disease_pair": [d2, d1],
                        "key_features": edge_data_rev.get("key_features", []),
                        "difficulty": edge_data_rev.get("difficulty", "moderate")
                    })

        return diffs

    def _get_subgraph_context(self, disease_ids: List[str]) -> str:
        """提取子图内上下文（参考P5 ret_context）"""
        G = self.kg.literature_graph
        context_parts = []

        for disease in disease_ids:
            disease_name = G.nodes[disease].get("name", disease)
            for successor in G.successors(disease):
                edge_data = G.get_edge_data(disease, successor)
                relation = edge_data.get("relation", "related_to")
                feature_name = G.nodes[successor].get("name", successor)
                is_core = edge_data.get("is_core", False)
                core_tag = "(核心)" if is_core else ""
                context_parts.append(
                    f"{disease_name} {relation} {feature_name}{core_tag}"
                )

        return "; ".join(context_parts)

    def _get_cross_layer_references(self, matched_l4: List[Dict]) -> List[Dict]:
        """跨层引用检索（参考P5 link_context）"""
        refs = []
        for match in matched_l4:
            l4_node = match["matched_node"]
            for link in self.kg.cross_layer_links:
                if link["kg_node"] == l4_node:
                    refs.append({
                        "feature": link["entity"],
                        "hpo_definition": link["definition"],
                        "source": link["source"]
                    })
        return refs
```

### 3.3 两阶段LLM生成（参考P5 get_response）

```python
async def generate_kg_enhanced_diagnosis(
    activation_result: Dict,
    patient_data: Dict,
    llm_client
) -> Dict:
    """
    两阶段LLM生成（参考MedGraphRAG get_response）

    阶段一: 子图内上下文 + 差异KG → 初步诊断推理
    阶段二: 跨层引用(指南+HPO) → 精炼诊断 + 溯源引用
    """
    # 阶段一
    stage1_prompt = f"""基于以下知识图谱信息，分析患者可能的诊断：

激活的疾病假设（按激活分数排序）:
{json.dumps(activation_result['activated_diseases'], ensure_ascii=False, indent=2)}

鉴别诊断差异:
{json.dumps(activation_result['diagnostic_differences'], ensure_ascii=False, indent=2)}

子图内上下文:
{activation_result['subgraph_context']}

患者数据:
{json.dumps(patient_data, ensure_ascii=False, indent=2)}

请给出初步诊断推理，包括：
1. 最可能的诊断及理由
2. 需要排除的鉴别诊断
3. 关键缺失信息"""

    stage1_result = await llm_client.ainvoke([
        SystemMessage(content="你是罕见肝病诊断专家，基于知识图谱进行推理。"),
        HumanMessage(content=stage1_prompt)
    ])

    # 阶段二
    stage2_prompt = f"""基于初步诊断推理，结合以下权威引用信息进行精炼：

初步推理:
{stage1_result.content}

权威引用:
{json.dumps(activation_result['cross_layer_references'], ensure_ascii=False, indent=2)}

请精炼诊断结论，确保：
1. 每条诊断依据标注引用来源（如[指南: AASLD 2022 §3.2]）
2. 阈值判断必须与引用原文一致
3. 如有矛盾，以指南原文为准"""

    stage2_result = await llm_client.ainvoke([
        SystemMessage(content="你是罕见肝病诊断专家，基于权威引用精炼诊断。"),
        HumanMessage(content=stage2_prompt)
    ])

    return {
        "preliminary_reasoning": stage1_result.content,
        "refined_diagnosis": stage2_result.content,
        "activation_result": activation_result
    }
```

---

## 四、与现有系统集成方案

### 4.1 模块映射与替换策略

| 现有模块 | 替换方式 | KG查询 | 降级方案 | Phase |
|----------|---------|--------|---------|-------|
| `FalsificationEngine` | 渐进替换 | `contradicts`关系 | 原有if-elif规则 | 3a |
| `GuidelineVerifier` | 渐进替换 | `guided_by`+`has_manifestation` | 原有硬编码字典 | 3b |
| `InformationGapAssessor` | 增强 | 度中心性/IC值→追问优先级 | 原有CRITICAL/HIGH/LOW | 3c |
| `DebateMediator` | 增强 | `differential_from`→差异上下文注入 | 无差异上下文 | 3d |
| `EvidenceChain` | 增强 | Triple Linking→溯源引用 | 原有硬编码引用库 | 3e |
| `GraphUpdater` | **移除** | — | hypotheses.confidence替代 | 0 |

### 4.2 LangGraph集成点

```python
# graph_orchestrator.py 修改点

async def _node_preprocessing(self, state: DiagnosticState) -> Dict:
    # 新增: KG激活（在预处理阶段执行，结果供后续节点使用）
    if self.kg_engine:
        patient_features = self._extract_features(state["patient_data"])
        triage_hint = state.get("triage_result", {}).get("path")
        activation = self.kg_engine.activate(patient_features, triage_hint)
        state_updates["graph_activation"] = activation
    return state_updates

async def _node_mdt_debate(self, state: DiagnosticState) -> Dict:
    # 新增: 注入KG差异上下文到辩论
    activation = state.get("graph_activation", {})
    if activation.get("diagnostic_differences"):
        debate_context = self._format_diff_for_debate(
            activation["diagnostic_differences"]
        )
    # ... 原有辩论逻辑
    return debate_state

async def _node_falsification(self, state: DiagnosticState) -> Dict:
    # 修改: 从KG contradicts关系获取证伪规则
    if self.kg_engine:
        contradicts = self.kg_engine.get_contradictions(
            [h["disease"] for h in state["hypotheses"]]
        )
    # ... 原有证伪逻辑
    return falsification_results
```

### 4.3 Feature Flag控制

```yaml
# config.yaml 新增
knowledge_graph:
  enabled: false          # 总开关
  engine: "networkx"      # "networkx" | "neo4j"
  data_path: "data/kg"    # KG数据路径
  embedding_model: "BAAI/bge-m3"
  activation:
    similarity_threshold: 0.5
    top_k_diseases: 5
  integration:
    falsification: false   # 逐模块开关
    guideline_verify: false
    info_gap: false
    debate_context: false
    evidence_chain: false
```

---

## 五、性能优化策略

### 5.1 检索性能优化

| 优化点 | 策略 | 来源 | 预期效果 |
|--------|------|------|----------|
| 嵌入预计算 | KG构建时预计算所有EL4节点嵌入 | P5 Milvus索引 | 查询时零嵌入开销 |
| 自适应阈值 | 根据匹配分数分布动态调整阈值 | P3固定0.5→改进 | 减少漏匹配/过匹配 |
| Top-down预过滤 | 分诊结果缩小搜索空间 | P5 U-Retrieval | 减少50%+候选节点 |
| IC值加权 | 高IC值特征权重更高 | P3 σ(e) | 提升鉴别力强的特征排名 |
| 缓存热门查询 | Redis缓存常见症状组合的激活结果 | — | 重复查询<10ms |

### 5.2 构建性能优化

| 优化点 | 策略 | 来源 | 预期效果 |
|--------|------|------|----------|
| 并行LLM抽取 | 多指南PDF并行处理 | P5 parallel_extraction | 3指南→1指南时间 |
| Gleaning限制 | max_gleaning=1（不做2轮） | P5 Gleaning | 减少50%LLM调用 |
| 批量Neo4j导入 | UNWIND批量Cypher | P5 add_graph_elements | 10x写入速度 |
| 增量更新 | 仅重建变更子图 | — | 局部更新<5min |

---

## 六、实施路线图

```
Phase 0 (0.5周): 移除GraphUpdater [DRA-KG v2]
    │
Phase 1 (3周): 数据提取 + 图谱构建
    ├── 1a: YAML+内置数据提取 (1周)
    ├── 1b: PDF指南LLM抽取+Gleaning+验证 (1.5周)
    └── 1c: HPO本体加载+IC值计算 (0.5周)
    │
Phase 2 (1.5周): 图谱构建 + 检索引擎
    ├── 2a: 三层图构建+诊断差异+KG校验 (1周)
    └── 2b: KGActivationEngine实现 (0.5周)
    │
Phase 3 (3周): 系统集成
    ├── 3a: 替换FalsificationEngine (1周)
    ├── 3b: 替换GuidelineVerifier (1周)
    ├── 3c: DUA-QA集成+辩论上下文注入 (1周)
    │
Phase 4 (1周): 测试+验证
    └── 端到端测试+激活基准测试+性能对比

总计: 9周
```
