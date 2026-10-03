<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ElDrawer,
  ElButton,
  ElDescriptions,
  ElDescriptionsItem,
  ElMessage,
  ElMessageBox,
} from 'element-plus'
import 'element-plus/es/components/drawer/style/css'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/descriptions/style/css'
import 'element-plus/es/components/descriptions-item/style/css'
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import { getBill, updateBillValidity } from '@/api/bills'
import { ApiError, type BillOccurrence } from '@/types/api'
import { useQueryRequest } from '@/composables/useQueryRequest'
import { useViewScope } from '@/composables/useViewScope'
import { useAuthStore } from '@/stores/auth'
import { asApiError, isUncertainWrite, writeErrorMessage } from '@/utils/apiErrors'
import { formatCycle, formatMoney } from '@/utils/format'
import ErrorState from '@/components/common/ErrorState.vue'
import LoadingBlock from '@/components/common/LoadingBlock.vue'
import OperationFeedback from '@/components/common/OperationFeedback.vue'
const props = defineProps<{ billId: number | null; refreshKey?: number; disabled?: boolean }>()
const emit = defineEmits<{ close: []; changed: []; busy: [value: boolean] }>()
const auth = useAuthStore(),
  route = useRoute(),
  router = useRouter()
const bill = ref<BillOccurrence | null>(null),
  loading = ref(false),
  saving = ref(false)
const error = ref<ApiError | null>(null),
  feedback = ref('')
