<template>
  <div class="medical-diagnosis-app">
    <!-- 页面头部 -->
    <header class="app-header">
      <div class="header-content">
        <div class="logo">
          <el-icon :size="32"><FirstAidKit /></el-icon>
          <h1>医疗智能诊断系统</h1>
        </div>
        <div class="header-actions">
          <el-button text @click="showHelp">
            <el-icon><QuestionFilled /></el-icon>
            帮助
          </el-button>
          <el-button text @click="showSystemInfo">
            <el-icon><InfoFilled /></el-icon>
            系统信息
          </el-button>
        </div>
      </div>
    </header>

    <!-- 主内容区 -->
    <main class="app-main">
      <!-- 步骤条 -->
      <el-steps :active="currentStep" finish-status="success" class="steps-container">
        <el-step title="填写患者信息" icon="Edit" />
        <el-step title="提交诊断" icon="Upload" />
        <el-step title="查看报告" icon="Document" />
      </el-steps>

      <!-- 流程说明 -->
      <el-alert
        v-if="currentStep === 0"
        title="对抗推理诊断流程"
        type="info"
        :closable="false"
        style="margin-bottom: 20px"
      >
        <template #default>
          <p style="margin: 0; font-size: 13px; color: #606266; line-height: 1.6">
            系统将自动执行：数据预处理 → 智能分诊 → MDT对抗辩论 → 证伪引擎 → 指南校验 → 报告生成<br>
            <span style="color: #909399">报告类型将根据诊断路径动态决定：常见病确诊 / 补检建议 / MDT深度诊断</span>
          </p>
        </template>
      </el-alert>

      <!-- 步骤1: 患者表单 -->
      <el-card v-show="currentStep === 0" class="form-card" shadow="hover">
        <PatientForm
          :loading="loading"
          @submit="handleDiagnosisSubmit"
        />
      </el-card>

      <!-- 步骤2: 诊断中 -->
      <el-card v-show="currentStep === 1" class="loading-card" shadow="hover">
        <div class="loading-content">
          <el-progress
            type="circle"
            :percentage="loadingProgress"
            :status="loadingProgress === 100 ? 'success' : undefined"
            :width="150"
          />
          <h2>{{ loadingMessage }}</h2>
          <el-timeline class="progress-timeline">
            <el-timeline-item
              v-for="(phase, idx) in diagnosticPhases"
              :key="idx"
              :type="phase.status === 'completed' ? 'success' : phase.status === 'active' ? 'primary' : 'info'"
              :timestamp="phase.time"
              placement="top"
            >
              <strong>{{ phase.name }}</strong>
              <p>{{ phase.description }}</p>
            </el-timeline-item>
          </el-timeline>
        </div>
      </el-card>

      <!-- 步骤3: 诊断结果 -->
      <DiagnosisResult
        v-show="currentStep === 2 && diagnosisReport"
        :report="diagnosisReport"
        :chief-complaint="diagnosisChiefComplaint"
        @export="handleExportReport"
        @new-diagnosis="handleNewDiagnosis"
      />
    </main>

    <!-- 页脚 -->
    <footer class="app-footer">
      <p>© 2026 医疗智能诊断系统 | LangGraph StateGraph 架构 | 仅供医疗研究使用</p>
    </footer>

    <!-- 帮助对话框 -->
    <el-dialog v-model="helpDialogVisible" title="使用帮助" width="600px">
      <el-steps direction="vertical" :active="4">
        <el-step title="填写患者信息" description="完整填写患者基本信息、既往史、症状、检验结果和超声检查数据" />
        <el-step title="提交诊断" description="点击提交按钮，系统将自动执行完整诊断流程，预计耗时30-120秒" />
        <el-step title="查看报告" description="诊断完成后可查看详细报告，支持导出为JSON格式" />
      </el-steps>
      <template #footer>
        <el-button type="primary" @click="helpDialogVisible = false">我知道了</el-button>
      </template>
    </el-dialog>

    <!-- 系统信息对话框 -->
    <el-dialog v-model="systemInfoVisible" title="系统信息" width="600px">
      <el-descriptions :column="1" border>
        <el-descriptions-item label="系统版本">v3.0.0</el-descriptions-item>
        <el-descriptions-item label="架构">LangGraph StateGraph</el-descriptions-item>
        <el-descriptions-item label="前端技术栈">Vue 3 + TypeScript + Element Plus</el-descriptions-item>
        <el-descriptions-item label="后端API">http://localhost:8000</el-descriptions-item>
        <el-descriptions-item label="核心特性">
          <ul style="margin: 0; padding-left: 20px">
            <li>MDT Multi-Agent Debate</li>
            <li>Falsification Engine</li>
            <li>HITL Interrupt/Resume</li>
            <li>Guideline Verification</li>
            <li>KG-Enhanced Diagnosis</li>
          </ul>
        </el-descriptions-item>
        <el-descriptions-item label="报告类型">
          <ul style="margin: 0; padding-left: 20px">
            <li>L5a: 常见病确诊报告</li>
            <li>L5b: 补检建议报告</li>
            <li>L5c: MDT终局诊断报告</li>
          </ul>
        </el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { FirstAidKit, QuestionFilled, InfoFilled } from '@element-plus/icons-vue'
