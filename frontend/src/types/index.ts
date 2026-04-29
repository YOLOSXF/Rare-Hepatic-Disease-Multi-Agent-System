/**
 * 类型定义文件 - 与后端 state_definition.py 和 graph_orchestrator.py 完全对齐
 * 基于三种报告类型：CommonDiagnosisReport, TriageRecommendationReport, MDTFinalReport
 */

// ==================== 患者输入数据 (对接 PatientInput + PatientData) ====================

export interface PatientData {
  patient_id: string                    // 患者ID (必填)
  age?: number                          // 年龄
  gender?: string                       // 性别
  chief_complaint: string               // 主诉 (必填)
  bmi?: number                          // BMI指数
  history?: MedicalHistory              // 既往史
  symptoms?: Record<string, boolean>    // 症状字典
  labs?: Record<string, any>            // 检验结果
  ultrasound?: Record<string, any>      // 超声检查
  ct?: Record<string, any>              // CT检查
  mri?: Record<string, any>             // MRI检查
  eye_exam?: Record<string, any>        // 眼科检查
}

export interface MedicalHistory {
  alcohol_intake?: number               // 饮酒量 (g/天)
  alcohol_intake_weekly?: number        // 每周饮酒量
  smoking?: boolean                     // 是否吸烟
  diabetes?: boolean                    // 糖尿病史
  hypertension?: boolean                // 高血压史
  family_liver_disease?: boolean        // 家族肝病史
  medications?: string[]                // 用药史
  allergies?: string[]                  // 过敏史
}

// ==================== 分诊结果 ====================

export interface TriageResult {
  path: string                          // common_fast_path / rare_deep_path / uncertain / insufficient_data
  diagnosis?: string                    // 诊断结果
  confidence: number                    // 置信度 (0-1)
  confidence_level: string              // high / medium / low
  is_rare_disease_alert: boolean        // 是否罕见病预警
  urgency: string                       // routine / urgent / emergency
  recommended_tests: string[]           // 推荐检查项目
  uncertainty_reason?: string           // 不确定原因
  matched_diseases?: string[]           // 匹配的疾病列表
}

// ==================== 诊断假设 ====================

export interface DiagnosticHypothesis {
  disease: string                       // 疾病名称
  confidence: number                    // 置信度
  supporting_evidence: string[]         // 支持证据
  opposing_evidence: string[]           // 反对证据
  source: string                        // 来源
  guidelines: string[]                  // 相关指南
}

// ==================== 证伪条目 ====================

export interface FalsificationEntry {
  hypothesis: string                    // 假设疾病
  falsified: boolean                    // 是否被证伪
  contradiction_score: number           // 矛盾评分
  contradicting_evidence: string[]      // 矛盾证据
  supporting_evidence: string[]         // 支持证据
  recommendation: string                // 建议
}

// ==================== 指南校验结果 ====================

export interface GuidelineCheckResult {
  diagnosis: string                     // 诊断疾病
  compliant: boolean                    // 是否符合指南
  missing_criteria: string[]            // 缺失标准
  met_criteria: string[]                // 符合标准
  recommendation: string                // 建议
}

// ==================== 辩论状态 ====================

export interface DebateMessage {
  message_type: string                  // propose/cfp/reject/accept/inform/query/agreement
  sender: string                        // 发送者
  content: string                       // 内容
  evidence: string[]                    // 证据
}

export interface DebateState {
  round_number: number                  // 轮次
  messages: DebateMessage[]             // 消息列表
  consensus_points: string[]            // 共识点
  disagreements: string[]               // 分歧点
  all_perspectives: any[]               // 所有观点
}

// ==================== HITL 追问问题 ====================

export interface Question {
  field: string                         // 字段
  question: string                      // 问题
  rationale: string                     // 理由
  priority: string                      // critical/high/medium/low
  related_disease?: string              // 相关疾病
  recommended_test?: string             // 推荐检查
}

// ==================== 报告基础字段 (ReportBase) ====================

