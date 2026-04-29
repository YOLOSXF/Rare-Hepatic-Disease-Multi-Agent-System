<template>
  <el-form
    ref="formRef"
    :model="formData"
    :rules="rules"
    label-width="140px"
    label-position="right"
    size="default"
    @submit.prevent="handleSubmit"
  >
    <!-- 基本信息 -->
    <el-divider content-position="left">
      <el-icon><User /></el-icon> 基本信息
    </el-divider>

    <el-row :gutter="20">
      <el-col :xs="24" :sm="12" :md="8">
        <el-form-item label="患者 ID" prop="patient_id">
          <el-input
            v-model="formData.patient_id"
            placeholder="请输入患者唯一ID"
            clearable
          />
        </el-form-item>
      </el-col>

      <el-col :xs="24" :sm="12" :md="8">
        <el-form-item label="年龄" prop="age">
          <el-input-number
            v-model="formData.age"
            :min="0"
            :max="150"
            :step="1"
            placeholder="年龄"
            style="width: 100%"
          />
        </el-form-item>
      </el-col>

      <el-col :xs="24" :sm="12" :md="8">
        <el-form-item label="性别" prop="gender">
          <el-select v-model="formData.gender" placeholder="请选择性别" clearable style="width: 100%">
            <el-option label="男" value="male" />
            <el-option label="女" value="female" />
            <el-option label="其他" value="other" />
          </el-select>
        </el-form-item>
      </el-col>
    </el-row>

    <el-row :gutter="20">
      <el-col :xs="24" :sm="12" :md="12">
        <el-form-item label="主诉" prop="chief_complaint">
          <el-input
            v-model="formData.chief_complaint"
            type="textarea"
            :rows="3"
            placeholder="请描述患者主要症状和就诊原因"
          />
        </el-form-item>
      </el-col>

      <el-col :xs="24" :sm="12" :md="12">
        <el-form-item label="BMI 指数" prop="bmi">
          <el-input-number
            v-model="formData.bmi"
            :min="10"
            :max="60"
            :step="0.1"
            :precision="1"
            placeholder="可选，自动计算"
            style="width: 100%"
          />
        </el-form-item>
      </el-col>
    </el-row>

    <!-- 既往史 -->
    <el-divider content-position="left">
      <el-icon><Document /></el-icon> 既往史
    </el-divider>

    <el-row :gutter="20">
      <el-col :xs="24" :sm="12" :md="8">
        <el-form-item label="每周饮酒量(g)">
          <el-input-number
            v-model="formData.history.alcohol_intake_weekly"
            :min="0"
            :step="10"
            placeholder="0"
            style="width: 100%"
          />
        </el-form-item>
      </el-col>

      <el-col :xs="24" :sm="12" :md="8">
        <el-form-item label="吸烟史">
          <el-switch
            v-model="formData.history.smoking"
            active-text="是"
            inactive-text="否"
          />
        </el-form-item>
      </el-col>

      <el-col :xs="24" :sm="12" :md="8">
        <el-form-item label="糖尿病史">
          <el-switch
            v-model="formData.history.diabetes"
            active-text="是"
            inactive-text="否"
          />
        </el-form-item>
      </el-col>
    </el-row>

    <el-row :gutter="20">
      <el-col :xs="24" :sm="12" :md="8">
        <el-form-item label="高血压史">
          <el-switch
            v-model="formData.history.hypertension"
            active-text="是"
            inactive-text="否"
          />
        </el-form-item>
      </el-col>

      <el-col :xs="24" :sm="12" :md="8">
        <el-form-item label="家族肝病史">
          <el-switch
            v-model="formData.history.family_liver_disease"
            active-text="是"
            inactive-text="否"
          />
        </el-form-item>
      </el-col>
    </el-row>

    <el-row :gutter="20">
      <el-col :span="24">
        <el-form-item label="用药史">
          <el-select
            v-model="formData.history.medications"
            multiple
            filterable
            allow-create
            default-first-option
            placeholder="输入或选择用药名称，回车添加"
            style="width: 100%"
          >
            <el-option
              v-for="item in commonMedications"
              :key="item"
              :label="item"
              :value="item"
            />
          </el-select>
        </el-form-item>
      </el-col>
    </el-row>

    <el-row :gutter="20">
      <el-col :span="24">
        <el-form-item label="过敏史">
          <el-select
            v-model="formData.history.allergies"
            multiple
            filterable
            allow-create
            default-first-option
            placeholder="输入或选择过敏原，回车添加"
            style="width: 100%"
          >
            <el-option
              v-for="item in commonAllergies"
              :key="item"
              :label="item"
              :value="item"
            />
          </el-select>
        </el-form-item>
      </el-col>
    </el-row>

    <!-- 症状 -->
    <el-divider content-position="left">
      <el-icon><WarningFilled /></el-icon> 症状（多选）
    </el-divider>

    <el-row :gutter="20">
      <el-col :xs="24" :sm="12" :md="8" v-for="symptom in symptomOptions" :key="symptom.value">
        <el-form-item>
          <el-checkbox v-model="formData.symptoms[symptom.value]" :label="symptom.label" />
        </el-form-item>
      </el-col>
    </el-row>

    <!-- 检验结果 -->
    <el-divider content-position="left">
      <el-icon><Histogram /></el-icon> 检验结果
    </el-divider>

    <el-row :gutter="20">
      <el-col :xs="24" :sm="12" :md="6" v-for="lab in labFields" :key="lab.key">
        <el-form-item :label="lab.label">
          <el-input
            v-model.number="formData.labs[lab.key]"
            :placeholder="lab.unit"
            clearable
          >
            <template #append>{{ lab.unit }}</template>
          </el-input>
        </el-form-item>
      </el-col>
    </el-row>

    <!-- 超声检查 -->
    <el-divider content-position="left">
      <el-icon><Monitor /></el-icon> 超声检查
    </el-divider>

    <el-row :gutter="20">
      <el-col :span="24">
        <el-form-item label="超声发现">
          <el-input
            v-model="formData.ultrasound.findings"
            type="textarea"
            :rows="3"
            placeholder="描述超声检查发现，如：脂肪肝回声、肝脏肿大等"
          />
        </el-form-item>
      </el-col>
    </el-row>

    <el-row :gutter="20">
      <el-col :xs="24" :sm="12" :md="8">
        <el-form-item label="肝脏大小">
          <el-input v-model="formData.ultrasound.liver_size" placeholder="如：正常、增大" />
        </el-form-item>
      </el-col>

      <el-col :xs="24" :sm="12" :md="8">
        <el-form-item label="回声特征">
          <el-select v-model="formData.ultrasound.echo_pattern" placeholder="请选择" clearable style="width: 100%">
            <el-option label="正常" value="normal" />
            <el-option label="脂肪肝回声" value="fatty" />
            <el-option label="回声增粗" value="coarse" />
            <el-option label="回声减低" value="decreased" />
          </el-select>
        </el-form-item>
      </el-col>
    </el-row>

    <!-- 提交按钮 -->
    <el-form-item>
      <el-button type="primary" @click="handleSubmit" :loading="loading" size="large" style="width: 200px">
        <el-icon v-if="!loading"><Promotion /></el-icon>
        {{ loading ? '诊断中...' : '提交诊断' }}
      </el-button>
      <el-button @click="handleReset" size="large">重置表单</el-button>
      <el-dropdown @command="handleFillTestCase" trigger="click">
        <el-button size="large" type="info">
          快速填充测试用例
          <el-icon class="el-icon--right"><arrow-down /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item
              v-for="tc in testCases"
              :key="tc.case_id"
              :command="tc.case_id"
            >
              <span style="display: flex; justify-content: space-between; align-items: center; width: 280px">
                <span>{{ tc.case_name }}</span>
                <el-tag size="small" :type="getCategoryTagType(tc.category)">{{ tc.category }}</el-tag>
              </span>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </el-form-item>
  </el-form>
