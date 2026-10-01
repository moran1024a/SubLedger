<script setup lang="ts">
import 'element-plus/es/components/card/style/css'
import 'element-plus/es/components/message/style/css'

import { ElCard } from 'element-plus'
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { createPlan } from '@/api/plans'
import { type BillPlanPayload } from '@/types/api'
import OperationFeedback from '@/components/common/OperationFeedback.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import BillPlanForm from '@/components/billing/BillPlanForm.vue'
import { getFieldErrors, writeErrorMessage } from '@/utils/apiErrors'

const router = useRouter()
const formComponent = ref<InstanceType<typeof BillPlanForm>>()
const operationMessage = ref('')
const submitting = ref(false)
const fieldErrors = ref<Record<string, string>>({})
async function save(payload: BillPlanPayload) {
  if (submitting.value) return
  fieldErrors.value = {}
  submitting.value = true
  try {
    const created = await createPlan(payload)
    formComponent.value?.markSaved()
    ElMessage.success('账单规则已创建')
    await router.replace(`/plans/${created.id}`)
  } catch (cause) {
    fieldErrors.value = getFieldErrors(cause)
    operationMessage.value = writeErrorMessage(cause)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="page-container">
    <PageHeader title="新建账单规则" /><OperationFeedback
      :message="operationMessage"
      action="查看最近规则，核实是否已创建"
      @check="router.push('/plans')"
    /><el-card
      ><BillPlanForm
        ref="formComponent"
        :submitting="submitting"
        :field-errors="fieldErrors"
        @submit="save"
        @cancel="router.push('/plans')"
    /></el-card>
  </div>
</template>
