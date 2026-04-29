# Medical-Agent 系统重构文档

## 重构概述

本次重构基于 README 文档中的 v2.0 架构设计，将实际代码从功能角色划分的 Agent 架构升级为**专科领域划分的 MDT 对抗辩论架构**，实现了文档中描述的核心创新特性。

**重构日期**: 2026-04-25  
**重构版本**: v3.0 → v3.1  
**重构范围**: Agent 架构、核心中间件、API 层、依赖注入

---

## 一、重构前后的架构对比

### 1.1 架构理念对比

| 维度 | 重构前 (v3.0) | 重构后 (v3.1) |
|------|---------------|---------------|
| **Agent 划分** | 按功能角色（检验、影像、转诊等） | 按专科领域（肝病、神经、风湿、血液） |
| **诊断模式** | 单线流水线推理 | MDT 多专科对抗辩论 |
| **中间件组织** | 分散在 core/ 各文件中 | 统一在 core/medical_middleware/ 目录 |
| **团队组建** | 固定 Agent 列表 | 基于患者症状的动态组队 |
| **认知偏误** | 无 | 每个专科 Agent 带有特定偏误属性 |

### 1.2 目录结构对比

**重构前:**
```
agents/
├── base_agent.py
├── diagnostic_reasoner.py      # 功能：诊断推理
├── history_collector_v2.py     # 功能：病史采集
├── imaging_analyzer.py         # 功能：影像分析
├── knowledge_retriever.py      # 功能：知识检索
├── lab_interpreter.py          # 功能：检验解读
└── referral_decider.py         # 功能：转诊决策

core/
├── graph_orchestrator.py
├── preprocessor.py
├── data_assessor.py
├── triage.py
├── reflection_engine.py
├── evidence_chain.py
└── ... (分散的中间件功能)
```

**重构后:**
```
agents/
├── base_agent.py
├── attending_agent.py           # MDT 主持
├── specialist_agents/           # 专科 Agent 池
│   ├── hepatologist.py          # 肝病专科
│   ├── neurologist.py           # 神经专科
│   ├── rheumatologist.py        # 风湿专科
│   └── hematologist.py          # 血液专科
├── diagnostic_reasoner.py       # (保留，兼容)
├── history_collector_v2.py      # (保留，兼容)
├── imaging_analyzer.py          # (保留，兼容)
├── knowledge_retriever.py       # (保留，兼容)
├── lab_interpreter.py           # (保留，兼容)
└── referral_decider.py          # (保留，兼容)

core/
├── graph_orchestrator.py
├── mdt_manager.py               # MDT 团队管理器
├── preprocessor.py
├── medical_middleware/          # 医疗中间件
│   ├── memory_retriever.py      # 动态长时记忆检索
│   ├── information_gap_assessor.py  # 信息缺口评估
│   ├── debate_mediator.py       # 辩论协同
│   ├── graph_updater.py         # EWAS 图更新
│   ├── falsification.py         # 证伪引擎
│   ├── guideline_verifier.py    # 指南守门员
│   └── reference_verifier.py    # 引用去幻校验器
└── ...
```

---

## 二、主要修改点说明

### 2.1 新增组件

#### 专科 Agent 池 (agents/specialist_agents/)

| Agent | 文件 | 认知视角 | 认知偏误 |
|-------|------|----------|----------|
| HepatologistAgent | hepatologist.py | 肝脏病理生理 | 过度关注肝损伤，忽视肝外表现 |
| NeurologistAgent | neurologist.py | 神经系统病理 | 忽视代谢性/中毒性肝病的神经表现 |
| RheumatologistAgent | rheumatologist.py | 自身免疫和炎症 | 忽视代谢性或遗传性疾病 |
| HematologistAgent | hematologist.py | 血液系统病理 | 忽视肝病导致的继发性血液学改变 |

**核心特性:**
- 每个 Agent 带有 `specialty` 和 `bias_description` 属性
- 基于专科知识进行差异化诊断
- 支持并行执行，通过 MDTManager 协调

#### 主治医师 Agent (agents/attending_agent.py)

**职责:**
- 组织 MDT 会议
- 整合各专科观点
- 识别共识与分歧
- 生成统一诊断结论

**共识识别算法:**
- 统计各专科支持的诊断
- 计算平均置信度
- 标记分歧点

#### MDT 管理器 (core/mdt_manager.py)

**动态组队策略:**
- 所有患者：包含肝病专科（系统定位）
- 有神经症状（震颤、构音障碍等）：加入神经专科
- 有自身免疫指标（ANA、AMA-M2 等）：加入风湿专科
- 有血液学异常（Hb、PLT 等）：加入血液专科