</template>

<script setup lang="ts">
import { ref, reactive, defineEmits } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { User, Document, WarningFilled, Histogram, Monitor, Promotion, ArrowDown } from '@element-plus/icons-vue'
import type { PatientData, MedicalHistory } from '@/types'
import { ElMessage } from 'element-plus'

const emit = defineEmits<{
  submit: [data: PatientData]
}>()

const props = defineProps<{
  loading?: boolean
}>()

const formRef = ref<FormInstance>()

// 表单数据
const formData = reactive<PatientData>({
  patient_id: '',
  chief_complaint: '',
  age: undefined,
  gender: undefined,
  bmi: undefined,
  history: {
    alcohol_intake_weekly: undefined,
    smoking: false,
    diabetes: false,
    hypertension: false,
    family_liver_disease: false,
    medications: [],
    allergies: [],
  },
  symptoms: {
    fatigue: false,
    jaundice: false,
    abdominal_pain: false,
    nausea: false,
    vomiting: false,
    appetite_loss: false,
    weight_loss: false,
    fever: false,
    dark_urine: false,
    pale_stool: false,
    itching: false,
    abdominal_swelling: false,
  },
  labs: {
    alt: undefined,
    ast: undefined,
    alp: undefined,
    ggt: undefined,
    tbil: undefined,
    dbil: undefined,
    albumin: undefined,
    pt: undefined,
  },
  ultrasound: {
    findings: '',
    liver_size: '',
    echo_pattern: '',
  },
})

