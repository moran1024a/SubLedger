<script setup lang="ts">
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/card/style/css'
import 'element-plus/es/components/descriptions/style/css'
import 'element-plus/es/components/descriptions-item/style/css'
import 'element-plus/es/components/dropdown/style/css'
import 'element-plus/es/components/dropdown-item/style/css'
import 'element-plus/es/components/dropdown-menu/style/css'
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'

import {
  ElButton,
  ElCard,
  ElDescriptions,
  ElDescriptionsItem,
  ElDropdown,
  ElDropdownItem,
  ElDropdownMenu,
} from 'element-plus'
import { useQueryRequest } from '@/composables/useQueryRequest'
import { watch, ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { deletePlan, disablePlan, enablePlan, getPlan, updatePlan } from '@/api/plans'
import { ApiError, type BillPlan, type BillPlanPayload } from '@/types/api'
import { returnPath } from '@/utils/navigation'
import OperationFeedback from '@/components/common/OperationFeedback.vue'
import { useViewScope } from '@/composables/useViewScope'
import PageHeader from '@/components/common/PageHeader.vue'
import LoadingBlock from '@/components/common/LoadingBlock.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import BillPlanForm from '@/components/billing/BillPlanForm.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import MoneyText from '@/components/common/MoneyText.vue'
import { useAuthStore } from '@/stores/auth'
import { cycleParts, formatCycle, formatDateTime, normalizeAmount } from '@/utils/format'
import { positiveId } from '@/utils/billFilters'
import { asApiError, getFieldErrors, isUncertainWrite, writeErrorMessage } from '@/utils/apiErrors'

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
const formComponent = ref<InstanceType<typeof BillPlanForm>>()
const uncertain = ref(false)
const busy = computed(() => submitting.value || toggling.value || deleting.value)
const scope = useViewScope(() => route.params.id)
let requestSequence = 0
const queryRequests = useQueryRequest()
async function cancelEdit() {
  if (busy.value) return
  const current = scope.capture()
  if (!(await formComponent.value?.confirmDiscard()) || !current()) return
  editing.value = false
  fieldErrors.value = {}
}
async function reload() {
  if (busy.value) return
  const current = scope.capture()
  if (editing.value && !(await formComponent.value?.confirmDiscard())) return
  if (!current()) return
  editing.value = false
  await load()
}
async function load() {
  const signal = queryRequests.next()
  const sequence = ++requestSequence
  const current = scope.capture()
  const targetId = positiveId(route.params.id)
  if (!targetId) {
    plan.value = null
    loading.value = false
    error.value = new ApiError({
      status: 400,
      code: 'INVALID_PLAN_ID',
      message: '账单规则地址无效，请返回规则列表。',
    })
    return
  }
  loading.value = true
  error.value = null
  try {
    const loaded = await getPlan(targetId, signal)
    if (!current() || signal.aborted || sequence !== requestSequence) return
    plan.value = loaded
    if (!uncertain.value) operationMessage.value = ''
    else
      operationMessage.value =
        '已重新查询当前规则。原操作结果仍待确认，请核对规则内容后再决定下一步。'
    fieldErrors.value = {}
  } catch (cause) {
    if (!current() || signal.aborted || sequence !== requestSequence) return
    error.value = asApiError(cause, '加载失败')
  } finally {
    if (current() && !signal.aborted && sequence === requestSequence) loading.value = false
  }
}
async function save(payload: BillPlanPayload) {
  if (!plan.value || busy.value || loading.value) return
  const old = plan.value
  const current = scope.capture()
  submitting.value = true
  fieldErrors.value = {}
  const oldCycle = cycleParts(old.cycle_type, old.cycle_days, old.cycle_interval)
  const nextCycle = cycleParts(payload.cycle_type, payload.cycle_days, payload.cycle_interval)
  const scheduleChanged =
    old.first_due_date !== payload.first_due_date ||
    oldCycle.type !== nextCycle.type ||
    oldCycle.interval !== nextCycle.interval
  const amountChanged = normalizeAmount(old.amount) !== normalizeAmount(payload.amount)
  const targetId = plan.value.id
  try {
    if (scheduleChanged || amountChanged) {
      const messages = []
      if (amountChanged) messages.push('历史账单金额保持不变，今日及未来账单使用新金额。')
      if (scheduleChanged)
        messages.push(
          '未来账单将重新生成，已有无效标记会被清除，历史账单不会删除。今日及未来的提醒记录会重建，已发送的当天提醒可能再次发送。',
        )
      await ElMessageBox.confirm(
        `规则「${old.name}」(#${targetId})。${messages.join(' ')}`,
        '确认保存账单规则',
        {
          type: 'warning',
          confirmButtonText: '确认保存',
          cancelButtonText: '取消',
        },
      )
    }
    if (!current() || plan.value !== old) return
    operationMessage.value = ''
    uncertain.value = false
    const updated = await updatePlan(targetId, payload)
    if (!current()) return
    formComponent.value?.markSaved()
    plan.value = updated
    editing.value = false
    ElMessage.success(updated.future_bills_rebuilt ? '已保存并重建未来账单' : '账单规则已保存')
  } catch (cause) {
    if (!current()) return
    if (cause !== 'cancel' && cause !== 'close') {
      fieldErrors.value = getFieldErrors(cause)
      uncertain.value = isUncertainWrite(cause)
      operationMessage.value = writeErrorMessage(cause)
    }
  } finally {
    if (current()) submitting.value = false
  }
}
async function toggle() {
  if (!plan.value || editing.value || busy.value || loading.value) return
  toggling.value = true
  const wasEnabled = plan.value.is_enabled
  const targetId = plan.value.id
  const current = scope.capture()
  try {
    if (wasEnabled)
      await ElMessageBox.confirm(
        `规则「${plan.value.name}」(#${targetId})。停用后不再生成新账单，当前未过账单将失效，不再参与月均和日均统计，也不再发送提醒；今日、本月、全年合计会同步减少。历史账单会保留。`,
        '确认停用',
        { type: 'warning', confirmButtonText: '停用', cancelButtonText: '取消' },
      )
    else
      await ElMessageBox.confirm(
        `规则「${plan.value.name}」(#${targetId})。启用后会恢复因停用而失效的今日及未来账单，补齐后续账单并恢复提醒。手动标记无效的账单不会恢复。`,
        '确认启用',
        { type: 'info', confirmButtonText: '启用', cancelButtonText: '取消' },
      )
    if (!current() || plan.value?.is_enabled !== wasEnabled) return
    operationMessage.value = ''
    uncertain.value = false
    if (wasEnabled) {
      await disablePlan(targetId)
      if (!current()) return
      ElMessage.success('账单规则已停用')
    } else {
      await enablePlan(targetId)
      if (!current()) return
      ElMessage.success('账单规则已启用')
    }
    await load()
  } catch (cause) {
    if (!current()) return
    if (cause !== 'cancel' && cause !== 'close') {
      uncertain.value = isUncertainWrite(cause)
      operationMessage.value = writeErrorMessage(cause)
    }
  } finally {
    if (current()) toggling.value = false
  }
}
async function remove() {
  if (!plan.value || editing.value || busy.value || loading.value) return
  deleting.value = true
  const targetId = plan.value.id
  const current = scope.capture()
  try {
    await ElMessageBox.confirm(
      `规则「${plan.value.name}」(#${targetId})。删除后无法恢复。按账户时区，今天以前的已过账单会保留，今天及未来账单会同步删除且不再发送提醒。`,
      '确认删除账单规则',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
    if (!current()) return
    operationMessage.value = ''
    uncertain.value = false
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
      uncertain.value = isUncertainWrite(cause)
      operationMessage.value = writeErrorMessage(cause)
    }
  } finally {
    if (current()) deleting.value = false
  }
}
watch(
  () => route.params.id,
  () => {
    queryRequests.cancel()
    plan.value = null
    operationMessage.value = ''
    uncertain.value = false
    submitting.value = false
    toggling.value = false
    deleting.value = false
    fieldErrors.value = {}
    editing.value = false
    requestSequence += 1
    void load()
  },
  { immediate: true, flush: 'sync' },
)
</script>

<template>
  <div class="page-container">
    <PageHeader title="账单规则详情"
      ><template #actions
        ><el-button :disabled="busy" @click="router.push(returnTo)">返回来源</el-button
        ><el-button
          v-if="plan && !editing"
          :disabled="busy || loading"
          @click="
            router.push({
              path: '/bills',
              query: { plan_id: String(plan.id), time_status: 'all', return_to: route.fullPath },
            })
          "
          >查看关联账单</el-button
        ><el-button
          v-if="plan"
          class="desktop-action"
          :type="plan.is_enabled ? undefined : 'success'"
          :plain="!plan.is_enabled"
          :loading="toggling"
          :disabled="editing || busy || loading"
          @click="toggle"
          >{{ plan.is_enabled ? '停用' : '启用' }}</el-button
        ><el-button
          v-if="plan && !editing"
          type="primary"
          :disabled="busy || loading"
          @click="editing = true"
          >编辑</el-button
        ><el-button
          v-if="plan && !editing"
          class="desktop-action"
          type="danger"
          :loading="deleting"
          :disabled="busy || loading"
          @click="remove"
          >删除</el-button
        ><el-dropdown
          v-if="plan && !editing"
          class="mobile-action"
          trigger="click"
          :disabled="busy || loading"
          ><el-button :loading="toggling || deleting" :disabled="busy || loading">更多</el-button
          ><template #dropdown
            ><el-dropdown-menu
              ><el-dropdown-item @click="toggle">{{
                plan.is_enabled ? '停用' : '启用'
              }}</el-dropdown-item
              ><el-dropdown-item divided @click="remove">删除</el-dropdown-item></el-dropdown-menu
            ></template
          ></el-dropdown
        ></template
      ></PageHeader
    ><OperationFeedback
      :message="operationMessage"
      action="重新查询核实"
      :disabled="busy || loading"
      @check="reload"
    /><LoadingBlock v-if="loading" /><ErrorState
      v-else-if="error"
      :message="error.message"
      :request-id="error.requestId"
      @retry="load"
    /><el-card v-else-if="plan && editing"
      ><BillPlanForm
        ref="formComponent"
        :plan="plan"
        :submitting="submitting"
        :field-errors="fieldErrors"
        @submit="save"
        @cancel="cancelEdit" /></el-card
    ><el-card v-else-if="plan"
      ><div class="plan-overview">
        <div>
          <p class="detail-label">
            {{ formatCycle(plan.cycle_type, plan.cycle_days, plan.cycle_interval) }}
          </p>
          <h2>{{ plan.name }}</h2>
          <StatusTag :active="plan.is_enabled" />
        </div>
        <div class="plan-amount numeric">
          <span class="detail-label">每次账单金额</span
          ><MoneyText :value="plan.amount" :currency="auth.user?.currency_code" />
        </div>
      </div>
      <el-descriptions :column="1" border class="plan-details"
        ><el-descriptions-item label="ID">{{ plan.id }}</el-descriptions-item
        ><el-descriptions-item label="首次日期">{{ plan.first_due_date }}</el-descriptions-item
        ><el-descriptions-item label="周期">{{
          formatCycle(plan.cycle_type, plan.cycle_days, plan.cycle_interval)
        }}</el-descriptions-item
        ><el-descriptions-item label="备注"
          ><span class="plan-note">{{ plan.note || '暂无备注' }}</span></el-descriptions-item
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

<style scoped>
.plan-overview {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--sl-space-6);
  margin-bottom: var(--sl-space-6);
}
.plan-overview > div {
  min-width: 0;
}
.plan-overview h2 {
  margin: 8px 0 12px;
  overflow-wrap: anywhere;
}
.detail-label {
  display: block;
  color: var(--sl-text-muted);
  font-size: 13px;
  margin: 0 0 8px;
}
.plan-amount {
  text-align: right;
  font-size: 28px;
  flex-shrink: 0;
}
.plan-details :deep(.el-descriptions__label) {
  width: 112px;
}
.plan-details :deep(.el-descriptions__content) {
  overflow-wrap: anywhere;
}
.plan-note {
  white-space: pre-wrap;
}
.mobile-action {
  display: none;
}

@media (max-width: 700px) {
  .desktop-action {
    display: none;
  }
  .mobile-action {
    display: inline-flex;
  }
  .page-container :deep(.page-actions) {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .plan-overview {
    flex-direction: column;
    gap: var(--sl-space-4);
  }
  .plan-amount {
    align-self: stretch;
  }
}
</style>