import PatientForm from '@/components/PatientForm.vue'
import DiagnosisResult from '@/components/DiagnosisResult.vue'
import type { PatientData, FinalReport, DiagnosisResponse } from '@/types'
import { submitDiagnosis } from '@/api/diagnosis'
import { ElMessage, ElNotification } from 'element-plus'

// 当前步骤
const currentStep = ref(0)

// 加载状态
const loading = ref(false)
const loadingProgress = ref(0)
const loadingMessage = ref('正在初始化...')

// 诊断报告
const diagnosisReport = ref<FinalReport | null>(null)
const diagnosisChiefComplaint = ref('')

// HITL中断状态
const hitlInterrupted = ref(false)
const hitlSessionId = ref('')

// 对话框
const helpDialogVisible = ref(false)
const systemInfoVisible = ref(false)

// 诊断阶段追踪
interface DiagnosticPhase {
  name: string
  description: string
  status: 'pending' | 'active' | 'completed'
  time: string
}

const diagnosticPhases = reactive<DiagnosticPhase[]>([
  { name: 'L1: 数据预处理', description: '标准化患者数据', status: 'pending', time: '' },
  { name: 'L1: 数据评估', description: '评估数据完整性', status: 'pending', time: '' },
  { name: 'L2: 智能分诊', description: '分诊路径决策', status: 'pending', time: '' },
  { name: 'L3: 记忆检索', description: '检索历史病例', status: 'pending', time: '' },
  { name: 'L3: MDT辩论', description: '多专科对抗推理', status: 'pending', time: '' },
  { name: 'L3: 证伪引擎', description: '排除矛盾假设', status: 'pending', time: '' },
  { name: 'L3: 指南校验', description: '临床指南符合性检查', status: 'pending', time: '' },
  { name: 'L5: 报告生成', description: '生成诊断报告', status: 'pending', time: '' },
])

/**
 * 处理诊断提交
 */
const handleDiagnosisSubmit = async (patientData: PatientData) => {
  loading.value = true
  currentStep.value = 1
  loadingProgress.value = 0
  hitlInterrupted.value = false
  
  try {
    // 模拟诊断流程阶段更新
    startPhaseSimulation()
    
    // 调用完整诊断 API
    const result: DiagnosisResponse = await submitDiagnosis(patientData)
    
    loadingProgress.value = 100
    completeAllPhases()
    
    // 检查是否是HITL中断响应
    if (result.hitl_status === 'interrupted') {
      hitlInterrupted.value = true
      hitlSessionId.value = result.hitl_session_id
      
      ElNotification({
        title: '需要补充信息',
        message: '诊断流程已暂停，请补充关键检查数据',
        type: 'warning',
        duration: 5000,
      })
      
      // 可以在这里显示HITL问题列表
      console.log('HITL Questions:', result.hitl_questions)
    }
    
    // 延迟显示结果
    await new Promise(resolve => setTimeout(resolve, 500))
    
    // 保存主诉信息用于报告展示
    diagnosisChiefComplaint.value = patientData.chief_complaint
    
    // 转换API响应为前端报告格式
    diagnosisReport.value = convertResponseToReport(result, patientData)
    currentStep.value = 2
    
    ElNotification({
      title: '诊断完成',
      message: `患者 ${patientData.patient_id} 的诊断报告已生成`,
      type: 'success',
      duration: 3000,
    })
  } catch (error: any) {
    ElMessage.error(error.message || '诊断请求失败')
    currentStep.value = 0
  } finally {
    loading.value = false
  }
}

/**
 * 将API响应转换为前端报告格式
 * 报告类型完全根据诊断路径决定 (对应 graph_orchestrator.py L198-200)
 */