// 表单验证规则
const rules = reactive<FormRules>({
  patient_id: [
    { required: true, message: '请输入患者ID', trigger: 'blur' },
    { min: 2, max: 50, message: '长度在 2 到 50 个字符', trigger: 'blur' },
  ],
  chief_complaint: [
    { required: true, message: '请输入主诉', trigger: 'blur' },
    { min: 5, max: 500, message: '长度在 5 到 500 个字符', trigger: 'blur' },
  ],
  age: [
    { required: true, message: '请输入年龄', trigger: 'blur' },
    { type: 'number', min: 0, max: 150, message: '年龄必须在 0-150 之间', trigger: 'blur' },
  ],
  gender: [
    { required: true, message: '请选择性别', trigger: 'change' },
  ],
})

// 常用药物列表
const commonMedications = [
  '阿司匹林', '二甲双胍', '阿托伐他汀', '恩替卡韦', '替诺福韦',
  '甘草酸制剂', '水飞蓟素', '熊去氧胆酸', '胰岛素', '降压药',
]

// 常见过敏原
const commonAllergies = [
  '青霉素', '磺胺类', '碘造影剂', '花粉', '尘螨',
  '海鲜', '花生', '牛奶', '鸡蛋', '乳胶',
]

// 症状选项
const symptomOptions = [
  { label: '乏力', value: 'fatigue' },
  { label: '黄疸', value: 'jaundice' },
  { label: '腹痛', value: 'abdominal_pain' },
  { label: '恶心', value: 'nausea' },
  { label: '呕吐', value: 'vomiting' },
  { label: '食欲减退', value: 'appetite_loss' },
  { label: '体重下降', value: 'weight_loss' },
  { label: '发热', value: 'fever' },
  { label: '尿色加深', value: 'dark_urine' },
  { label: '大便颜色变浅', value: 'pale_stool' },
  { label: '皮肤瘙痒', value: 'itching' },
  { label: '腹胀', value: 'abdominal_swelling' },
]

// 检验字段配置
const labFields = [
  { key: 'alt', label: 'ALT', unit: 'U/L' },
  { key: 'ast', label: 'AST', unit: 'U/L' },
  { key: 'alp', label: 'ALP', unit: 'U/L' },
  { key: 'ggt', label: 'GGT', unit: 'U/L' },
  { key: 'tbil', label: '总胆红素', unit: 'μmol/L' },
  { key: 'dbil', label: '直接胆红素', unit: 'μmol/L' },
  { key: 'albumin', label: '白蛋白', unit: 'g/L' },
  { key: 'pt', label: '凝血酶原时间', unit: 's' },
]

/**
 * 提交表单
 */
const handleSubmit = async () => {
  if (!formRef.value) return

  try {
    await formRef.value.validate()
    emit('submit', { ...formData })
  } catch (error) {
    ElMessage.warning('请检查表单填写是否完整')
  }
}

/**
 * 重置表单
 */
const handleReset = () => {
  formRef.value?.resetFields()
  ElMessage.info('表单已重置')
}

/**
 * 测试用例数据（从 patient_cases_suite.json 提取，用于快速填充表单）
 */
