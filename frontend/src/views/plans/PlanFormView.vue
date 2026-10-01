<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { createPlan } from '@/api/plans'
import { ApiError, type BillPlanPayload } from '@/types/api'
import PageHeader from '@/components/common/PageHeader.vue'
import BillPlanForm from '@/components/billing/BillPlanForm.vue'
import { getFieldErrors } from '@/utils/apiErrors'

const router = useRouter()
const submitting = ref(false)
const fieldErrors = ref<Record<string, string>>({})
async function save(payload: BillPlanPayload) {
  if (submitting.value) return
  fieldErrors.value = {}
  submitting.value = true
  try {
    const created = await createPlan(payload)
    ElMessage.success('账单规则已创建')
    await router.replace(`/plans/${created.id}`)
  } catch (cause) {
    fieldErrors.value = getFieldErrors(cause)
    ElMessage.error(cause instanceof ApiError ? cause.message : '保存失败')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="page-container">
    <PageHeader title="新建账单规则" /><el-card
      ><BillPlanForm
        :submitting="submitting"
        :field-errors="fieldErrors"
        @submit="save"
        @cancel="router.push('/plans')"
    /></el-card>
  </div>
</template>