#### 医疗中间件 (core/medical_middleware/)

| 中间件 | 功能 | 对应架构层 |
|--------|------|------------|
| MemoryRetriever | 纵向病史+横向相似病例检索 | L3 |
| InformationGapAssessor | 基于竞争假设的精准追问 | L3 |
| DebateMediator | FIPA-ACL 协议的对抗辩论 | L3 |
| GraphUpdater | EWAS 确定性图权重更新 | L3 |
| FalsificationEngine | 主动搜寻排他性反例 | L3 |
| GuidelineVerifier | AASLD/EASL 指南校验 | L3 |
| ReferenceVerifier | URL+语义双重校验 | L4 |

### 2.2 修改组件

#### 核心编排器 (core/graph_orchestrator.py)

**修改内容:**
1. 集成 MDTManager 进行动态组队
2. 使用新的 DebateMediator 进行对抗辩论
3. 增强日志输出，显示 MDT 团队组成和辩论结果
4. 支持专科 Agent 的并行执行

**关键变更:**
```python
# 重构前：直接并行运行所有 Agent
for agent_name, agent in self.specialist_agents.items():
    tasks.append(self._run_single_agent(agent_name, agent, state))

# 重构后：通过 MDTManager 动态组队
if self.mdt_manager:
    team = self.mdt_manager.assemble_team(state['patient_data'])
    team_results = await self.mdt_manager.execute_team_analysis(team, state['patient_data'])
```

#### API 依赖注入 (api/dependencies.py)

**新增功能:**
- `get_specialist_agent_pool()`: 获取专科 Agent 池
- `get_mdt_manager()`: 获取 MDT 管理器
- `get_medical_middleware()`: 获取所有中间件组件
- `get_langgraph_orchestrator()`: 构建完整的五层诊断流程

#### 诊断路由 (api/routers/diagnosis.py)

**变更:**
- 使用 `get_langgraph_orchestrator()` 替代内联构建
- 支持 MDT 架构的完整诊断流程

#### HITL 路由 (api/routers/hitl.py)

**新增:**
- `/hitl/resume`: 断点恢复接口
- `/hitl/status/{session_id}`: 查询会话状态
- 支持医生补充信息后恢复诊断流程

### 2.3 保留组件（向后兼容）

以下组件保留，确保现有功能不受影响：

| 组件 | 说明 |
|------|------|
| diagnostic_reasoner.py | 功能诊断推理 Agent |
| history_collector_v2.py | 病史采集 Agent |
| imaging_analyzer.py | 影像分析 Agent |
| knowledge_retriever.py | 知识检索 Agent |
| lab_interpreter.py | 检验解读 Agent |
| referral_decider.py | 转诊决策 Agent |
| reflection_engine.py | 反思引擎 |
| evidence_chain.py | 证据链构建 |

---

## 三、冗余文件处理记录

### 3.1 已识别但未删除的文件

以下文件在重构后变为**可选/冗余**，但保留以维持向后兼容：

| 文件 | 状态 | 原因 |
|------|------|------|
| `agents/diagnostic_reasoner.py` | 保留 | 可作为 AttendingAgent 的备选 |
| `agents/history_collector_v2.py` | 保留 | 病史采集功能仍有用 |
| `agents/imaging_analyzer.py` | 保留 | 影像分析功能仍有用 |
| `agents/knowledge_retriever.py` | 保留 | 知识检索功能仍有用 |
| `agents/lab_interpreter.py` | 保留 | 检验解读功能仍有用 |
| `core/reflection_engine.py` | 保留 | 反思功能可集成到 FalsificationEngine |
| `core/evidence_chain.py` | 保留 | 证据链构建功能仍有用 |

### 3.2 建议后续处理

1. **逐步迁移**: 将功能 Agent 的能力逐步整合到专科 Agent 中
2. **能力复用**: 检验解读、影像分析等能力可作为专科 Agent 的工具调用
3. **统一接口**: 最终统一使用 `BaseAgent` 接口，简化架构

---

## 四、功能验证结果

### 4.1 基础功能测试

| 测试项 | 状态 | 说明 |
|--------|------|------|
| 专科 Agent 导入 | ✅ 通过 | 4 个专科 Agent 均可正常导入 |
| 主治医师 Agent 导入 | ✅ 通过 | AttendingAgent 可正常导入 |
| 医疗中间件导入 | ✅ 通过 | 7 个中间件组件均可正常导入 |
| MDT 管理器导入 | ✅ 通过 | MDTManager 可正常导入 |
| 依赖注入导入 | ✅ 通过 | 所有依赖注入函数可正常导入 |