const testCases = [
  {
    case_id: 'CASE-001',
    case_name: '信息完整-脂肪肝-中年男性',
    category: '信息完整',
    patient_data: {
      patient_id: 'P001',
      age: 48,
      gender: 'male',
      bmi: 32.5,
      chief_complaint: '体检发现脂肪肝3个月',
      history: {
        alcohol_intake_weekly: 40,
        smoking: false,
        diabetes: false,
        hypertension: false,
        family_liver_disease: false,
        medications: [],
        allergies: []
      },
      symptoms: {
        fatigue: true,
        jaundice: false,
        abdominal_pain: false,
        nausea: false,
        vomiting: false,
        appetite_loss: false,
        weight_loss: false,
        fever: false,
        dark_urine: false,
        pale_stool: false,
        itching: false,
        abdominal_swelling: false
      },
      labs: {
        alt: 68,
        ast: 52,
        alp: 78,
        ggt: 85,
        tbil: 12.5,
        dbil: 6.2,
        albumin: 42,
        pt: 12.5
      },
      ultrasound: {
        findings: '中度脂肪肝，肝回声增强',
        liver_size: '',
        echo_pattern: ''
      }
    }
  },
  {
    case_id: 'CASE-002',
    case_name: '信息完整-酒精性肝病-中年男性',
    category: '信息完整',
    patient_data: {
      patient_id: 'P002',
      age: 53,
      gender: 'male',
      bmi: 27.2,
      chief_complaint: '乏力、食欲差2个月',
      history: {
        alcohol_intake_weekly: 450,
        smoking: false,
        diabetes: false,
        hypertension: false,
        family_liver_disease: false,
        medications: [],
        allergies: []
      },
      symptoms: {
        fatigue: true,
        jaundice: false,
        abdominal_pain: false,
        nausea: false,
        vomiting: false,
        appetite_loss: true,
        weight_loss: false,
        fever: false,
        dark_urine: false,
        pale_stool: false,
        itching: false,
        abdominal_swelling: false
      },
      labs: {
        alt: 90,
        ast: 195,
        alp: 78,
        ggt: 220,
        tbil: 28.5,
        dbil: 14.0,
        albumin: 40,
        pt: 12.8
      },
      ultrasound: {
        findings: '肝实质增粗',
        liver_size: '',
        echo_pattern: ''
      }
    }
  },
  {
    case_id: 'CASE-003',
    case_name: '信息完整-Wilson病-年轻女性',
    category: '罕见病',
    patient_data: {
      patient_id: 'P003',
      age: 16,
      gender: 'female',
      bmi: 17.9,
      chief_complaint: '手抖、肝功能异常半年',
      history: {
        alcohol_intake_weekly: 0,
        smoking: false,
        diabetes: false,
        hypertension: false,
        family_liver_disease: true,
        medications: [],
        allergies: []
      },
      symptoms: {
        fatigue: true,
        jaundice: false,
        abdominal_pain: false,
        nausea: false,
        vomiting: false,
        appetite_loss: false,
        weight_loss: false,
        fever: false,
        dark_urine: false,
        pale_stool: false,
        itching: false,
        abdominal_swelling: false
      },
      labs: {
        alt: 130,
        ast: 101,
        alp: 80,
        ggt: 65,
        tbil: 45,
        dbil: 22.0,
        albumin: 38,
        pt: 13.0
      },
      ultrasound: {
        findings: '肝硬化表现',
        liver_size: '',
        echo_pattern: ''
      }
    }
  },
  {
    case_id: 'CASE-005',
    case_name: '关键缺失-无肝功能检查',
    category: '关键信息缺失',
    patient_data: {
      patient_id: 'P005',
      age: 35,
      gender: 'male',
      bmi: 28.0,
      chief_complaint: '体检发现肝脏问题',
      history: {
        alcohol_intake_weekly: 80,
        smoking: false,
        diabetes: false,
        hypertension: false,
        family_liver_disease: false,
        medications: [],
        allergies: []
      },
      symptoms: {
        fatigue: true,
        jaundice: false,
        abdominal_pain: false,
        nausea: false,
        vomiting: false,
        appetite_loss: false,
        weight_loss: false,
        fever: false,
        dark_urine: false,
        pale_stool: false,
        itching: false,
        abdominal_swelling: false
      },
      labs: {
        alt: undefined,
        ast: undefined,
        alp: undefined,
        ggt: undefined,
        tbil: undefined,
        dbil: undefined,
        albumin: undefined,
        pt: undefined
      },
      ultrasound: {
        findings: '脂肪肝',
        liver_size: '',
        echo_pattern: ''
      }
    }
  }
]

