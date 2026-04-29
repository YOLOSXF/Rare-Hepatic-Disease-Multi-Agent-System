# Medical-Agent 架构升级实施计划

**版本：** v2.0  
**日期：** 2026-04-10  
**目标架构：** 五层分层架构（参考 DeepRare + HEAL）

---

## 📊 当前状态评估

### 架构符合度：25%

| 架构层 | 设计要求 | 当前实现 | 符合度 | 优先级 |
|--------|---------|---------|--------|--------|
| **输入层** | 隐私脱敏 + 哈希化 | ❌ 无 | 0% | P1 |
| **L1 数据标准化** | NER + HPO 映射 + 对抗检测 | ⚠️ 仅字段映射 | 30% | P0 |
| **L2 智能分诊** | 罕见病红旗优先 + 分层决策 | ⚠️ 部分实现 | 60% | P0 |
| **L3A 常见快轨** | Core KG + 3-Agent 辩论 | ❌ 无 | 0% | P1 |
| **L3B 罕见深轨** | 多 Agent 辩论 + 图权重调整 | ❌ 无 | 20% | P0 |
| **L3C 不确定处理** | 鉴别清单 + MDT + 随访 | ❌ 无 | 0% | P2 |
| **L4 知识库** | KG + Milvus + Chroma | ❌ 无 | 0% | P0 |
| **L5 输出** | 审计日志 + 反馈收集 | ⚠️ 仅报告 | 40% | P1 |

---

## ✅ 已完成任务

### 任务 1：LangChain 大模型客户端集成

**状态：** ✅ 完成  
**文件：** `core/llm_client.py`

**实现功能：**
- ✅ 支持 DashScope（通义千问）
- ✅ 支持 OpenAI
- ✅ 支持 DeepSeek
- ✅ 支持 Ollama（本地）
- ✅ 懒加载初始化
- ✅ 从 YAML 配置加载
- ✅ 完整/流式/批量 API

**已更新引用：**
- ✅ `agents/history_collector_v2.py`

**依赖更新：**
```bash
pip install langchain langchain-core langchain-community langchain-openai
```

---

## 📋 待实施任务

### 阶段 1：核心能力（P0 - 必须）

#### 1.1 集成 DeepRare HPO 提取器

**参考文件：** `/home/user/agent/DeepRare/hpo_extractor.py`

**实施内容：**
1. 复制 `DeepRare/hpo_extractor.py` 到 `core/hpo_extractor.py`
2. 适配到当前项目结构
3. 集成到 `core/preprocessor.py`
4. 更新 L1 分诊逻辑

**预计工作量：** 4 小时

**验收标准：**
- [ ] 能从病历文本提取 HPO 术语
- [ ] 能映射到标准 HPO ID
- [ ] 单元测试通过

---

#### 1.2 实现自适应病例分类（参考 HEAL）

**参考文件：** `/home/user/agent/HEAL/0910-adaptive framework.py`

**实施内容：**
1. 创建 `core/adaptive_classifier.py`（替换当前空壳）
2. 实现简单/中等/复杂病历分类
3. 集成到 L2 分诊流程
4. 支持 L3A/L3B/L3C 路由

**预计工作量：** 3 小时

**验收标准：**
- [ ] 能正确分类病历复杂度
- [ ] 分诊路由正确
- [ ] 与 LangChain 集成

---

#### 1.3 重构 L2 分诊逻辑

**修改文件：** `core/triage.py`

**实施内容：**
1. 罕见病红旗规则最高优先级
2. 常见病/急危重症规则分离
3. 集成自适应分类器
4. 添加 LLM Agent 兜底

**预计工作量：** 4 小时

**验收标准：**
- [ ] 罕见病优先触发
- [ ] 分层决策正确
- [ ] 测试用例通过

---

### 阶段 2：增强能力（P1 - 重要）

#### 2.1 实现常见肝病快轨（L3A）

**新建文件：**
- `core/common_track_orchestrator.py`
- `agents/common_disease_debate.py`
- `knowledge/core_kg.py`

**实施内容：**
1. Core KG 图推理（简化版，先用规则）
2. 3-Agent 轻量辩论
3. 中国指南符合性校验
4. 置信度评估≥0.85

**预计工作量：** 8 小时

**验收标准：**
- [ ] 常见病快速输出
- [ ] 指南符合性检查
- [ ] 置信度评估准确

---

#### 2.2 实现多 Agent 辩论机制（L3B）

**参考文件：** `DeepRare/tools/llm_agent.py`

**实施内容：**
1. 基于 LangChain 实现 Agent 工具调用
2. 多 Agent 层级辩论
3. 辩论→图权重动态调整
4. Self-Reflection 迭代验证

