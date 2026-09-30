<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import type { BillPlan, BillPlanPayload } from '@/types/api'
import { isValidAmount, isValidCycleDays } from '@/utils/validation'

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
  cycle_type: 'monthly',
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
  cycle_days: [
    {
      validator: (_rule: unknown, value: number | null, callback: (error?: Error) => void) =>
        form.cycle_type !== 'custom_days' || (value !== null && isValidCycleDays(String(value)))
          ? callback()
          : callback(new Error('请输入 1 到 36500 的整数天数')),
      trigger: 'blur',
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
        cycle_type: plan.cycle_type,
        cycle_days: plan.cycle_days,
        note: plan.note ?? '',
      })
  },
  { immediate: true },
)
watch(
  () => form.cycle_type,
  (type) => {
    if (type !== 'custom_days') form.cycle_days = null
  },
)
async function submit() {
  if (!(await formRef.value?.validate())) return
  emit('submit', {
    ...form,
    name: form.name.trim(),
    note: form.note?.trim() || null,
    cycle_days: form.cycle_type === 'custom_days' ? Number(form.cycle_days) : null,
  })
}
</script>

<template>
  <el-form
    ref="formRef"
    :model="form"
    :rules="rules"
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
    <el-form-item label="周期" prop="cycle_type" :error="fieldErrors?.cycle_type"
      ><el-select v-model="form.cycle_type" style="width: 100%"
        ><el-option label="单次" value="once" /><el-option label="每月" value="monthly" /><el-option
          label="每季度"
          value="quarterly" /><el-option label="每年" value="yearly" /><el-option
          label="自定义天数"
          value="custom_days" /></el-select
    ></el-form-item>
    <el-form-item
      v-if="form.cycle_type === 'custom_days'"
      label="每 N 天"
      prop="cycle_days"
      :error="fieldErrors?.cycle_days"
      ><el-input-number
        v-model="form.cycle_days"
        :min="1"
        :max="36500"
        :precision="0"
        controls-position="right"
        style="width: 100%"
    /></el-form-item>
    <el-form-item label="备注" prop="note" :error="fieldErrors?.note"
      ><el-input v-model="form.note" type="textarea" :rows="4" maxlength="2000" show-word-limit
    /></el-form-item>
    <div class="form-actions">
      <el-button @click="$emit('cancel')">取消</el-button
      ><el-button type="primary" :loading="submitting" native-type="submit">保存</el-button>
    </div>
  </el-form>
</template>

<style scoped>
.plan-form {
  max-width: 720px;
}
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>
