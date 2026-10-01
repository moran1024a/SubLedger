<script setup lang="ts">
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/card/style/css'
import 'element-plus/es/components/descriptions/style/css'
import 'element-plus/es/components/descriptions-item/style/css'
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'

import { ElButton, ElCard, ElDescriptions, ElDescriptionsItem } from 'element-plus'
import { useQueryRequest } from '@/composables/useQueryRequest'
import { onBeforeUnmount, watch, ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { deletePlan, disablePlan, enablePlan, getPlan, updatePlan } from '@/api/plans'
import { ApiError, type BillPlan, type BillPlanPayload } from '@/types/api'
import { returnPath } from '@/utils/navigation'
import OperationFeedback from '@/components/common/OperationFeedback.vue'
import { confirmDiscardChanges } from '@/composables/useUnsavedChanges'
import PageHeader from '@/components/common/PageHeader.vue'
import LoadingBlock from '@/components/common/LoadingBlock.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import BillPlanForm from '@/components/billing/BillPlanForm.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import MoneyText from '@/components/common/MoneyText.vue'
import { useAuthStore } from '@/stores/auth'
import { formatCycle, formatDateTime } from '@/utils/format'
import { asApiError, getFieldErrors, writeErrorMessage } from '@/utils/apiErrors'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const returnTo = computed(() => returnPath(route.query.return_to))
const operationMessage = ref('')
const plan = ref<BillPlan | null>(null)
const loading = ref(true)
const editing = ref(false)
const submitting = ref(false)
const toggling = ref(false)
const deleting = ref(false)
const error = ref<ApiError | null>(null)
const fieldErrors = ref<Record<string, string>>({})
let generation = 0
let requestSequence = 0
onBeforeUnmount(() => {
  generation += 1
  requestSequence += 1
})
const queryRequests = useQueryRequest()
async function reload() {
  if (editing.value && !confirmDiscardChanges()) return
  editing.value = false
  await load()
}
async function load() {
  const signal = queryRequests.next()
  const sequence = ++requestSequence
  const targetId = Number(route.params.id)
  loading.value = true
  error.value = null
  try {
    const loaded = await getPlan(targetId, signal)
    if (signal.aborted || sequence !== requestSequence) return
    plan.value = loaded
  } catch (cause) {
    if (signal.aborted || sequence !== requestSequence) return
    error.value = asApiError(cause, '加载失败')
  } finally {
    if (!signal.aborted && sequence === requestSequence) loading.value = false
  }
}
async function save(payload: BillPlanPayload) {
  if (!plan.value || submitting.value || toggling.value || deleting.value) return
  const old = plan.value
  submitting.value = true
  fieldErrors.value = {}
  const scheduleChanged =
    old.first_due_date !== payload.first_due_date ||
    old.cycle_type !== payload.cycle_type ||
    (old.cycle_interval ?? 1) !== (payload.cycle_interval ?? 1) ||
    old.cycle_days !== payload.cycle_days
  const amountChanged = old.amount !== payload.amount
  const targetId = plan.value.id
  const version = generation
  const current = () => version === generation && Number(route.params.id) === targetId
  try {
    if (scheduleChanged || amountChanged) {
      const messages = []
      if (amountChanged) messages.push('历史账单金额保持不变，今日及未来账单使用新金额。')
      if (scheduleChanged)
        messages.push('未来账单将重新生成，已有无效标记会被清除，历史账单不会删除。')
      await ElMessageBox.confirm(messages.join(' '), '确认保存账单规则', {
        type: 'warning',
        confirmButtonText: '确认保存',
        cancelButtonText: '取消',
      })
    }
    if (!current()) return
    const updated = await updatePlan(targetId, payload)
    if (!current()) return
    plan.value = updated
    editing.value = false
    ElMessage.success(updated.future_bills_rebuilt ? '已保存并重建未来账单' : '账单规则已保存')
  } catch (cause) {
    if (!current()) return
    if (cause !== 'cancel' && cause !== 'close') {
      fieldErrors.value = getFieldErrors(cause)
      operationMessage.value = writeErrorMessage(cause)
    }
  } finally {
    submitting.value = false
  }
}
async function toggle() {
  if (!plan.value || editing.value || submitting.value || toggling.value || deleting.value) return
  toggling.value = true
  const wasEnabled = plan.value.is_enabled
  const targetId = plan.value.id
  const version = generation
  const current = () => version === generation && Number(route.params.id) === targetId
  try {
    if (wasEnabled) {
      await ElMessageBox.confirm(
        '停用后不再生成新账单，当前未过账单将失效，不再参与月均和日均统计，也不再发送提醒。历史账单会保留。',
        '确认停用',
        { type: 'warning', confirmButtonText: '停用', cancelButtonText: '取消' },
      )
      if (!current()) return
      await disablePlan(targetId)
      if (!current()) return
      ElMessage.success('账单规则已停用')
    } else {
      if (!current()) return
      await enablePlan(targetId)
      if (!current()) return
      ElMessage.success('账单规则已启用')
    }
    await load()
  } catch (cause) {
    if (!current()) return
    if (cause !== 'cancel' && cause !== 'close') operationMessage.value = writeErrorMessage(cause)
  } finally {
    toggling.value = false
  }
}
async function remove() {
  if (!plan.value || editing.value || submitting.value || toggling.value || deleting.value) return
  deleting.value = true
  const targetId = plan.value.id
  const version = generation
  const current = () => version === generation && Number(route.params.id) === targetId
  try {
    await ElMessageBox.confirm(
      '删除后无法恢复。按账户时区，今天以前的已过账单会保留，今天及未来账单会同步删除且不再发送提醒。',
      '确认删除账单规则',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
    if (!current()) return
    await deletePlan(targetId)
    if (!current()) return
    ElMessage.success('账单规则已删除')
    await router.replace('/plans')
  } catch (cause) {
    if (!current()) return
    if (cause instanceof ApiError && cause.code === 'BILL_PLAN_NOT_FOUND') {
      ElMessage.success('账单规则已不存在')
      await router.replace('/plans')
    } else if (cause !== 'cancel' && cause !== 'close') {
      operationMessage.value = writeErrorMessage(cause)
    }
  } finally {
    deleting.value = false
  }
}
watch(
  () => route.params.id,
  () => {
    generation += 1
    plan.value = null
    fieldErrors.value = {}
    editing.value = false
    const targetId = Number(route.params.id)
    requestSequence += 1
    if (Number.isSafeInteger(targetId) && targetId > 0) void load()
  },
  { immediate: true, flush: 'sync' },
)
</script>

<template>
  <div class="page-container">
    <PageHeader title="账单规则详情"
      ><template #actions
        ><el-button @click="router.push(returnTo)">返回来源</el-button
        ><el-button
          v-if="plan && !editing"
          @click="
            router.push({
              path: '/bills',
              query: { plan_id: String(plan.id), time_status: 'all', return_to: route.fullPath },
            })
          "
          >查看关联账单</el-button
        ><el-button
          v-if="plan"
          :type="plan.is_enabled ? 'danger' : 'success'"
          :loading="toggling"
          :disabled="editing || submitting || deleting"
          @click="toggle"
          >{{ plan.is_enabled ? '停用' : '启用' }}</el-button
        ><el-button
          v-if="plan && !editing"
          type="primary"
          :disabled="submitting || toggling || deleting"
          @click="editing = true"
          >编辑</el-button
        ><el-button
          v-if="plan && !editing"
          type="danger"
          :loading="deleting"
          :disabled="submitting || toggling"
          @click="remove"
          >删除</el-button
        ></template
      ></PageHeader
    ><OperationFeedback
      :message="operationMessage"
      action="重新查询核实"
      @check="reload"
    /><LoadingBlock v-if="loading" /><ErrorState
      v-else-if="error"
      :message="error.message"
      :request-id="error.requestId"
      @retry="load"
    /><el-card v-else-if="plan && editing"
      ><BillPlanForm
        :plan="plan"
        :submitting="submitting"
        :field-errors="fieldErrors"
        @submit="save"
        @cancel="editing = false" /></el-card
    ><el-card v-else-if="plan"
      ><el-descriptions :column="1" border
        ><el-descriptions-item label="ID">{{ plan.id }}</el-descriptions-item
        ><el-descriptions-item label="名称">{{ plan.name }}</el-descriptions-item
        ><el-descriptions-item label="金额"
          ><MoneyText :value="plan.amount" :currency="auth.user?.currency_code"
        /></el-descriptions-item>
        ><el-descriptions-item label="首次日期">{{ plan.first_due_date }}</el-descriptions-item
        ><el-descriptions-item label="周期">{{
          formatCycle(plan.cycle_type, plan.cycle_days, plan.cycle_interval)
        }}</el-descriptions-item
        ><el-descriptions-item label="状态"
          ><StatusTag :active="plan.is_enabled" /></el-descriptions-item
        ><el-descriptions-item label="备注">{{ plan.note || '—' }}</el-descriptions-item
        ><el-descriptions-item label="创建时间">{{
          formatDateTime(plan.created_at, auth.user?.timezone)
        }}</el-descriptions-item
        ><el-descriptions-item label="更新时间">{{
          formatDateTime(plan.updated_at, auth.user?.timezone)
        }}</el-descriptions-item></el-descriptions
      ></el-card
    >
  </div>
</template>