**修改文件：**
- `core/reflection_engine.py`（重写）
- `core/langgraph_orchestrator.py`（增强）

**预计工作量：** 12 小时

**验收标准：**
- [ ] 多 Agent 辩论正常
- [ ] 图权重动态调整
- [ ] 迭代验证有效

---

#### 2.3 集成向量数据库

**新建文件：**
- `knowledge/similar_cases_db.py`（Milvus）
- `knowledge/guideline_db.py`（Chroma）

**实施内容：**
1. 安装 Milvus 和 Chroma
2. 实现相似病例检索
3. 实现指南向量检索
4. 集成到 L3B 深轨

**预计工作量：** 6 小时

**验收标准：**
- [ ] Milvus 连接正常
- [ ] Chroma 检索正常
- [ ] 相似病例检索准确

---

#### 2.4 激活 Tools 目录

**参考文件：** `DeepRare/tools/*`

**实施内容：**
1. 重写 `tools/guideline_search.py`
2. 重写 `tools/pubmed_search.py`
3. 重写 `tools/hpo_search.py`
4. 集成到 Agents

**预计工作量：** 6 小时

**验收标准：**
- [ ] 工具能正常调用
- [ ] 返回结果可用
- [ ] 错误处理完善

---

### 阶段 3：完善能力（P2 - 可选）

#### 3.1 实现不确定病例处理（L3C）

**新建文件：**
- `core/uncertain_track.py`
- `core/mdt_connector.py`

**实施内容：**
1. 鉴别诊断检查清单
2. 远程 MDT 触发（简化版）
3. 观察随访模式

**预计工作量：** 4 小时

---

#### 3.2 实现审计日志和反馈收集（L5）

**新建文件：**
- `core/audit_logger.py`
- `core/feedback_collector.py`

**实施内容：**
1. 完整审计日志
2. 医生强制确认接口
3. 反馈收集与模型迭代

**预计工作量：** 4 小时

---

#### 3.3 实现输入层隐私保护

**新建文件：**
- `core/privacy_preserver.py`

**实施内容：**
1. 隐私脱敏
2. 哈希化患者标识
3. 对抗样本检测

**预计工作量：** 3 小时

---

## 🗓️ 时间规划

### 第一周（核心能力）
- Day 1-2: HPO 提取器集成
- Day 3-4: 自适应分类器实现
- Day 5: L2 分诊重构

### 第二周（增强能力）
- Day 6-8: 常见肝病快轨
- Day 9-12: 多 Agent 辩论
- Day 13-14: 向量数据库集成

### 第三周（完善能力）
- Day 15-16: Tools 激活
- Day 17-18: 不确定病例处理
- Day 19-20: 审计日志 + 隐私保护

---

## 📦 依赖安装

```bash
# 核心依赖
pip install langchain langchain-core langchain-community langchain-openai

# 向量数据库
pip install pymilvus chromadb

# 图数据库（可选）
# pip install neo4j

# 深度学习（HPO 映射）
pip install transformers torch

# 其他
pip install beautifulsoup4 fake-useragent
```

---

## 🧪 测试计划

### 单元测试
- [ ] HPO 提取器测试
- [ ] 自适应分类器测试
- [ ] 分诊逻辑测试
- [ ] Agent 辩论测试

### 集成测试
- [ ] 完整诊断流程测试
- [ ] 常见快轨测试
- [ ] 罕见深轨测试
- [ ] 不确定处理测试

### 性能测试
- [ ] 响应时间 < 5s
- [ ] 并发支持 > 10 QPS
- [ ] 内存占用 < 2GB

---

## 📊 成功指标

| 指标 | 当前 | 目标 |
|------|------|------|
| 架构符合度 | 25% | 90% |
| 诊断准确率 | - | >85% |
| 响应时间 | - | <5s |
| 罕见病识别率 | - | >90% |
| 常见病快轨比例 | 0% | >60% |

---

## 🔄 风险管理

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| DeepRare 代码不兼容 | 高 | 逐步适配，保留原功能 |
| LangChain 版本冲突 | 中 | 锁定版本号 |
| 向量数据库性能 | 中 | 先使用内存版，后迁移 |
| 开发时间超期 | 中 | 优先级排序，分阶段交付 |

---

## 📝 下一步行动

### 立即执行（今天）
1. ✅ LangChain 客户端集成（已完成）
2. ⏳ 安装 LangChain 依赖
3. ⏳ 测试 LangChain 客户端

### 明天开始
1. 集成 DeepRare HPO 提取器
2. 实现自适应病例分类
3. 更新测试用例

---

**负责人：** AI Assistant  
**开始日期：** 2026-04-10  
**预计完成：** 2026-04-30
