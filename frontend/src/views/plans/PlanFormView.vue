<script setup lang="ts">
import 'element-plus/es/components/card/style/css'
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'

import { ElCard } from 'element-plus'
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
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
// A new tab keeps this unsaved draft available while the user checks the rule list.
function openPlansInNewTab() {
  window.open(router.resolve('/plans').href, '_blank', 'noopener')
}
async function save(payload: BillPlanPayload) {
  if (submitting.value) return
  const current = scope.capture()
  submitting.value = true
  try {
    if (uncertain.value)
      await ElMessageBox.confirm(
        '上次创建结果待确认。请先在规则列表核实是否已创建，重复创建会产生两条规则。确定已核实并再次创建吗？',
        '确认再次提交',
        { type: 'warning', confirmButtonText: '继续提交', cancelButtonText: '取消' },
      )
    if (!current()) return
    fieldErrors.value = {}
    operationMessage.value = ''
    const created = await createPlan(payload)
    if (!current()) return
    formComponent.value?.markSaved()
    ElMessage.success('账单规则已创建')
    await router.replace(`/plans/${created.id}`)
  } catch (cause) {
    if (!current() || cause === 'cancel' || cause === 'close') return
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
    <PageHeader
      title="新建账单规则"
      description="填写名称、金额、首次日期和周期，保存后自动生成账单"
    /><OperationFeedback
      :message="operationMessage"
      :action="uncertain ? '查看最近规则，核实是否已创建' : undefined"
      @check="openPlansInNewTab"
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
