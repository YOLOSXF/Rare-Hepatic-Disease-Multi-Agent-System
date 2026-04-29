/**
 * 诊断相关 API 接口
 * 对接后端 /api/v1/diagnose/ 和 /api/v1/diagnose/screen
 */
import request from './request'
import type { PatientData, DiagnosisResponse } from '@/types'

/**
 * 提交完整诊断请求 (L1-L5)
 * @param patientData 患者数据
 * @returns 诊断响应 (可能包含 HITL 中断信息)
 */
export const submitDiagnosis = async (patientData: PatientData): Promise<DiagnosisResponse> => {
  const response = await request.post('/diagnose/', {
    patient_id: patientData.patient_id,
    chief_complaint: patientData.chief_complaint,
    age: patientData.age,
    gender: patientData.gender,
    medical_history: patientData.history || {},
    lab_results: patientData.labs || {},
    imaging_results: patientData.ultrasound || {},
    family_history: [],  // 可选字段
    medication_history: patientData.history?.medications || [],
    alcohol_intake: patientData.history?.alcohol_intake_weekly,
  })
  return response
}

/**
 * 快速筛查 (L1-L2 轻量级)
 * @param patientData 患者数据
 * @returns 诊断响应
 */
export const quickScreen = async (patientData: PatientData): Promise<DiagnosisResponse> => {
  const response = await request.post('/diagnose/screen', {
    patient_id: patientData.patient_id,
    chief_complaint: patientData.chief_complaint,
    age: patientData.age,
    gender: patientData.gender,
    medical_history: patientData.history || {},
    lab_results: patientData.labs || {},
    imaging_results: patientData.ultrasound || {},
    family_history: [],
    medication_history: patientData.history?.medications || [],
    alcohol_intake: patientData.history?.alcohol_intake_weekly,
  })
  return response
}

/**
 * HITL 恢复接口 (补充数据后继续诊断)
 * @param threadId 会话ID
 * @param answers 患者补充答案
 * @returns 恢复后的诊断结果
 */
export const resumeDiagnosis = async (threadId: string, answers: Record<string, any>): Promise<any> => {
  const response = await request.post(`/hitl/resume/${threadId}`, answers)
  return response
}

/**
 * 获取健康检查状态
 */
export const healthCheck = async (): Promise<any> => {
  const response = await request.get('/health')
  return response
}
