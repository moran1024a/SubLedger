<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { dateShortcut, readBillQuery, validDate } from '@/utils/billFilters'
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
const route = useRoute()
const router = useRouter()
const bills = ref<BillOccurrence[]>([])
const plans = ref<BillPlan[]>([])
const loading = ref(true)
const error = ref<ApiError | null>(null)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const dateRange = ref<string[] | null>(null)
const timeStatus = ref<BillTimeStatus | 'all'>('upcoming')
const sort = ref<'asc' | 'desc'>('asc')
const keyword = ref('')
const valid = ref<'' | 'true' | 'false'>('')
const planId = ref('')
let applied = readBillQuery({})
function restore() {
  applied = readBillQuery(route.query)
  page.value = applied.page
  pageSize.value = applied.page_size
  dateRange.value =
    applied.start_date || applied.end_date ? [applied.start_date, applied.end_date] : null
  timeStatus.value = applied.time_status
  sort.value = applied.sort
  keyword.value = applied.q
  valid.value = applied.is_valid as '' | 'true' | 'false'
  planId.value = applied.plan_id ? String(applied.plan_id) : ''
}
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
      start_date: applied.start_date,
      end_date: applied.end_date,
      time_status: applied.time_status === 'all' ? undefined : applied.time_status,
      sort: applied.sort,
      q: applied.q,
      is_valid: applied.is_valid === '' ? undefined : applied.is_valid === 'true',
      plan_id: applied.plan_id,
    })
    if (sequence !== requestSequence) return
    total.value = result.total
    const lastPage = Math.max(1, Math.ceil(result.total / pageSize.value))
    if (page.value > lastPage) {
      page.value = lastPage
      await navigate(true)
      return
    }
    bills.value = result.items
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
async function navigate(replace = false) {
  ++requestSequence
  const query: Record<string, string> = {
    time_status: applied.time_status,
    sort: applied.sort,
    page: String(page.value),
    page_size: String(pageSize.value),
  }
  for (const key of ['start_date', 'end_date', 'q', 'is_valid', 'plan_id'] as const) {
    const value = applied[key]
    if (value !== '' && value !== undefined) query[key] = String(value)
  }
  const target = { query }
  if (router.resolve(target).fullPath === route.fullPath) {
    restore()
    await load()
  } else if (replace) await router.replace(target)
  else await router.push(target)
}
function query() {
  const [start = '', end = ''] = dateRange.value ?? []
  if ((start && !validDate(start)) || (end && !validDate(end)) || (start && end && start > end)) {
    ElMessage.error('请选择有效日期，开始日期不能晚于结束日期')
    return
  }
  applied = {
    ...applied,
    start_date: start,
    end_date: end,
    time_status: timeStatus.value,
    sort: sort.value,
    q: keyword.value.trim(),
    is_valid: valid.value,
    plan_id: planId.value ? Number(planId.value) : undefined,
  }
  page.value = 1
  void navigate()
}
function changeStatus() {
  // Tabs operate on the submitted filters, never silently submit draft fields.
  applied = {
    ...applied,
    time_status: timeStatus.value,
    sort: timeStatus.value === 'upcoming' ? 'asc' : 'desc',
    start_date: '',
    end_date: '',
  }
  page.value = 1
  void navigate()
}
function showHistory() {
  timeStatus.value = 'passed'
  changeStatus()
}
function reset() {
  applied = readBillQuery({})
  page.value = 1
  pageSize.value = 20
  void navigate()
}
function shortcut(kind: 'month' | 'next30' | 'lastMonth') {
  const value = dateShortcut(kind, auth.user?.timezone ?? 'UTC')
  dateRange.value = value.range
  timeStatus.value = value.status
  sort.value = value.status === 'upcoming' ? 'asc' : 'desc'
  query()
}
function resize() {
  page.value = 1
  void navigate()
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
watch(
  () => route.fullPath,
  () => {
    restore()
    void load()
  },
)
onMounted(() => {
  restore()
  void load()
  void listPlans()
    .then((result) => {
      plans.value = result
    })
    .catch(() => {
      ElMessage.warning('规则选项加载失败，仍可按名称搜索账单')
    })
})
</script>

<template>
  <div class="page-container">
    <PageHeader title="账单记录" description="查看账单实例并调整有效性" /><el-card
      class="content-card"
    >
      <el-radio-group v-model="timeStatus" class="status-tabs" @change="changeStatus">
        <el-radio-button value="upcoming">未过账单</el-radio-button>
        <el-radio-button value="passed">已过账单</el-radio-button>
        <el-radio-button value="all">全部账单</el-radio-button>
      </el-radio-group>
      <p class="hint">
        按账户时区划分，今天计入未过账单；时间状态不代表付款状态。切换标签会清除日期范围。
      </p>
      <div class="filters" @keyup.enter="query">
        <el-input
          v-model="keyword"
          clearable
          maxlength="128"
          placeholder="搜索账单名称"
          style="width: 200px"
        />
        <el-date-picker
          v-model="dateRange"
          value-format="YYYY-MM-DD"
          type="daterange"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
        />
        <el-select v-model="sort" style="width: 140px">
          <el-option label="日期升序" value="asc" /><el-option
            label="日期降序"
            value="desc"
          /> </el-select
        ><el-select v-model="valid" clearable placeholder="有效性" style="width: 120px"
          ><el-option label="有效" value="true" /><el-option
            label="无效"
            value="false" /></el-select
        ><el-select
          v-model="planId"
          filterable
          clearable
          placeholder="账单规则"
          style="width: 180px"
          ><el-option
            v-for="plan in plans"
            :key="plan.id"
            :label="plan.name"
            :value="String(plan.id)" /></el-select
        ><el-button type="primary" @click="query">查询</el-button
        ><el-button @click="reset">重置</el-button>
      </div>
      <div class="filters">
        <el-button @click="shortcut('month')">本月</el-button>
        <el-button @click="shortcut('next30')">未来 30 天</el-button>
        <el-button @click="shortcut('lastMonth')">上月</el-button>
      </div>
      <LoadingBlock v-if="loading" /><ErrorState
        v-else-if="error"
        :message="error.message"
        :request-id="error.requestId"
        @retry="load" /><EmptyState
        v-else-if="!bills.length"
        title="暂无账单实例"
        description="当前筛选条件没有账单记录" />
      <div v-if="!loading && !error && !bills.length" class="filters">
        <el-button @click="reset">清除筛选</el-button>
        <el-button @click="showHistory">查看历史</el-button>
      </div>
      <el-table v-if="!loading && !error && bills.length" :data="bills" stripe
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
      <div class="pagination">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[20, 50, 100]"
          :total="total"
          layout="total, sizes, prev, pager, next"
          @current-change="navigate()"
          @size-change="resize"
        /></div
    ></el-card>
  </div>
</template>

<style scoped>
.hint {
  color: #6b7280;
  font-size: 13px;
}
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
