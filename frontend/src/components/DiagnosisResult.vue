<template>
  <div v-if="report" class="medical-report">
    <!-- 报告导航栏 -->
    <nav class="report-nav">
      <div class="nav-left">
        <el-breadcrumb separator="/">
          <el-breadcrumb-item>诊断系统</el-breadcrumb-item>
          <el-breadcrumb-item>{{ getReportTitle() }}</el-breadcrumb-item>
        </el-breadcrumb>
      </div>
      <div class="nav-right">
        <el-button-group size="small">
          <el-button @click="exportAsPDF" :icon="Document">PDF</el-button>
          <el-button @click="exportAsJSON" :icon="Download">JSON</el-button>
          <el-button @click="exportAsText" :icon="Tickets">TXT</el-button>
        </el-button-group>
        <el-button size="small" @click="$emit('new-diagnosis')" :icon="RefreshRight">新诊断</el-button>
      </div>
    </nav>

    <!-- 报告头部 -->
    <section class="report-hero" :class="`hero-${getHeroTheme()}`">
      <div class="hero-content">
        <div class="hero-badge">
          <el-icon :size="28"><component :is="getHeroIcon()" /></el-icon>
        </div>
        <div class="hero-text">
          <h1 class="hero-title">{{ getReportTitle() }}</h1>
          <p class="hero-subtitle">{{ getReportSubtitle() }}</p>
        </div>
        <div class="hero-meta">
          <el-tag :type="getStatusType()" effect="dark" size="large">
            {{ report.status === 'CONCLUSIVE' ? '结论明确' : '结论不明确' }}
          </el-tag>
          <span class="meta-item">
            <el-icon><User /></el-icon>
            {{ report.patient_id }}
          </span>
          <span class="meta-item">
            <el-icon><Clock /></el-icon>
            {{ new Date().toLocaleString('zh-CN') }}
          </span>
        </div>
      </div>
    </section>

    <!-- 关键指标仪表盘 -->
    <section class="dashboard-grid">
      <div class="metric-card" :class="getConfidenceLevelClass()">
        <div class="metric-header">
          <span class="metric-label">置信度</span>
          <el-icon><Aim /></el-icon>
        </div>
        <div class="metric-value">{{ (report.confidence * 100).toFixed(0) }}%</div>
        <el-progress
          :percentage="Math.round(report.confidence * 100)"
          :color="getConfidenceColor(report.confidence)"
          :stroke-width="8"
          :show-text="false"
        />
        <div class="metric-footer">{{ report.confidence_level?.toUpperCase() }}</div>
      </div>

      <div class="metric-card">
        <div class="metric-header">
          <span class="metric-label">数据完整度</span>
          <el-icon><DataAnalysis /></el-icon>
        </div>
        <div class="metric-value">{{ (report.data_completeness_score * 100).toFixed(0) }}%</div>
        <el-progress
          :percentage="Math.round(report.data_completeness_score * 100)"
          :color="getDataCompletenessColor()"
          :stroke-width="8"
          :show-text="false"
        />
        <div class="metric-footer">{{ getDataCompletenessLabel() }}</div>
      </div>

      <div class="metric-card">
        <div class="metric-header">
          <span class="metric-label">紧急程度</span>
          <el-icon><BellFilled /></el-icon>
        </div>
        <div class="metric-value">{{ getUrgencyText() }}</div>
        <div class="metric-footer">
          <el-tag :type="getUrgencyType()" size="small">{{ getUrgencyDescription() }}</el-tag>
        </div>
      </div>

      <div class="metric-card" v-if="report.is_rare_disease_alert">
        <div class="metric-header">
          <span class="metric-label">罕见病预警</span>
          <el-icon><WarningFilled /></el-icon>
        </div>
        <div class="metric-value">已触发</div>
        <div class="metric-footer">
          <el-tag type="danger" size="small">需要专科评估</el-tag>
        </div>
      </div>

      <div class="metric-card" v-else>
        <div class="metric-header">
          <span class="metric-label">诊断路径</span>
          <el-icon><Compass /></el-icon>
        </div>
        <div class="metric-value">{{ getPathText() }}</div>
        <div class="metric-footer">
          <el-tag :type="getPathType()" size="small">{{ getPathDescription() }}</el-tag>
        </div>
      </div>
    </section>

    <!-- ==================== COMMON_DIAGNOSIS 常见病确诊报告 ==================== -->
    <template v-if="report.report_type === 'COMMON_DIAGNOSIS'">
      <!-- 诊断结论 -->
      <el-collapse v-model="activeSections" class="report-collapse">
        <el-collapse-item name="diagnosis" title="" class="collapse-item-primary">
          <template #title>
            <div class="collapse-title-primary">
              <el-icon class="collapse-icon-success"><CircleCheckFilled /></el-icon>
              <span class="collapse-title-text">诊断结论</span>
              <el-tag size="small" type="success">确诊</el-tag>
            </div>
          </template>
          <div class="diagnosis-highlight">
            <div class="diagnosis-main">
              <h2>{{ typeof report.diagnosis === 'string' ? report.diagnosis : report.diagnosis?.disease }}</h2>
              <el-tag v-if="typeof report.diagnosis === 'object' && report.diagnosis" type="success" size="large">
                置信度 {{ (report.diagnosis.confidence * 100).toFixed(1) }}%
              </el-tag>
            </div>
            <p v-if="report.message" class="diagnosis-message">{{ report.message }}</p>
          </div>
        </el-collapse-item>

        <!-- 临床推理 -->
        <el-collapse-item v-if="report.clinical_reasoning" name="reasoning" title="">
          <template #title>
            <div class="collapse-title">
              <el-icon class="collapse-icon-info"><EditPen /></el-icon>
              <span class="collapse-title-text">LLM 临床推理分析</span>
            </div>
          </template>
          <div class="reasoning-content">
            <div class="reasoning-text">{{ report.clinical_reasoning }}</div>
          </div>
        </el-collapse-item>

        <!-- 诊断证据 -->
        <el-collapse-item v-if="typeof report.diagnosis === 'object' && report.diagnosis?.supporting_evidence?.length" name="evidence" title="">
          <template #title>
            <div class="collapse-title">
              <el-icon class="collapse-icon-primary"><Link /></el-icon>
              <span class="collapse-title-text">支持证据 ({{ report.diagnosis.supporting_evidence.length }})</span>
            </div>
          </template>
          <el-table :data="report.diagnosis.supporting_evidence.map((e, i) => ({ index: i + 1, evidence: e }))" stripe>
            <el-table-column prop="index" label="序号" width="80" align="center" />
            <el-table-column prop="evidence" label="证据内容" />
          </el-table>
        </el-collapse-item>

        <!-- 治疗方案与预后 -->
        <el-collapse-item v-if="report.follow_up_plan || report.referral_recommendation" name="treatment" title="">
          <template #title>
            <div class="collapse-title">
              <el-icon class="collapse-icon-warning"><FirstAidKit /></el-icon>
              <span class="collapse-title-text">治疗方案与预后</span>
            </div>
          </template>
          <el-row :gutter="20">
            <el-col :xs="24" :md="12">
              <div class="treatment-card">
                <h4>随访计划</h4>
                <p>{{ report.follow_up_plan || '暂无随访计划' }}</p>
              </div>
            </el-col>
            <el-col :xs="24" :md="12">
              <div class="treatment-card">
                <h4>转诊建议</h4>
                <p>{{ report.referral_recommendation || '无需转诊' }}</p>
              </div>
            </el-col>
          </el-row>
        </el-collapse-item>

        <!-- 检验指标可视化 -->
        <el-collapse-item v-if="report.triage && Object.keys(report.triage).length" name="indicators" title="">
          <template #title>
            <div class="collapse-title">
              <el-icon class="collapse-icon-danger"><TrendCharts /></el-icon>
              <span class="collapse-title-text">检验指标可视化</span>
            </div>
          </template>
          <div class="indicators-grid">
            <div
              v-for="(value, key) in report.triage"
              :key="key"
              class="indicator-item"
            >
              <span class="indicator-label">{{ formatKey(key) }}</span>
              <span class="indicator-value">{{ typeof value === 'object' ? JSON.stringify(value) : value }}</span>
            </div>
          </div>
        </el-collapse-item>

        <!-- 匹配疾病列表 -->
        <el-collapse-item v-if="report.matched_diseases?.length" name="matched" title="">
          <template #title>
            <div class="collapse-title">
              <el-icon class="collapse-icon-primary"><List /></el-icon>
              <span class="collapse-title-text">匹配疾病列表 ({{ report.matched_diseases.length }})</span>
            </div>
          </template>
          <el-table :data="report.matched_diseases" stripe>
            <el-table-column label="疾病" min-width="200">
              <template #default="{ row }">
                {{ typeof row === 'string' ? row : row.disease || row }}
              </template>
            </el-table-column>
            <el-table-column label="置信度" width="150" v-if="typeof report.matched_diseases[0] === 'object'">
              <template #default="{ row }">
                <el-tag v-if="row.confidence" :type="getConfidenceLevelType(row.confidence)" size="small">
                  {{ (row.confidence * 100).toFixed(0) }}%
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-collapse-item>
      </el-collapse>
    </template>

    <!-- ==================== TRIAGE_RECOMMENDATION 补检建议报告 ==================== -->
    <template v-if="report.report_type === 'TRIAGE_RECOMMENDATION'">
      <el-collapse v-model="activeSections" class="report-collapse">
        <!-- 患者主诉 -->
        <el-collapse-item name="complaint" title="">
          <template #title>
            <div class="collapse-title-primary">
              <el-icon class="collapse-icon-info"><User /></el-icon>
              <span class="collapse-title-text">患者主诉</span>
            </div>
          </template>
          <div class="complaint-content">
            <el-descriptions :column="1" border>
              <el-descriptions-item label="主诉">
                {{ props.chiefComplaint || '暂无主诉信息' }}
              </el-descriptions-item>
            </el-descriptions>
          </div>
        </el-collapse-item>

        <!-- 初步诊断 -->
        <el-collapse-item v-if="report.diagnosis" name="primary_diagnosis" title="">
          <template #title>
            <div class="collapse-title-primary">
              <el-icon class="collapse-icon-success"><CircleCheckFilled /></el-icon>
              <span class="collapse-title-text">初步诊断</span>
            </div>
          </template>
          <div class="diagnosis-highlight">
            <div class="diagnosis-main">
              <h2>{{ typeof report.diagnosis === 'string' ? report.diagnosis : report.diagnosis?.disease }}</h2>
              <el-tag v-if="typeof report.diagnosis === 'object' && report.diagnosis" size="large">
                置信度 {{ ((report.diagnosis.confidence || report.confidence) * 100).toFixed(1) }}%
              </el-tag>
              <el-tag v-else type="warning" size="large">
                置信度 {{ (report.confidence * 100).toFixed(1) }}%
              </el-tag>
            </div>
            <p v-if="report.uncertainty_reason" class="diagnosis-message">
              <el-icon><WarningFilled /></el-icon>
              当前诊断存在不确定性，建议补充关键检查项目以明确病因
            </p>
          </div>
        </el-collapse-item>

        <!-- 鉴别诊断 -->
        <el-collapse-item v-if="report.differential_diagnosis?.length" name="differential" title="">
          <template #title>
            <div class="collapse-title">
              <el-icon class="collapse-icon-info"><List /></el-icon>
              <span class="collapse-title-text">鉴别诊断 ({{ report.differential_diagnosis.length }})</span>
            </div>
          </template>
          <el-table :data="report.differential_diagnosis" stripe>
            <el-table-column label="疑似疾病" min-width="200">
              <template #default="{ row }">
                <strong>{{ typeof row === 'string' ? row : row.disease || row }}</strong>
              </template>
            </el-table-column>
            <el-table-column label="置信度" width="150" v-if="typeof report.differential_diagnosis[0] === 'object'">
              <template #default="{ row }">
                <el-progress
                  :percentage="Math.round((row.confidence || 0) * 100)"
                  :color="getConfidenceColor(row.confidence)"
                  :stroke-width="12"
                />
              </template>
            </el-table-column>
          </el-table>
        </el-collapse-item>

        <!-- LLM 临床分析 -->
        <el-collapse-item v-if="report.clinical_analysis" name="analysis" title="">
          <template #title>
            <div class="collapse-title">
              <el-icon class="collapse-icon-info"><EditPen /></el-icon>
              <span class="collapse-title-text">LLM 临床分析</span>
            </div>
          </template>
          <div class="analysis-content">
            <div class="analysis-text">{{ report.clinical_analysis }}</div>
          </div>
        </el-collapse-item>

        <!-- 推荐检查项目 -->
        <el-collapse-item v-if="report.recommended_tests?.length" name="tests" title="">
          <template #title>
            <div class="collapse-title">
              <el-icon class="collapse-icon-primary"><Document /></el-icon>
              <span class="collapse-title-text">推荐检查项目 ({{ report.recommended_tests.length }})</span>
            </div>
          </template>
          <div class="tests-grid">
            <div
              v-for="(test, idx) in report.recommended_tests"
              :key="idx"
              class="test-card"
            >
              <div class="test-number">{{ idx + 1 }}</div>
              <div class="test-content">
                <h4>{{ typeof test === 'string' ? test : test.test }}</h4>
                <p v-if="typeof test === 'object' && test.purpose">{{ test.purpose }}</p>
                <p v-else>用于进一步确认诊断方向</p>
              </div>
            </div>
          </div>
        </el-collapse-item>

        <!-- 缺失数据 -->
        <el-collapse-item v-if="report.missing_critical?.length || report.missing_recommended?.length" name="missing" title="">
          <template #title>
            <div class="collapse-title">
              <el-icon class="collapse-icon-danger"><CircleCloseFilled /></el-icon>
              <span class="collapse-title-text">缺失数据</span>
            </div>
          </template>
          <el-row :gutter="20">
            <el-col :xs="24" :md="12" v-if="report.missing_critical?.length">
              <div class="missing-card critical">
                <h4>关键缺失数据</h4>
                <ul>
                  <li v-for="(item, idx) in report.missing_critical" :key="idx">{{ item }}</li>
                </ul>
              </div>
            </el-col>
            <el-col :xs="24" :md="12" v-if="report.missing_recommended?.length">
              <div class="missing-card recommended">
                <h4>推荐补充数据</h4>
                <ul>
                  <li v-for="(item, idx) in report.missing_recommended" :key="idx">{{ item }}</li>
                </ul>
              </div>
            </el-col>
          </el-row>
        </el-collapse-item>
      </el-collapse>
    </template>

    <!-- ==================== FINAL_DIAGNOSIS MDT终局诊断报告 ==================== -->
    <template v-if="report.report_type === 'FINAL_DIAGNOSIS'">
      <el-collapse v-model="activeSections" class="report-collapse">
        <!-- 临床总结 -->
        <el-collapse-item v-if="report.clinical_summary" name="summary" title="">
          <template #title>
            <div class="collapse-title">
              <el-icon class="collapse-icon-primary"><EditPen /></el-icon>
              <span class="collapse-title-text">临床总结</span>
            </div>
          </template>
          <div class="summary-content">
            <div class="summary-text">{{ report.clinical_summary }}</div>
          </div>
        </el-collapse-item>

        <!-- 诊断结论 -->
        <el-collapse-item v-if="report.diagnosis" name="diagnosis" title="">
          <template #title>
            <div class="collapse-title-primary">
              <el-icon class="collapse-icon-success"><CircleCheckFilled /></el-icon>
              <span class="collapse-title-text">诊断结论</span>
            </div>
          </template>
          <div class="diagnosis-highlight">
            <h2>{{ typeof report.diagnosis === 'string' ? report.diagnosis : report.diagnosis?.disease }}</h2>
            <p v-if="report.message">{{ report.message }}</p>
          </div>
        </el-collapse-item>

        <!-- 鉴别诊断 -->
        <el-collapse-item v-if="report.differential_diagnosis?.length" name="differential" title="">
          <template #title>
            <div class="collapse-title">
              <el-icon class="collapse-icon-info"><List /></el-icon>
              <span class="collapse-title-text">鉴别诊断 (Top {{ report.differential_diagnosis.length }})</span>
            </div>
          </template>
          <el-table :data="report.differential_diagnosis" stripe>
            <el-table-column label="疾病" min-width="150">
              <template #default="{ row }">
                <strong>{{ typeof row === 'string' ? row : row.disease || row }}</strong>
              </template>
            </el-table-column>
            <el-table-column label="置信度" width="150" v-if="typeof report.differential_diagnosis[0] === 'object'">
              <template #default="{ row }">
                <el-progress
                  :percentage="Math.round((row.confidence || 0) * 100)"
                  :color="getConfidenceColor(row.confidence)"
                  :stroke-width="12"
                />
              </template>
            </el-table-column>
            <el-table-column prop="source" label="来源" width="120" v-if="typeof report.differential_diagnosis[0] === 'object'" />
            <el-table-column label="证据" min-width="200" v-if="typeof report.differential_diagnosis[0] === 'object'">
              <template #default="{ row }">
                <el-tag
                  v-for="(ev, idx) in (row.supporting_evidence || []).slice(0, 3)"
                  :key="idx"
                  size="small"
                  class="evidence-tag"
                >
                  {{ ev }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-collapse-item>

        <!-- 证伪日志 -->
        <el-collapse-item v-if="report.falsification_log?.length" name="falsification" title="">
          <template #title>
            <div class="collapse-title">
              <el-icon class="collapse-icon-danger"><CircleCloseFilled /></el-icon>
              <span class="collapse-title-text">证伪日志 (已排除 {{ report.falsification_log.filter((e: any) => e.falsified).length }} 项)</span>
            </div>
          </template>
          <el-timeline>
            <el-timeline-item
              v-for="(entry, idx) in report.falsification_log"
              :key="idx"
              :type="entry.falsified ? 'danger' : 'success'"
              :timestamp="entry.hypothesis"
              placement="top"
            >
              <el-card shadow="hover">
                <div class="falsification-detail">
                  <div class="falsification-header">
                    <el-tag :type="entry.falsified ? 'danger' : 'success'" size="small">
                      {{ entry.falsified ? '已排除' : '保留' }}
                    </el-tag>
                    <span class="contradiction-score">
                      矛盾评分: {{ (entry.contradiction_score * 100).toFixed(1) }}%
                    </span>
                  </div>
                  <p v-if="entry.recommendation">
                    <strong>建议:</strong> {{ entry.recommendation }}
                  </p>
                  <p v-if="entry.contradicting_evidence?.length">
                    <strong>矛盾证据:</strong> {{ entry.contradicting_evidence.join('；') }}
                  </p>
                </div>
              </el-card>
            </el-timeline-item>
          </el-timeline>
        </el-collapse-item>

        <!-- MDT 辩论过程 -->
        <el-collapse-item v-if="report.debate_process" name="debate" title="">
          <template #title>
            <div class="collapse-title">
              <el-icon class="collapse-icon-primary"><ChatDotRound /></el-icon>
              <span class="collapse-title-text">MDT 辩论过程 ({{ report.debate_process.round_number }} 轮)</span>
            </div>
          </template>
          <el-tabs type="border-card">
            <el-tab-pane label="共识点">
              <ul v-if="report.debate_process.consensus_points?.length">
                <li v-for="(point, idx) in report.debate_process.consensus_points" :key="idx">{{ point }}</li>
              </ul>
              <el-empty v-else description="暂无共识" :image-size="80" />
            </el-tab-pane>
            <el-tab-pane label="分歧点">
              <ul v-if="report.debate_process.disagreements?.length">
                <li v-for="(disagreement, idx) in report.debate_process.disagreements" :key="idx">{{ disagreement }}</li>
              </ul>
              <el-empty v-else description="暂无分歧" :image-size="80" />
            </el-tab-pane>
            <el-tab-pane label="辩论消息">
              <el-timeline>
                <el-timeline-item
                  v-for="(msg, idx) in report.debate_process.messages?.slice(0, 10)"
                  :key="idx"
                  :type="getMessageType(msg.message_type)"
                >
                  <strong>{{ msg.sender }}</strong> [{{ msg.message_type }}]
                  <p>{{ msg.content }}</p>
                </el-timeline-item>
              </el-timeline>
            </el-tab-pane>
          </el-tabs>
        </el-collapse-item>

        <!-- 指南校验 -->
        <el-collapse-item v-if="report.guideline_check" name="guideline" title="">
          <template #title>
            <div class="collapse-title">
              <el-icon class="collapse-icon-success"><Checked /></el-icon>
              <span class="collapse-title-text">指南符合性校验</span>
            </div>
          </template>
          <el-alert
            :title="report.guideline_check.compliant ? '符合临床指南' : '不符合临床指南'"
            :type="report.guideline_check.compliant ? 'success' : 'warning'"
            :description="report.guideline_check.recommendation"
            :closable="false"
            show-icon
          />
          <el-descriptions :column="1" border style="margin-top: 15px">
            <el-descriptions-item label="诊断">{{ report.guideline_check.diagnosis }}</el-descriptions-item>
            <el-descriptions-item label="符合标准">
              <el-tag v-for="(c, i) in report.guideline_check.met_criteria" :key="i" type="success" size="small">{{ c }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="缺失标准">
              <el-tag v-for="(c, i) in report.guideline_check.missing_criteria" :key="i" type="danger" size="small">{{ c }}</el-tag>
            </el-descriptions-item>
          </el-descriptions>
        </el-collapse-item>

        <!-- HITL 问题 -->
        <el-collapse-item v-if="report.hitl_status === 'interrupted' && report.hitl_questions?.length" name="hitl" title="">
          <template #title>
            <div class="collapse-title">
              <el-icon class="collapse-icon-warning"><QuestionFilled /></el-icon>
              <span class="collapse-title-text">需要补充的信息 (HITL)</span>
            </div>
          </template>
          <el-alert
            title="系统需要更多关键信息以完成诊断"
            type="warning"
            :closable="false"
            show-icon
            style="margin-bottom: 15px"
          />
          <el-timeline>
            <el-timeline-item
              v-for="(q, idx) in report.hitl_questions"
              :key="idx"
              :type="getQuestionPriorityType(q.priority)"
            >
              <strong>{{ q.question }}</strong>
              <p>理由: {{ q.rationale }}</p>
              <p>优先级: {{ getPriorityText(q.priority) }}</p>
            </el-timeline-item>
          </el-timeline>
        </el-collapse-item>

        <!-- 知识图谱 -->
        <el-collapse-item v-if="report.knowledge_graph && Object.keys(report.knowledge_graph).length" name="graph" title="">
          <template #title>
            <div class="collapse-title">
              <el-icon class="collapse-icon-info"><Share /></el-icon>
              <span class="collapse-title-text">知识图谱检索结果</span>
            </div>
          </template>
          <div class="graph-weights">
            <div
              v-for="(value, key) in report.knowledge_graph"
              :key="key"
              class="weight-item"
            >
              <span class="weight-label">{{ key }}</span>
              <el-progress
                :percentage="Math.min(Math.round(typeof value === 'number' ? value * 100 : 50), 100)"
                :stroke-width="10"
                :show-text="false"
              />
              <span class="weight-value">{{ typeof value === 'number' ? (value * 100).toFixed(0) + '%' : String(value) }}</span>
            </div>
          </div>
        </el-collapse-item>
      </el-collapse>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, defineProps, defineEmits } from 'vue'
import type { FinalReport } from '@/types'
import {
  SuccessFilled, WarningFilled, InfoFilled, Document, Download, RefreshRight,
  EditPen, List, CircleCloseFilled, ChatDotRound, Checked, QuestionFilled, Share,
  User, Clock, BellFilled, Aim, DataAnalysis, Compass, TrendCharts,
  CircleCheckFilled, FirstAidKit, Link, Tickets
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const props = defineProps<{
  report: FinalReport | null
  chiefComplaint?: string
}>()

const emit = defineEmits<{
  export: []
  newDiagnosis: []
}>()

const activeSections = ref<string[]>([])

const getReportTitle = () => {
  if (!props.report) return '诊断报告'
  switch (props.report.report_type) {
    case 'COMMON_DIAGNOSIS': return '常见病确诊报告'
    case 'TRIAGE_RECOMMENDATION': return '补检建议报告'
    case 'FINAL_DIAGNOSIS': return 'MDT 深度诊断报告'
    default: return '诊断报告'
  }
}

const getReportSubtitle = () => {
  if (!props.report) return ''
  const subtitles: Record<string, string> = {
    COMMON_DIAGNOSIS: '基于规则引擎与临床指南的快速确诊',
    TRIAGE_RECOMMENDATION: '数据不足，建议补充关键检查项目',
    FINAL_DIAGNOSIS: '多学科对抗推理深度诊断报告',
  }
  return subtitles[props.report.report_type] || ''
}

const getHeroTheme = () => {
  if (!props.report) return 'default'
  if (props.report.report_type === 'COMMON_DIAGNOSIS') return 'success'
  if (props.report.report_type === 'TRIAGE_RECOMMENDATION') return 'warning'
  if (props.report.report_type === 'FINAL_DIAGNOSIS') return 'info'
  return 'default'
}

const getHeroIcon = () => {
  if (!props.report) return InfoFilled
  switch (props.report.report_type) {
    case 'COMMON_DIAGNOSIS': return CircleCheckFilled
    case 'TRIAGE_RECOMMENDATION': return WarningFilled
    case 'FINAL_DIAGNOSIS': return SuccessFilled
    default: return InfoFilled
  }
}

const getStatusType = () => {
  if (!props.report) return 'info'
  return props.report.status === 'CONCLUSIVE' ? 'success' : 'warning'
}

const getConfidenceLevelClass = () => {
  if (!props.report) return ''
  const c = props.report.confidence
  if (c >= 0.8) return 'level-high'
  if (c >= 0.6) return 'level-medium'
  return 'level-low'
}

const getPathType = () => {
  if (!props.report) return 'info'
  switch (props.report.path) {
    case 'common_fast_path': case 'common': return 'success'
    case 'rare_deep_path': case 'rare': return 'danger'
    default: return 'warning'
  }
}

const getPathText = () => {
  if (!props.report) return '未知'
  switch (props.report.path) {
    case 'common_fast_path': case 'common': return '常见病快速通道'
    case 'rare_deep_path': case 'rare': return '罕见病深度诊断'
    default: return '不确定/需补检'
  }
}

const getPathDescription = () => {
  if (!props.report) return ''
  switch (props.report.path) {
    case 'common_fast_path': case 'common': return '标准诊疗流程'
    case 'rare_deep_path': case 'rare': return '需要专科评估'
    default: return '数据不足'
  }
}

const getConfidenceColor = (confidence: number) => {
  if (confidence >= 0.8) return '#67C23A'
  if (confidence >= 0.6) return '#E6A23C'
  return '#F56C6C'
}

const getConfidenceLevelType = (confidence: number) => {
  if (confidence >= 0.8) return 'success'
  if (confidence >= 0.6) return 'warning'
  return 'danger'
}

const getUrgencyType = () => {
  if (!props.report) return 'info'
  switch (props.report.urgency) {
    case 'emergency': return 'danger'
    case 'urgent': return 'warning'
    default: return 'success'
  }
}

const getUrgencyText = () => {
  if (!props.report) return '未知'
  switch (props.report.urgency) {
    case 'emergency': return '急诊'
    case 'urgent': return '加急'
    default: return '常规'
  }
}

const getUrgencyDescription = () => {
  if (!props.report) return ''
  switch (props.report.urgency) {
    case 'emergency': return '立即处理'
    case 'urgent': return '尽快处理'
    default: return '按计划处理'
  }
}

const getDataCompletenessColor = () => {
  if (!props.report) return '#F56C6C'
  const c = props.report.data_completeness_score
  if (c >= 0.8) return '#67C23A'
  if (c >= 0.6) return '#E6A23C'
  return '#F56C6C'
}

const getDataCompletenessLabel = () => {
  if (!props.report) return ''
  const c = props.report.data_completeness_score
  if (c >= 0.8) return '数据充足'
  if (c >= 0.6) return '数据基本充足'
  return '数据不足'
}

const getMessageType = (type: string) => {
  switch (type) {
    case 'propose': return 'primary'
    case 'agree': case 'accept': return 'success'
    case 'reject': return 'danger'
    case 'query': return 'warning'
    default: return 'info'
  }
}

const getQuestionPriorityType = (priority: string) => {
  switch (priority) {
    case 'critical': return 'danger'
    case 'high': return 'warning'
    case 'medium': return 'primary'
    default: return 'info'
  }
}

const getPriorityText = (priority: string) => {
  switch (priority) {
    case 'critical': return '关键'
    case 'high': return '高'
    case 'medium': return '中'
    case 'low': return '低'
    default: return priority
  }
}

const formatKey = (key: string) => {
  return key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
}

const exportAsJSON = () => {
  if (!props.report) return
  const blob = new Blob([JSON.stringify(props.report, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `diagnosis_${props.report.patient_id}_${Date.now()}.json`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('JSON 报告已导出')
}

const exportAsText = () => {
  if (!props.report) return
  const text = JSON.stringify(props.report, null, 2)
  const blob = new Blob([text], { type: 'text/plain' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `diagnosis_${props.report.patient_id}_${Date.now()}.txt`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('TXT 报告已导出')
}

const exportAsPDF = () => {
  ElMessage.info('PDF 导出功能开发中')
}
</script>

<style scoped lang="scss">
.medical-report {
  max-width: 1400px;
  margin: 0 auto;
  padding: 20px;
}

// 导航栏
.report-nav {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  background: white;
  border-radius: 8px;
  margin-bottom: 20px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}

// Hero 区域
.report-hero {
  border-radius: 12px;
  padding: 32px;
  margin-bottom: 24px;
  color: white;
  position: relative;
  overflow: hidden;

  &::before {
    content: '';
    position: absolute;
    top: -50%;
    right: -20%;
    width: 400px;
    height: 400px;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.08);
  }

  &::after {
    content: '';
    position: absolute;
    bottom: -30%;
    left: -10%;
    width: 300px;
    height: 300px;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.05);
  }

  &.hero-success {
    background: linear-gradient(135deg, #67C23A 0%, #529b2e 100%);
  }

  &.hero-warning {
    background: linear-gradient(135deg, #E6A23C 0%, #d4932e 100%);
  }

  &.hero-info {
    background: linear-gradient(135deg, #409EFF 0%, #337ecc 100%);
  }

  .hero-content {
    display: flex;
    align-items: center;
    gap: 24px;
    position: relative;
    z-index: 1;

    .hero-badge {
      width: 64px;
      height: 64px;
      border-radius: 16px;
      background: rgba(255, 255, 255, 0.2);
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
    }

    .hero-text {
      flex: 1;

      .hero-title {
        margin: 0;
        font-size: 28px;
        font-weight: 700;
        letter-spacing: -0.5px;
      }

      .hero-subtitle {
        margin: 6px 0 0;
        font-size: 14px;
        opacity: 0.85;
      }
    }

    .hero-meta {
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      gap: 8px;

      .meta-item {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 13px;
        opacity: 0.9;
      }
    }
  }
}

// 指标仪表盘
.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.metric-card {
  background: white;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
  transition: transform 0.2s, box-shadow 0.2s;

  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  }

  .metric-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;

    .metric-label {
      font-size: 13px;
      color: #909399;
      font-weight: 500;
    }

    .el-icon {
      color: #C0C4CC;
    }
  }

  .metric-value {
    font-size: 32px;
    font-weight: 700;
    color: #303133;
    margin-bottom: 8px;
  }

  .metric-footer {
    margin-top: 12px;
    font-size: 12px;
    color: #909399;
  }

  &.level-high .metric-value { color: #67C23A; }
  &.level-medium .metric-value { color: #E6A23C; }
  &.level-low .metric-value { color: #F56C6C; }
}

// 折叠面板
.report-collapse {
  background: white;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}

.collapse-title-primary,
.collapse-title {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 0;
}

.collapse-icon-success { color: #67C23A; font-size: 20px; }
.collapse-icon-info { color: #409EFF; font-size: 20px; }
.collapse-icon-primary { color: #909399; font-size: 20px; }
.collapse-icon-warning { color: #E6A23C; font-size: 20px; }
.collapse-icon-danger { color: #F56C6C; font-size: 20px; }

.collapse-title-text {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

// 诊断高亮
.diagnosis-highlight {
  padding: 24px;
  background: #f0f9eb;
  border-radius: 8px;
  border-left: 4px solid #67C23A;

  .diagnosis-main {
    display: flex;
    align-items: center;
    gap: 16px;
    margin-bottom: 12px;

    h2 {
      margin: 0;
      font-size: 24px;
      color: #303133;
    }
  }

  .diagnosis-message {
    margin: 0;
    color: #606266;
    line-height: 1.6;
  }
}

// 临床推理
.reasoning-content,
.analysis-content,
.summary-content {
  padding: 20px;
}

.reasoning-text,
.analysis-text,
.summary-text {
  line-height: 1.8;
  color: #606266;
  white-space: pre-wrap;
  padding: 16px;
  background: #f5f7fa;
  border-radius: 8px;
  border-left: 4px solid #409EFF;
}

// 治疗方案
.treatment-card {
  padding: 20px;
  background: #f5f7fa;
  border-radius: 8px;
  margin-bottom: 12px;

  h4 {
    margin: 0 0 10px;
    color: #409EFF;
    font-size: 15px;
  }

  p {
    margin: 0;
    color: #606266;
    line-height: 1.6;
  }
}

// 指标网格
.indicators-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
  padding: 20px;
}

.indicator-item {
  display: flex;
  flex-direction: column;
  padding: 12px;
  background: #f5f7fa;
  border-radius: 8px;

  .indicator-label {
    font-size: 12px;
    color: #909399;
    margin-bottom: 4px;
  }

  .indicator-value {
    font-size: 16px;
    font-weight: 600;
    color: #303133;
  }
}

// 检查项目
.tests-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
  padding: 20px;
}

.test-card {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 16px;
  background: #f5f7fa;
  border-radius: 8px;
  transition: background 0.2s;

  &:hover {
    background: #ecf5ff;
  }

  .test-number {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: #409EFF;
    color: white;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 14px;
    flex-shrink: 0;
  }

  .test-content {
    h4 {
      margin: 0 0 4px;
      color: #303133;
      font-size: 15px;
    }

    p {
      margin: 0;
      color: #909399;
      font-size: 13px;
    }
  }
}

// 缺失数据
.missing-card {
  padding: 20px;
  border-radius: 8px;
  margin-bottom: 12px;

  &.critical {
    background: #fef0f0;
    border-left: 4px solid #F56C6C;
  }

  &.recommended {
    background: #fdf6ec;
    border-left: 4px solid #E6A23C;
  }

  h4 {
    margin: 0 0 12px;
    font-size: 15px;
  }

  ul {
    margin: 0;
    padding-left: 20px;

    li {
      margin: 6px 0;
      color: #606266;
    }
  }
}

// 证伪详情
.falsification-detail {
  .falsification-header {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 8px;
  }

  .contradiction-score {
    font-size: 13px;
    color: #909399;
  }

  p {
    margin: 6px 0;
    color: #606266;
    font-size: 14px;
  }
}

// 知识图谱权重
.graph-weights {
  padding: 20px;
}

.weight-item {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 12px;

  .weight-label {
    width: 120px;
    font-size: 13px;
    color: #606266;
    flex-shrink: 0;
    text-align: right;
  }

  .el-progress {
    flex: 1;
  }

  .weight-value {
    width: 50px;
    font-size: 13px;
    color: #909399;
    text-align: right;
  }
}

// 证据标签
.evidence-tag {
  margin: 2px 6px 2px 0;
}

// 响应式
@media (max-width: 768px) {
  .medical-report {
    padding: 10px;
  }

  .hero-content {
    flex-direction: column;
    align-items: flex-start !important;
    gap: 16px;

    .hero-meta {
      align-items: flex-start !important;
    }
  }

  .dashboard-grid {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 480px) {
  .dashboard-grid {
    grid-template-columns: 1fr;
  }

  .report-nav {
    flex-direction: column;
    gap: 12px;
  }
}
</style>
