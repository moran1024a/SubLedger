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
import { getFieldErrors, isUncertainWrite, writeErrorMessage } from '@/utils/apiErrors'
import { useViewScope } from '@/composables/useViewScope'

const router = useRouter()
const formComponent = ref<InstanceType<typeof BillPlanForm>>()
const operationMessage = ref('')
const submitting = ref(false)
const fieldErrors = ref<Record<string, string>>({})
const scope = useViewScope()
const uncertain = ref(false)
async function save(payload: BillPlanPayload) {
  if (submitting.value || uncertain.value) return
  const current = scope.capture()
  fieldErrors.value = {}
  operationMessage.value = ''
  submitting.value = true
  try {
    const created = await createPlan(payload)
    if (!current()) return
    formComponent.value?.markSaved()
    ElMessage.success('账单规则已创建')
    await router.replace(`/plans/${created.id}`)
  } catch (cause) {
    if (!current()) return
    fieldErrors.value = getFieldErrors(cause)
    uncertain.value = isUncertainWrite(cause)
    operationMessage.value = writeErrorMessage(cause)
  } finally {
    if (current()) submitting.value = false
  }
}
</script>

<template>
  <div class="page-container">
    <PageHeader title="新建账单规则" /><OperationFeedback
      :message="operationMessage"
      :action="uncertain ? '查看最近规则，核实是否已创建' : undefined"
      @check="router.push('/plans')"
    /><el-card
      ><BillPlanForm
        ref="formComponent"
        :submitting="submitting"
        :submit-disabled="uncertain"
        :field-errors="fieldErrors"
        @submit="save"
        @cancel="router.push('/plans')"
    /></el-card>
  </div>
</template>