const convertResponseToReport = (response: DiagnosisResponse, patientData: PatientData): FinalReport => {
  // 如果是HITL中断响应，构造一个特殊的报告
  if (response.hitl_status === 'interrupted') {
    const path = response.metadata?.triage_path || 'unknown'
    return {
      report_type: 'FINAL_DIAGNOSIS',
      report_version: response.metadata?.version || 'hitl_interrupted_v1',
      status: 'INCONCLUSIVE',
      patient_id: response.patient_id,
      path: path === 'rare_deep_path' ? 'rare' : path,
      diagnosis: response.primary_diagnosis || null,
      confidence: response.confidence_score || 0,
      confidence_level: response.confidence_score >= 0.8 ? 'high' : response.confidence_score >= 0.6 ? 'medium' : 'low',
      is_rare_disease_alert: response.metadata?.is_rare_disease_alert || true,
      urgency: response.referral_recommendation?.urgency || 'routine',
      triage: response.triage || {},
      data_completeness_score: response.metadata?.data_completeness || 0,
      differential_diagnosis: response.differential_diagnosis || response.partial_diagnosis || [],
      referral: response.referral_recommendation || {},
      debate_process: response.debate_process || null,
      falsification_log: response.falsification_log || [],
      kg_retrieval_result: response.metadata?.kg_retrieval_result || {},
      memory_context: response.metadata?.memory_context || null,
      guideline_check: response.guideline_check || null,
      hitl_questions: response.hitl_questions || [],
      hitl_status: 'interrupted',
      excluded_hypotheses: response.metadata?.excluded_hypotheses || [],
      clinical_summary: response.clinical_summary,
      recommended_tests: response.recommended_tests || [],
    }
  }

  // 获取诊断路径 (核心判断依据)
  const path = response.metadata?.triage_path || 'unknown'

  // ==================== 根据诊断路径动态决定报告类型 ====================
  // graph_orchestrator.py L198-200:
  // - common_fast_path: 常见病快速通道 → common_disease_report (确诊报告)
  // - rare_deep_path: 罕见病预警 → 进入 L3 深度诊断 → mdt_final_report
  // - uncertain_fallback: 不确定/数据不足 → triage_examination_report (补检开单)

  if (path === 'common_fast_path') {
    // L5a: 常见病确诊报告
    return {
      report_type: 'COMMON_DIAGNOSIS',
      report_version: response.metadata?.version || 'rule_based_v1',
      status: 'CONCLUSIVE',
      patient_id: response.patient_id,
      path: 'common',
      diagnosis: response.primary_diagnosis,
      confidence: response.confidence_score,
      confidence_level: response.confidence_score >= 0.8 ? 'high' : 'medium',
      is_rare_disease_alert: response.metadata?.is_rare_disease_alert || false,
      urgency: response.referral_recommendation?.urgency || 'routine',
      triage: response.triage || {},
      data_completeness_score: response.metadata?.data_completeness || 0,
      recommended_tests: response.recommended_tests || [],
      matched_diseases: response.differential_diagnosis || [],
      clinical_reasoning: response.clinical_summary || response.clinical_analysis,
      message: response.evidence_chain?.join(', ') || '',
      follow_up_plan: response.follow_up_plan?.plan || response.follow_up_plan,
      referral_recommendation: response.referral_recommendation,
    }
  }

  if (path === 'uncertain_fallback' || path === 'uncertain' || path === 'insufficient_data') {
    // L5b: 补检建议报告 (数据不足/不确定)
    return {
      report_type: 'TRIAGE_RECOMMENDATION',
      report_version: response.metadata?.version || 'triage_v1',
      status: 'INCONCLUSIVE',
      patient_id: response.patient_id,
      path: 'uncertain',
      diagnosis: response.primary_diagnosis || null,
      confidence: response.confidence_score,
      confidence_level: response.confidence_score >= 0.8 ? 'high' : response.confidence_score >= 0.6 ? 'medium' : 'low',
      is_rare_disease_alert: response.metadata?.is_rare_disease_alert || false,
      urgency: response.referral_recommendation?.urgency || 'routine',
      triage: response.triage || {},
      data_completeness_score: response.metadata?.data_completeness || 0,
      differential_diagnosis: response.differential_diagnosis || [],
      recommended_tests: response.recommended_tests || [],
      missing_critical: [],
      missing_recommended: [],
      clinical_analysis: response.clinical_analysis,
      uncertainty_reason: response.uncertainty_reason,
      message: '数据不足，建议补充关键检查项目',
    }
  }

  // L5c: MDT终局诊断报告 (rare_deep_path 或其他)
  return {
    report_type: 'FINAL_DIAGNOSIS',
    report_version: response.metadata?.version || 'mdt_v1',
    status: 'CONCLUSIVE',
    patient_id: response.patient_id,
    path: path === 'rare_deep_path' ? 'rare' : path,
    diagnosis: response.primary_diagnosis || null,
    confidence: response.confidence_score,
    confidence_level: response.confidence_score >= 0.8 ? 'high' : response.confidence_score >= 0.6 ? 'medium' : 'low',
    is_rare_disease_alert: response.metadata?.is_rare_disease_alert || false,
    urgency: response.referral_recommendation?.urgency || 'routine',
    triage: response.triage || {},
    data_completeness_score: response.metadata?.data_completeness || 0,
    differential_diagnosis: response.differential_diagnosis || [],
    referral: response.referral_recommendation || {},
    debate_process: response.debate_process || null,
    falsification_log: response.falsification_log || [],
    kg_retrieval_result: response.metadata?.kg_retrieval_result || {},
    memory_context: response.metadata?.memory_context || null,
    guideline_check: response.guideline_check || null,
    hitl_questions: [],
    hitl_status: 'normal',
    excluded_hypotheses: response.metadata?.excluded_hypotheses || [],
    clinical_summary: response.clinical_summary,
    recommended_tests: response.recommended_tests || [],
  }
}

