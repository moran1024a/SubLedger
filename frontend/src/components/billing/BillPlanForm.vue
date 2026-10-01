<script setup lang="ts">
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/date-picker/style/css'
import 'element-plus/es/components/form/style/css'
import 'element-plus/es/components/form-item/style/css'
import 'element-plus/es/components/input/style/css'
import 'element-plus/es/components/input-number/style/css'
import 'element-plus/es/components/option/style/css'
import 'element-plus/es/components/select/style/css'

import {
  ElButton,
  ElDatePicker,
  ElForm,
  ElFormItem,
  ElInput,
  ElInputNumber,
  ElOption,
  ElSelect,
} from 'element-plus'
import { computed, nextTick, reactive, ref, watch } from 'vue'
import type { BillPlan, BillPlanPayload } from '@/types/api'
import { isValidAmount } from '@/utils/validation'
import { cycleParts, cycleLimits, formatCycle } from '@/utils/format'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'

const props = defineProps<{
  plan?: BillPlan | null
  submitting?: boolean
  fieldErrors?: Record<string, string>
}>()
const emit = defineEmits<{ submit: [payload: BillPlanPayload]; cancel: [] }>()
const formRef = ref()
const form = reactive<BillPlanPayload>({
  name: '',
  amount: '',
  first_due_date: '',
  cycle_type: 'month',
  cycle_interval: 1,
  cycle_days: null,
  note: '',
})
const rules = {
  name: [
    { required: true, message: '请输入名称', trigger: 'blur' },
    { max: 128, message: '名称最多 128 个字符', trigger: 'blur' },
  ],
  amount: [
    { required: true, message: '请输入金额', trigger: 'blur' },
    {
      validator: (_rule: unknown, value: string, callback: (error?: Error) => void) =>
        isValidAmount(value)
          ? callback()
          : callback(new Error('请输入大于 0 且最多两位小数的金额')),
      trigger: 'blur',
    },
  ],
  first_due_date: [{ required: true, message: '请选择首次账单日期', trigger: 'change' }],
  cycle_type: [{ required: true, message: '请选择周期', trigger: 'change' }],
  cycle_interval: [
    {
      validator: (_rule: unknown, value: number, callback: (error?: Error) => void) => {
        const max =
          form.cycle_type === 'once'
            ? 1
            : cycleLimits[cycleParts(form.cycle_type).type as keyof typeof cycleLimits]
        if (Number.isInteger(value) && value >= 1 && value <= max) callback()
        else callback(new Error(`请输入 1 到 ${max} 的整数`))
      },
      trigger: 'change',
    },
  ],
  note: [{ max: 2000, message: '备注最多 2000 个字符', trigger: 'blur' }],
}
watch(
  () => props.plan,
  (plan) => {
    if (plan)
      Object.assign(form, {
        name: plan.name,
        amount: plan.amount,
        first_due_date: plan.first_due_date,
        cycle_type: cycleParts(plan.cycle_type, plan.cycle_days, plan.cycle_interval).type,
        cycle_interval: cycleParts(plan.cycle_type, plan.cycle_days, plan.cycle_interval).interval,
        cycle_days: null,
        note: plan.note ?? '',
      })
  },
  { immediate: true },
)
watch(
  () => form.cycle_type,
  (type) => {
    if (type === 'once') form.cycle_interval = 1
  },
)
const { dirty, confirmDiscard } = useUnsavedChanges()
const baseline = ref(JSON.stringify(form))
watch(
  form,
  () => {
    dirty.value = JSON.stringify(form) !== baseline.value
  },
  { deep: true, flush: 'sync' },
)
function markSaved() {
  baseline.value = JSON.stringify(form)
  dirty.value = false
}
watch(
  () => props.plan,
  () => {
    void nextTick(markSaved)
  },
)
const maxInterval = computed(() =>
  form.cycle_type === 'once'
    ? 1
    : cycleLimits[cycleParts(form.cycle_type).type as keyof typeof cycleLimits],
)
async function focusError() {
  await nextTick()
  formRef.value?.$el?.querySelector('.is-error input, .is-error textarea')?.focus()
}
watch(() => props.fieldErrors, focusError)
async function submit() {
  if (props.submitting) return
  try {
    if (!(await formRef.value?.validate())) return
  } catch {
    await focusError()
    return
  }
  emit('submit', {
    ...form,
    name: form.name.trim(),
    note: form.note?.trim() || null,
    cycle_days: null,
  })
}
function cancel() {
  if (!props.submitting && confirmDiscard()) emit('cancel')
}
defineExpose({ markSaved })
</script>

<template>
  <el-form
    ref="formRef"
    :model="form"
    :rules="rules"
    :disabled="submitting"
    scroll-to-error
    label-position="top"
    class="plan-form"
    @submit.prevent="submit"
  >
    <el-form-item label="名称" prop="name" :error="fieldErrors?.name"
      ><el-input v-model="form.name" maxlength="128" show-word-limit
    /></el-form-item>
    <el-form-item label="金额" prop="amount" :error="fieldErrors?.amount"
      ><el-input v-model="form.amount" placeholder="例如 120.00" inputmode="decimal"
    /></el-form-item>
    <el-form-item label="首次账单日期" prop="first_due_date" :error="fieldErrors?.first_due_date"
      ><el-date-picker
        v-model="form.first_due_date"
        value-format="YYYY-MM-DD"
        type="date"
        style="width: 100%"
    /></el-form-item>
    <el-form-item label="重复方式 / 周期单位" prop="cycle_type" :error="fieldErrors?.cycle_type">
      <el-select v-model="form.cycle_type" style="width: 100%">
        <el-option label="单次" value="once" /><el-option label="每 N 天" value="day" />
        <el-option label="每 N 周" value="week" /><el-option label="每 N 个月" value="month" />
        <el-option label="每 N 年" value="year" />
      </el-select>
    </el-form-item>
    <el-form-item
      v-if="form.cycle_type !== 'once'"
      label="周期间隔"
      prop="cycle_interval"
      :error="fieldErrors?.cycle_interval"
    >
      <el-input-number
        v-model="form.cycle_interval"
        :min="1"
        :max="maxInterval"
        :precision="0"
        controls-position="right"
        style="width: 100%"
      />
    </el-form-item>
    <p class="form-summary" aria-live="polite">
      {{ formatCycle(form.cycle_type, null, form.cycle_interval) }} · 每次
      {{ form.amount || '—' }} · 首次
      {{ form.first_due_date || '待选择' }}。月、年以首次日期为基准，短月取月末。
    </p>
    <el-form-item label="备注" prop="note" :error="fieldErrors?.note"
      ><el-input v-model="form.note" type="textarea" :rows="4" maxlength="2000" show-word-limit
    /></el-form-item>
    <p v-if="dirty" class="form-summary">有未保存的修改</p>
    <div class="form-actions">
      <el-button @click="cancel">取消</el-button
      ><el-button type="primary" :loading="submitting" native-type="submit">保存</el-button>
    </div>
  </el-form>
</template>

<style scoped>
.form-summary {
  color: #6b7280;
  font-size: 13px;
  margin: 0 0 18px;
}
.plan-form {
  max-width: 720px;
}
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>