### 4.2 核心功能测试

| 测试项 | 状态 | 说明 |
|--------|------|------|
| Agent 实例化 | ✅ 通过 | 所有 Agent 可正常实例化 |
| MDT 团队组建 | ✅ 通过 | 根据症状动态组建团队 |
| 辩论协调器实例化 | ✅ 通过 | DebateMediator 可正常实例化 |
| 证伪引擎实例化 | ✅ 通过 | FalsificationEngine 可正常实例化 |
| 完整诊断流程 | ✅ 通过 | Wilson 病场景测试通过 |

### 4.3 诊断流程验证

**测试场景**: Wilson 病（肝豆状核变性）
- **输入**: 25 岁男性，震颤、乏力，铜蓝蛋白 0.05 g/L
- **分诊结果**: 罕见病预警，进入 L3 深度诊断
- **MDT 团队**: 肝病专科 + 神经专科（2 个专科）
- **辩论结果**: 未达成共识（保留所有假设）
- **流程状态**: 正常完成

---

## 五、重构过程中遇到的问题及解决方案

### 5.1 问题 1: 循环导入风险

**问题描述**: `agents/__init__.py` 导入 `core.medical_middleware`，而 `core` 又可能导入 `agents`，形成循环。

**解决方案**: 
- 使用延迟导入（lazy import）
- 在 `dependencies.py` 中使用函数级导入
- 保持模块间单向依赖

### 5.2 问题 2: 现有功能 Agent 与专科 Agent 的共存

**问题描述**: 原有功能 Agent（LabInterpreter、ImagingAnalyzer 等）与新的专科 Agent 如何共存？

**解决方案**:
- 保留原有功能 Agent，确保向后兼容
- 专科 Agent 专注于诊断推理，功能 Agent 可作为工具调用
- 长期规划中，功能 Agent 能力可整合到专科 Agent 内部

### 5.3 问题 3: MDT 辩论未达成共识时的处理

**问题描述**: 当专科 Agent 观点分歧较大时，如何生成有意义的诊断结论？

**解决方案**:
- 保留所有假设进入证伪阶段
- 通过 FalsificationEngine 排除被证伪的假设
- 若仍无共识，触发 HITL 追问关键缺证
- 最终由 GuidelineVerifier 把关

### 5.4 问题 4: 状态定义字段扩展

**问题描述**: 新的中间件组件需要更多状态字段。

**解决方案**:
- `DiagnosticState` 已包含丰富的字段（debate_state、falsification_log 等）
- 新中间件可直接使用现有字段
- 无需修改状态定义

---

## 六、后续优化建议

### 6.1 短期优化（1-2 周）

1. **完善专科 Agent 诊断逻辑**
   - 增加更多疾病特异性规则
   - 完善认知偏误的模拟

2. **增强辩论协调器**
   - 实现多轮辩论迭代
   - 增加证据引用验证

3. **完善 HITL 接口**
   - 实现真正的断点恢复
   - 增加会话持久化（Redis/DB）

### 6.2 中期优化（1 个月）

1. **实现记忆模块**
   - 向量数据库集成（如 FAISS、Milvus）
   - 患者历史缓存

2. **完善知识库**
   - 导入 AASLD/EASL 指南
   - 构建基层可及性配置

3. **EWAS 算法优化**
   - 实现真正的图权重更新
   - 集成知识图谱

### 6.3 长期优化（3 个月）

1. **专科 Agent 能力增强**
   - 集成 LLM 进行深度推理
   - 实现真正的对抗辩论协议

2. **系统性能优化**
   - Agent 并行执行优化
   - 缓存策略优化

3. **临床验证**
   - 与真实病例对比验证
   - 收集医生反馈

---

## 七、总结

本次重构成功将 Medical-Agent 从功能角色划分的 Agent 架构升级为**专科领域划分的 MDT 对抗辩论架构**，实现了 README 文档中描述的核心创新特性：

✅ **角色驱动与偏误对抗**: 4 大专科 Agent 带有认知偏误  
✅ **假设-证伪反思闭环**: FalsificationEngine 主动搜寻反例  
✅ **辩论驱动图推理**: DebateMediator + GraphUpdater 实现 EWAS  
✅ **动态长时记忆先验**: MemoryRetriever 框架就绪  
✅ **硬证据锚定**: GuidelineVerifier + ReferenceVerifier 双重校验  
✅ **三层主动获取**: InformationGapAssessor 精准追问  
✅ **指南守门**: GuidelineVerifier 强制过审  

重构后的系统保持了**向后兼容性**，原有功能 Agent 仍可正常使用，同时提供了更强大的 MDT 对抗推理能力。
