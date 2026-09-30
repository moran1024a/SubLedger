<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listBills, updateBillValidity } from '@/api/bills'
import { listPlans } from '@/api/plans'
import { ApiError, type BillOccurrence, type BillPlan, type BillTimeStatus } from '@/types/api'
import PageHeader from '@/components/common/PageHeader.vue'
import LoadingBlock from '@/components/common/LoadingBlock.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import MoneyText from '@/components/common/MoneyText.vue'
import { formatCycle, formatDate } from '@/utils/format'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const bills = ref<BillOccurrence[]>([])
const plans = ref<BillPlan[]>([])
const loading = ref(true)
const error = ref<ApiError | null>(null)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const start = ref<string | null>('')
const end = ref<string | null>('')
const timeStatus = ref<BillTimeStatus | ''>('')
const valid = ref<'' | 'true' | 'false'>('')
const planId = ref('')
const actionId = ref<number | null>(null)
let requestSequence = 0
function cycleText(bill: BillOccurrence) {
  if (bill.cycle_type === 'custom_days' && bill.cycle_days === null) return '自定义天数'
  return formatCycle(bill.cycle_type, bill.cycle_days)
}
async function load() {
  const sequence = ++requestSequence
  loading.value = true
  error.value = null
  try {
    const result = await listBills({
      page: page.value,
      page_size: pageSize.value,
      start_date: start.value,
      end_date: end.value,
      time_status: timeStatus.value || undefined,
      is_valid: valid.value === '' ? undefined : valid.value === 'true',
      plan_id: planId.value ? Number(planId.value) : undefined,
    })
    if (sequence !== requestSequence) return
    bills.value = result.items
    total.value = result.total
  } catch (cause) {
    if (sequence !== requestSequence) return
    error.value =
      cause instanceof ApiError
        ? cause
        : new ApiError({
            status: 0,
            code: 'NETWORK',
            message: '无法连接服务器，请检查网络或服务状态。',
          })
  } finally {
    if (sequence === requestSequence) loading.value = false
  }
}
function query() {
  page.value = 1
  load()
}
function reset() {
  page.value = 1
  start.value = ''
  end.value = ''
  timeStatus.value = ''
  valid.value = ''
  planId.value = ''
  load()
}
async function toggle(bill: BillOccurrence) {
  if (actionId.value !== null) return
  try {
    if (bill.is_valid)
      await ElMessageBox.confirm(
        '标记无效后将不再计入统计、提醒和最近账单倒计时，记录不会被删除。',
        '确认标记无效',
        { type: 'warning', confirmButtonText: '标记无效', cancelButtonText: '取消' },
      )
    actionId.value = bill.id
    await updateBillValidity(bill.id, !bill.is_valid)
    ElMessage.success(bill.is_valid ? '账单已标记无效' : '账单已恢复有效')
    await load()
  } catch (cause) {
    if (cause !== 'cancel' && cause !== 'close')
      ElMessage.error(cause instanceof ApiError ? cause.message : '操作失败')
  } finally {
    actionId.value = null
  }
}
onMounted(async () => {
  try {
    plans.value = await listPlans()
  } catch {
    /* bill query still gives useful result */
  }
  await load()
})
</script>

<template>
  <div class="page-container">
    <PageHeader title="账单记录" description="查看账单实例并调整有效性" /><el-card
      class="content-card"
      ><div class="filters">
        <el-date-picker
          v-model="start"
          value-format="YYYY-MM-DD"
          type="date"
          placeholder="开始日期"
        /><el-date-picker
          v-model="end"
          value-format="YYYY-MM-DD"
          type="date"
          placeholder="结束日期"
        /><el-select v-model="timeStatus" clearable placeholder="时间状态" style="width: 140px"
          ><el-option label="未过" value="upcoming" /><el-option
            label="已过"
            value="passed" /></el-select
        ><el-select v-model="valid" clearable placeholder="有效性" style="width: 120px"
          ><el-option label="有效" value="true" /><el-option
            label="无效"
            value="false" /></el-select
        ><el-select v-model="planId" clearable placeholder="账单规则" style="width: 180px"
          ><el-option
            v-for="plan in plans"
            :key="plan.id"
            :label="plan.name"
            :value="String(plan.id)" /></el-select
        ><el-button type="primary" @click="query">查询</el-button
        ><el-button @click="reset">重置</el-button>
      </div>
      <LoadingBlock v-if="loading" /><ErrorState
        v-else-if="error"
        :message="error.message"
        :request-id="error.requestId"
        @retry="load" /><EmptyState
        v-else-if="!bills.length"
        title="暂无账单实例"
        description="当前筛选条件没有账单记录" /><el-table v-else :data="bills" stripe
        ><el-table-column prop="due_date" label="日期" width="130"
          ><template #default="{ row }">{{ formatDate(row.due_date) }}</template></el-table-column
        ><el-table-column prop="plan_name" label="名称" min-width="160" /><el-table-column
          label="金额"
          width="130"
          ><template #default="{ row }"
            ><MoneyText
              :value="row.amount"
              :currency="auth.user?.currency_code" /></template></el-table-column
        ><el-table-column label="周期" width="130"
          ><template #default="{ row }">{{ cycleText(row) }}</template></el-table-column
        ><el-table-column label="时间状态" width="100"
          ><template #default="{ row }"
            ><el-tag :type="row.time_status === 'upcoming' ? 'warning' : 'info'">{{
              row.time_status === 'upcoming' ? '未过' : '已过'
            }}</el-tag></template
          ></el-table-column
        ><el-table-column label="有效性" width="100"
          ><template #default="{ row }"
            ><StatusTag
              :active="row.is_valid"
              active-text="有效"
              inactive-text="无效" /></template></el-table-column
        ><el-table-column label="操作" width="130" fixed="right"
          ><template #default="{ row }"
            ><el-button
              link
              :type="row.is_valid ? 'danger' : 'success'"
              :loading="actionId === row.id"
              :disabled="actionId !== null"
              @click="toggle(row)"
              >{{ row.is_valid ? '标记无效' : '恢复有效' }}</el-button
            ></template
          ></el-table-column
        ></el-table
      >
      <div v-if="total > pageSize" class="pagination">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="load"
        /></div
    ></el-card>
  </div>
</template>

<style scoped>
.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 18px;
}
.pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 18px;
}
</style>
