<script setup lang="ts">
import { ref, watch } from 'vue'
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
import { useAuthStore } from '@/stores/auth'
import { asApiError, writeErrorMessage } from '@/utils/apiErrors'
import { formatCycle, formatMoney } from '@/utils/format'
import ErrorState from '@/components/common/ErrorState.vue'
import LoadingBlock from '@/components/common/LoadingBlock.vue'
import OperationFeedback from '@/components/common/OperationFeedback.vue'
const props = defineProps<{ billId: number | null }>()
const emit = defineEmits<{ close: []; changed: [] }>()
const auth = useAuthStore(),
  route = useRoute(),
  router = useRouter()
const bill = ref<BillOccurrence | null>(null),
  loading = ref(false),
  saving = ref(false)
const error = ref<ApiError | null>(null),
  feedback = ref('')
const queries = useQueryRequest()
async function load() {
  const id = props.billId
  if (!id) return
  const signal = queries.next()
  loading.value = true
  error.value = null
  try {
    const result = await getBill(id, signal)
    if (!signal.aborted) bill.value = result
  } catch (cause) {
    if (!signal.aborted) error.value = asApiError(cause)
  } finally {
    if (!signal.aborted) loading.value = false
  }
}
watch(
  () => props.billId,
  (id) => {
    queries.cancel()
    bill.value = null
    error.value = null
    feedback.value = ''
    if (id) void load()
  },
  { immediate: true },
)
async function toggle() {
  if (!bill.value || saving.value) return
  const target = bill.value,
    id = target.id
  saving.value = true
  try {
    if (target.is_valid)
      await ElMessageBox.confirm('标记无效后不再计入统计和提醒，记录会保留。', '确认标记无效', {
        type: 'warning',
        confirmButtonText: '标记无效',
        cancelButtonText: '取消',
      })
    if (props.billId !== id) return
    const updated = await updateBillValidity(id, !target.is_valid)
    emit('changed')
    if (props.billId !== id) return
    bill.value = updated
    feedback.value = ''
    ElMessage.success(updated.is_valid ? '已恢复有效' : '已标记无效')
  } catch (cause) {
    if (props.billId === id && cause !== 'cancel' && cause !== 'close')
      feedback.value = writeErrorMessage(cause)
  } finally {
    saving.value = false
  }
}
function viewPlan() {
  if (bill.value)
    void router.push({ path: `/plans/${bill.value.plan_id}`, query: { return_to: route.fullPath } })
}
</script>
<template>
  <el-drawer
    :model-value="billId !== null"
    title="账单详情"
    size="min(460px, 100%)"
    :close-on-click-modal="!saving"
    :close-on-press-escape="!saving"
    :show-close="!saving"
    @update:model-value="!$event && emit('close')"
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
      @retry="load"
    />
    <OperationFeedback :message="feedback" action="重新查询核实" @check="load" />
    <template v-if="bill">
      <h2>{{ bill.plan_name }}</h2>
      <p class="detail-money">{{ formatMoney(bill.amount, auth.user?.currency_code) }}</p>
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
      <div class="detail-actions">
        <el-button v-if="bill.plan_status !== 'deleted'" :disabled="saving" @click="viewPlan"
          >查看关联规则</el-button
        >
        <el-button
          :type="bill.is_valid ? 'danger' : 'success'"
          :loading="saving"
          :disabled="
            loading ||
            (!bill.is_valid && bill.time_status === 'upcoming' && bill.plan_status !== 'enabled')
          "
          @click="toggle"
          >{{ bill.is_valid ? '标记无效' : '恢复有效' }}</el-button
        >
        <el-button :disabled="saving" @click="emit('close')">关闭详情</el-button>
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
}
.hint {
  color: #6b7280;
  font-size: 13px;
  margin-top: 16px;
}
.detail-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 20px;
}
.detail-actions .el-button {
  margin-left: 0;
}
</style>