export interface ReportBase {
  report_type: string                   // COMMON_DIAGNOSIS / TRIAGE_RECOMMENDATION / FINAL_DIAGNOSIS
  report_version: string                // llm_enhanced_v1 / rule_based_v1
  status: string                        // CONCLUSIVE / INCONCLUSIVE
  patient_id: string                    // 患者ID
  path: string                          // common / rare / uncertain
  diagnosis: string | DiagnosticHypothesis | null  // 诊断结论
  confidence: number                    // 置信度 (0-1)
  confidence_level: string              // high / medium / low
  is_rare_disease_alert: boolean        // 罕见病预警
  urgency: string                       // routine / urgent / emergency
  triage: Record<string, any>           // 分诊结果
  data_completeness_score: number       // 数据完整度评分
}

// ==================== L5a: 常见病确诊报告 ====================

export interface CommonDiagnosisReport extends ReportBase {
  report_type: 'COMMON_DIAGNOSIS'
  follow_up_plan?: string               // 随访计划
  referral_recommendation?: any         // 转诊建议 (字符串或对象)
  recommended_tests: string[]           // 推荐检查
  matched_diseases: any[]               // 匹配的疾病
  clinical_reasoning?: string           // 临床推理 (LLM生成)
  message?: string                      // 附加消息
}

// ==================== L5b: 补检建议报告 ====================

export interface RecommendedTest {
  test: string                          // 检查项目名称
  purpose: string                       // 检查目的说明
}

export interface TriageRecommendationReport extends ReportBase {
  report_type: 'TRIAGE_RECOMMENDATION'
  uncertainty_reason?: string           // 不确定原因
  differential_diagnosis: any[]         // 鉴别诊断列表
  recommended_tests: (string | RecommendedTest)[]  // 推荐检查 (字符串或对象)
  missing_critical: string[]            // 缺失的关键数据
  missing_recommended: string[]         // 缺失的推荐数据
  clinical_analysis?: string            // 临床分析 (LLM生成)
  message?: string                      // 附加消息
}

// ==================== L5c: MDT终局诊断报告 ====================

export interface MDTFinalReport extends ReportBase {
  report_type: 'FINAL_DIAGNOSIS'
  differential_diagnosis: any[]         // 鉴别诊断列表
  referral: Record<string, any>         // 转诊决策
  debate_process?: DebateState | null   // 辩论过程
  falsification_log: any[]              // 证伪日志
  knowledge_graph: Record<string, number>  // 知识图谱权重
  memory_context?: Record<string, any> | null  // 记忆上下文
  guideline_check?: GuidelineCheckResult | null  // 指南校验
  hitl_questions: any[]                 // HITL问题列表
  hitl_status: string                   // HITL状态: normal/interrupted/resumed
  excluded_hypotheses: string[]         // 被排除的假设
  clinical_summary?: string             // 临床总结
}

// ==================== 联合类型 ====================

export type FinalReport = CommonDiagnosisReport | TriageRecommendationReport | MDTFinalReport

// ==================== API 请求/响应 (对接 DiagnosisResponse) ====================

export interface DiagnosisRequest {
  patient_id: string
  chief_complaint: string
  age?: number
  gender?: string
  lab_results?: Record<string, any>
  imaging_results?: Record<string, any>
  medical_history?: Record<string, any>
  family_history?: string[]
  medication_history?: string[]
  alcohol_intake?: number
}

export interface HITLInterruptedResponse {
  success: true
  patient_id: string
  hitl_status: 'interrupted'
  hitl_session_id: string
  hitl_questions: Question[]
  partial_diagnosis: any[]
  evidence_chain: any[]
}

export interface NormalDiagnosisResponse {
  success: true
  patient_id: string
  chief_complaint?: string
  primary_diagnosis?: string
  differential_diagnosis: string[]
  confidence_score: number
  referral_recommendation?: Record<string, any>
  evidence_chain: any[]
  follow_up_plan?: Record<string, any>
  metadata?: Record<string, any>
  debate_process?: DebateState
  falsification_log: FalsificationEntry[]
  guideline_check?: GuidelineCheckResult
  error?: string
}

export type DiagnosisResponse = HITLInterruptedResponse | NormalDiagnosisResponse

export interface ApiResponse<T> {
  success: boolean
  data?: T
  error?: string
  message?: string
}