/**
 * 根据分类返回标签类型
 */
const getCategoryTagType = (category: string) => {
  switch (category) {
    case '信息完整':
      return 'success'
    case '关键信息缺失':
      return 'danger'
    case '非关键信息缺失':
      return 'warning'
    default:
      return 'info'
  }
}

/**
 * 处理测试用例填充
 */
const handleFillTestCase = (caseId: string) => {
  const testCase = testCases.find(tc => tc.case_id === caseId)
  if (!testCase) return

  const data = testCase.patient_data
  
  formData.patient_id = data.patient_id
  formData.age = data.age
  formData.gender = data.gender
  formData.bmi = data.bmi
  formData.chief_complaint = data.chief_complaint
  
  if (data.history) {
    formData.history!.alcohol_intake_weekly = data.history.alcohol_intake_weekly
    formData.history!.smoking = data.history.smoking || false
    formData.history!.diabetes = data.history.diabetes || false
    formData.history!.hypertension = data.history.hypertension || false
    formData.history!.family_liver_disease = data.history.family_liver_disease || false
    formData.history!.medications = data.history.medications || []
    formData.history!.allergies = data.history.allergies || []
  }
  
  if (data.symptoms) {
    Object.keys(formData.symptoms!).forEach(key => {
      formData.symptoms![key] = data.symptoms![key] || false
    })
  }
  
  if (data.labs) {
    formData.labs!.alt = data.labs.alt
    formData.labs!.ast = data.labs.ast
    formData.labs!.alp = data.labs.alp
    formData.labs!.ggt = data.labs.ggt
    formData.labs!.tbil = data.labs.tbil
    formData.labs!.dbil = data.labs.dbil
    formData.labs!.albumin = data.labs.albumin
    formData.labs!.pt = data.labs.pt
  }
  
  if (data.ultrasound) {
    formData.ultrasound!.findings = data.ultrasound.findings || ''
    formData.ultrasound!.liver_size = data.ultrasound.liver_size || ''
    formData.ultrasound!.echo_pattern = data.ultrasound.echo_pattern || ''
  }
  
  ElMessage.success(`已填充测试用例：${testCase.case_name}`)
}

/**
 * 填入示例数据（用于测试）
 */
const handleFillDemo = () => {
  formData.patient_id = 'P20260425001'
  formData.age = 45
  formData.gender = 'male'
  formData.chief_complaint = '体检发现肝功能异常2周，乏力伴食欲减退'
  formData.bmi = 28.5
  formData.history!.alcohol_intake_weekly = 50
  formData.history!.smoking = true
  formData.history!.diabetes = false
  formData.history!.hypertension = true
  formData.history!.family_liver_disease = false
  formData.history!.medications = ['降压药']
  formData.history!.allergies = ['青霉素']
  
  formData.symptoms!.fatigue = true
  formData.symptoms!.appetite_loss = true
  formData.symptoms!.nausea = true
  
  formData.labs!.alt = 150
  formData.labs!.ast = 120
  formData.labs!.alp = 180
  formData.labs!.ggt = 95
  formData.labs!.tbil = 35.2
  formData.labs!.dbil = 18.5
  formData.labs!.albumin = 38
  formData.labs!.pt = 13.5
  
  formData.ultrasound!.findings = '肝脏回声增粗，轻度脂肪肝表现，肝内血管显示清晰'
  formData.ultrasound!.liver_size = '轻度增大'
  formData.ultrasound!.echo_pattern = 'fatty'
  
  ElMessage.success('已填入示例数据')
}
</script>

<style scoped lang="scss">
.el-form {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}

.el-divider {
  margin: 30px 0 20px;
  
  :deep(.el-divider__text) {
    font-size: 16px;
    font-weight: 600;
    color: #409eff;
    display: flex;
    align-items: center;
    gap: 8px;
  }
}

.el-form-item {
  margin-bottom: 22px;
}

:deep(.el-input-number) {
  width: 100%;
}

:deep(.el-checkbox) {
  margin-right: 20px;
}

// 响应式设计
@media (max-width: 768px) {
  .el-form {
    padding: 10px;
  }
  
  :deep(.el-form-item__label) {
    width: 100px !important;
  }
}
</style>