const queries = useQueryRequest()
const scope = useViewScope(() => props.billId)
const parentScope = useViewScope(() => route.path)
const uncertain = ref(false)
watch(saving, (value) => emit('busy', value), { flush: 'sync' })
onBeforeUnmount(() => emit('busy', false))
async function load(verify = false) {
  const id = props.billId
  const signal = queries.next()
  const current = scope.capture()
  if (!id || !Number.isSafeInteger(id) || id <= 0) {
    loading.value = false
    bill.value = null
    if (id !== null)
      error.value = new ApiError({
        status: 400,
        code: 'INVALID_BILL_ID',
        message: '账单地址无效，请关闭详情后重新选择。',
      })
    return
  }
  loading.value = true
  error.value = null
  try {
    const result = await getBill(id, signal)
    if (!signal.aborted && current()) {
      bill.value = result
      if (!uncertain.value) feedback.value = ''
      else
        feedback.value = `已重新查询，当前账单为${result.is_valid ? '有效' : '无效'}。原操作结果仍待确认，请核对后再操作。`
      if (verify) emit('changed')
    }
  } catch (cause) {
    if (!signal.aborted && current()) error.value = asApiError(cause)
  } finally {
    if (!signal.aborted && current()) loading.value = false
  }
}
watch(
  () => props.billId,
  (id) => {
    queries.cancel()
    bill.value = null
    error.value = null
    feedback.value = ''
    uncertain.value = false
    saving.value = false
    loading.value = false
    if (id !== null) void load()
  },
  { immediate: true, flush: 'sync' },
)
watch(
  () => props.refreshKey,
  () => {
    if (props.billId !== null && !saving.value) void load()
  },
)
async function verify() {
  if (saving.value || props.disabled || loading.value) return
  await load(true)
}
async function toggle() {
  if (!bill.value || saving.value || loading.value || props.disabled) return
  const target = bill.value,
    id = target.id
  const current = scope.capture()
  const parentCurrent = parentScope.capture()
  saving.value = true
  try {
    if (target.is_valid)
      await ElMessageBox.confirm(
        `账单「${target.plan_name}」(${target.due_date}，#${id})。标记无效后不再计入统计和提醒，记录会保留。`,
        '确认标记无效',
        {
          type: 'warning',
          confirmButtonText: '标记无效',
          cancelButtonText: '取消',
        },
      )
    if (!current() || props.billId !== id || bill.value?.is_valid !== target.is_valid) return
    feedback.value = ''
    uncertain.value = false
    const updated = await updateBillValidity(id, !target.is_valid)
    if (current() && props.billId === id) {
      bill.value = updated
      error.value = null
      feedback.value = ''
      ElMessage.success(updated.is_valid ? '已恢复有效' : '已标记无效')
    }
    // Closing or changing the drawer does not undo a successful write. The
    // mounted parent still needs fresh list/statistics data for that change.
    if (parentCurrent()) emit('changed')
  } catch (cause) {
    if (current() && props.billId === id && cause !== 'cancel' && cause !== 'close') {
      uncertain.value = isUncertainWrite(cause)
      feedback.value = writeErrorMessage(cause)
    }
  } finally {
    if (current()) saving.value = false
  }
}
function viewPlan() {
  if (bill.value && !saving.value && !props.disabled)
    void router.push({ path: `/plans/${bill.value.plan_id}`, query: { return_to: route.fullPath } })
}
</script>
<template>
  <el-drawer
    :model-value="billId !== null"
    title="账单详情"
    size="min(460px, 100%)"
    :close-on-click-modal="!saving && !disabled"
    :close-on-press-escape="!saving && !disabled"
    :show-close="!saving && !disabled"
    @update:model-value="!$event && !saving && !disabled && emit('close')"
  >
    <LoadingBlock v-if="loading && !bill" />
    <ErrorState
      v-if="error"
      :message="
        error.code === 'BILL_OCCURRENCE_NOT_FOUND'
          ? '账单已不存在或不可访问，可关闭详情继续查询。'
          : error.message
      "
      :request-id="error.requestId"
      @retry="verify"
    />
    <OperationFeedback
      :message="feedback"
      action="重新查询核实"
      :disabled="saving || disabled || loading"
      @check="verify"
    />
    <template v-if="bill">
      <h2>{{ bill.plan_name }}</h2>
      <p class="detail-money numeric">{{ formatMoney(bill.amount, auth.user?.currency_code) }}</p>
      <el-descriptions :column="1" border>
        <el-descriptions-item label="日期">{{ bill.due_date }}</el-descriptions-item>
        <el-descriptions-item label="周期">{{
          formatCycle(bill.cycle_type, bill.cycle_days, bill.cycle_interval)
        }}</el-descriptions-item>
        <el-descriptions-item label="时间状态">{{
          bill.time_status === 'upcoming' ? '未过' : '已过'
        }}</el-descriptions-item>
        <el-descriptions-item label="有效性">{{
          bill.is_valid ? '有效' : '无效'
        }}</el-descriptions-item>
        <el-descriptions-item label="关联规则">{{
          bill.plan_status === 'deleted'
            ? '已删除，历史账单保留'
            : bill.plan_status === 'disabled'
              ? '已停用'
              : '启用中'
        }}</el-descriptions-item>
      </el-descriptions>
      <p class="hint">日期按账户时区 {{ auth.user?.timezone }} 划分。有效性不代表付款状态。</p>
      <p
        v-if="!bill.is_valid && bill.time_status === 'upcoming' && bill.plan_status !== 'enabled'"
        class="hint"
      >
        停用规则的今天及未来账单不能恢复有效。
      </p>
      <div class="detail-actions form-actions">
        <el-button
          v-if="bill.plan_status !== 'deleted'"
          :disabled="saving || disabled"
          @click="viewPlan"
          >查看关联规则</el-button
        >
        <el-button
          :type="bill.is_valid ? 'danger' : 'success'"
          :loading="saving"
          :disabled="
            loading ||
            saving ||
            disabled ||
            (!bill.is_valid && bill.time_status === 'upcoming' && bill.plan_status !== 'enabled')
          "
          @click="toggle"
          >{{ bill.is_valid ? '标记无效' : '恢复有效' }}</el-button
        >
        <el-button :disabled="saving || disabled" @click="emit('close')">关闭详情</el-button>
      </div>
    </template>
  </el-drawer>
</template>
<style scoped>
h2 {
  overflow-wrap: anywhere;
}
.detail-money {
  font-size: 28px;
  font-weight: 600;
  margin: 16px 0;
  text-align: right;
  overflow-wrap: anywhere;
}
.hint {
  color: var(--sl-text-muted);
  font-size: 13px;
  margin-top: 16px;
}
.detail-actions {
  margin-top: var(--sl-space-6);
}
:deep(.el-descriptions__label) {
  width: 92px;
}
:deep(.el-descriptions__content) {
  overflow-wrap: anywhere;
}
</style>