/**
 * 模拟诊断流程阶段更新
 */
const startPhaseSimulation = () => {
  const totalPhases = diagnosticPhases.length
  const totalTime = 60000 // 总预估时间60秒
  const timePerPhase = totalTime / totalPhases
  
  diagnosticPhases.forEach((phase, idx) => {
    setTimeout(() => {
      phase.status = 'active'
      phase.time = new Date().toLocaleTimeString()
      loadingProgress.value = Math.round(((idx + 0.5) / totalPhases) * 100)
      loadingMessage.value = phase.name
    }, idx * timePerPhase)
    
    setTimeout(() => {
      phase.status = 'completed'
    }, (idx + 1) * timePerPhase)
  })
}

/**
 * 完成所有阶段
 */
const completeAllPhases = () => {
  const now = new Date().toLocaleTimeString()
  diagnosticPhases.forEach(phase => {
    phase.status = 'completed'
    if (!phase.time) phase.time = now
  })
}

/**
 * 导出报告
 */
const handleExportReport = () => {
  if (!diagnosisReport.value) return
  
  const reportData = JSON.stringify(diagnosisReport.value, null, 2)
  const blob = new Blob([reportData], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `diagnosis_${diagnosisReport.value.patient_id}_${Date.now()}.json`
  a.click()
  URL.revokeObjectURL(url)
  
  ElMessage.success('报告已导出')
}

/**
 * 新诊断
 */
const handleNewDiagnosis = () => {
  currentStep.value = 0
  diagnosisReport.value = null
  loadingProgress.value = 0
  hitlInterrupted.value = false
  hitlSessionId.value = ''
  
  diagnosticPhases.forEach(phase => {
    phase.status = 'pending'
    phase.time = ''
  })
}

/**
 * 显示帮助
 */
const showHelp = () => {
  helpDialogVisible.value = true
}

/**
 * 显示系统信息
 */
const showSystemInfo = () => {
  systemInfoVisible.value = true
}

/**
 * 页面初始化
 */
onMounted(() => {
  console.log('医疗智能诊断系统已加载')
})
</script>

<style scoped lang="scss">
.medical-diagnosis-app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.app-header {
  background: white;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
  padding: 20px 0;

  .header-content {
    max-width: 1400px;
    margin: 0 auto;
    padding: 0 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;

    .logo {
      display: flex;
      align-items: center;
      gap: 15px;
      color: #409eff;

      h1 {
        margin: 0;
        font-size: 24px;
        color: #303133;
      }
    }

    .header-actions {
      display: flex;
      gap: 10px;
    }
  }
}

.app-main {
  flex: 1;
  max-width: 1400px;
  margin: 30px auto;
  padding: 0 20px;
  width: 100%;
}

.steps-container {
  background: white;
  padding: 20px 30px;
  border-radius: 8px;
  margin-bottom: 20px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}

.form-card,
.loading-card {
  border-radius: 8px;
}

.loading-content {
  text-align: center;
  padding: 40px 20px;

  h2 {
    margin: 20px 0;
    color: #409eff;
  }

  .progress-timeline {
    margin-top: 40px;
    text-align: left;
    max-width: 600px;
    margin-left: auto;
    margin-right: auto;

    p {
      margin: 5px 0;
      color: #909399;
      font-size: 14px;
    }
  }
}

.app-footer {
  background: white;
  padding: 20px;
  text-align: center;
  color: #909399;
  margin-top: 40px;

  p {
    margin: 0;
    font-size: 14px;
  }
}

// 响应式设计
@media (max-width: 768px) {
  .app-header .header-content {
    flex-direction: column;
    gap: 15px;
  }

  .steps-container {
    padding: 15px;

    :deep(.el-step__title) {
      font-size: 12px;
    }
  }

  .app-main {
    margin: 15px auto;
    padding: 0 10px;
  }
}

@media (max-width: 480px) {
  .logo h1 {
    font-size: 18px;
  }

  .app-header {
    padding: 15px 0;
  }
}
</style>
