# 医疗智能诊断系统 - 前端

基于 Vue 3 + TypeScript + Element Plus 的医疗诊断前端界面，与后端 LangGraph StateGraph 架构完美对接。

## 技术栈

- **框架**: Vue 3.4 + TypeScript 5.4
- **UI库**: Element Plus 2.6
- **构建工具**: Vite 5.1
- **HTTP客户端**: Axios 1.6
- **状态管理**: Pinia 2.1
- **路由**: Vue Router 4.3

## 快速开始

### 1. 安装依赖

```bash
cd frontend
npm install
```

### 2. 启动开发服务器

```bash
npm run dev
```

访问: http://localhost:3000

### 3. 构建生产版本

```bash
npm run build
```

### 4. 类型检查

```bash
npm run type-check
```

## 项目结构

```
frontend/
├── src/
│   ├── api/                    # API 请求封装
│   │   ├── request.ts          # Axios 实例配置
│   │   └── diagnosis.ts        # 诊断相关 API
│   ├── components/             # Vue 组件
│   │   ├── PatientForm.vue     # 患者数据输入表单
│   │   └── DiagnosisResult.vue # 诊断结果展示
│   ├── types/                  # TypeScript 类型定义
│   │   └── index.ts            # 对接后端数据结构
│   ├── App.vue                 # 主应用组件
│   ├── main.ts                 # 应用入口
│   └── vite-env.d.ts           # 类型声明
├── index.html                  # HTML 入口
├── vite.config.ts              # Vite 配置
├── tsconfig.json               # TypeScript 配置
└── package.json                # 依赖配置
```

## 核心功能

### 1. 患者数据输入表单

- ✅ 完整覆盖后端 `PatientData` 所有字段
- ✅ 表单验证（必填、格式、范围）
- ✅ 响应式设计，支持移动端
- ✅ 示例数据一键填充（测试用）

**包含字段**:
- 基本信息：患者ID、年龄、性别、主诉、BMI
- 既往史：饮酒量、吸烟、糖尿病、高血压、家族史、用药史、过敏史
- 症状：12种常见肝病症状多选
- 检验结果：ALT、AST、ALP、GGT、胆红素、白蛋白、凝血酶原时间
- 超声检查：超声发现、肝脏大小、回声特征

### 2. 诊断接口调用

- ✅ 支持两种诊断模式：
  - **完整诊断** (L1-L5): 执行完整对抗推理流程
  - **快速筛查** (L1-L2): 轻量级分诊
- ✅ 实时进度显示（8个诊断阶段追踪）
- ✅ 错误处理和用户提示

### 3. 诊断结果展示

完整呈现后端 `graph_orchestrator.py` 定义的所有报告字段：

- 📋 **报告头部**: 诊断路径、置信度、紧急程度、数据完整度
- 🏥 **诊断结论**: 主要诊断 + 支持/反对证据
- 🧠 **临床推理**: LLM 生成的专业分析（如可用）
- 🔍 **鉴别诊断**: Top 5 候选疾病列表
- ❌ **证伪日志**: 被排除的假设及矛盾证据
- 💬 **MDT辩论**: 共识点、分歧点、辩论消息
- ✅ **指南校验**: 临床指南符合性检查
- 📝 **推荐检查**: 建议的进一步检查项目
- 📅 **随访计划**: 门诊随访建议
- ⚠️ **HITL问题**: 需要补充的关键信息

## API 对接

### 后端地址

默认: `http://localhost:8000`

### 主要接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/v1/diagnose/` | POST | 完整诊断 (L1-L5) |
| `/api/v1/diagnose/screen` | POST | 快速筛查 (L1-L2) |
| `/api/v1/hitl/resume/:threadId` | POST | HITL恢复 |
| `/api/v1/health` | GET | 健康检查 |

### 代理配置

开发环境已配置 Vite 代理，自动转发 `/api` 请求到后端：

```typescript
// vite.config.ts
server: {
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true,
    },
  },
}
```

## 数据类型对接

前端类型定义完全基于后端文件：

- [state_definition.py](../core/state_definition.py) → `PatientData`, `Question`, `DiagnosticHypothesis`
- [graph_orchestrator.py](../core/graph_orchestrator.py) → `DiagnosisReport`, `TriageResult`, `FalsificationEntry`

### 报告类型映射

| 后端报告类型 | 前端显示 |
|-------------|---------|
| `COMMON_DIAGNOSIS` | 常见病确诊报告 |
| `TRIAGE_RECOMMENDATION` | 补检建议报告 |
| `FINAL_DIAGNOSIS` | MDT 深度诊断报告 |

## 响应式设计

- ✅ 桌面端 (≥1200px): 三列表单布局
- ✅ 平板端 (≥768px): 双列布局
- ✅ 移动端 (<768px): 单列布局

## 开发说明

### 表单验证规则

- 患者ID: 必填，2-50字符
- 主诉: 必填，5-500字符
- 年龄: 必填，0-150
- 性别: 必选

### 诊断流程阶段

1. L1: 数据预处理
2. L1: 数据评估
3. L2: 智能分诊
4. L3: 记忆检索
5. L3: MDT辩论
6. L3: 证伪引擎
7. L3: 指南校验
8. L5: 报告生成

### 导出报告

支持导出 JSON 格式诊断报告，文件名格式：`diagnosis_{patientId}_{timestamp}.json`

## 注意事项

1. 确保后端服务已启动 (`python -m uvicorn api.main:app --reload`)
2. 首次使用需填写完整的患者数据
3. 完整诊断模式耗时约 30-120 秒
4. 本系统仅供医疗研究使用，不可直接用于临床诊断

## 浏览器兼容性

- Chrome ≥ 90
- Firefox ≥ 88
- Safari ≥ 14
- Edge ≥ 90

## License

仅供医疗研究使用
