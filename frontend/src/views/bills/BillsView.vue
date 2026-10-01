<script setup lang="ts">
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/card/style/css'
import 'element-plus/es/components/date-picker/style/css'
import 'element-plus/es/components/input/style/css'
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import 'element-plus/es/components/option/style/css'
import 'element-plus/es/components/pagination/style/css'
import 'element-plus/es/components/radio-button/style/css'
import 'element-plus/es/components/radio-group/style/css'
import 'element-plus/es/components/select/style/css'
import 'element-plus/es/components/table/style/css'
import 'element-plus/es/components/table-column/style/css'
import 'element-plus/es/components/tag/style/css'

import {
  ElButton,
  ElCard,
  ElDatePicker,
  ElInput,
  ElOption,
  ElPagination,
  ElRadioButton,
  ElRadioGroup,
  ElSelect,
  ElTable,
  ElTableColumn,
  ElTag,
} from 'element-plus'
import { useQueryRequest } from '@/composables/useQueryRequest'
import { asApiError, writeErrorMessage } from '@/utils/apiErrors'
import { computed, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
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
import BillDetailDrawer from '@/components/billing/BillDetailDrawer.vue'
import OperationFeedback from '@/components/common/OperationFeedback.vue'
import { useBillDrawer } from '@/composables/useBillDrawer'
import { rememberPosition, restorePosition, returnPath } from '@/utils/navigation'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const { billId, openBill, closeBill } = useBillDrawer()
const moreFilters = ref(false),
  hasLoaded = ref(false),
  operationMessage = ref('')
let loadedKey = ''
onBeforeRouteLeave(() => {
  rememberPosition(route.fullPath)
})
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
const applied = ref(readBillQuery({}))
function restore() {
  applied.value = readBillQuery(route.query)
  page.value = applied.value.page
  pageSize.value = applied.value.page_size
  dateRange.value =
    applied.value.start_date || applied.value.end_date
      ? [applied.value.start_date, applied.value.end_date]
      : null
  timeStatus.value = applied.value.time_status
  sort.value = applied.value.sort
  keyword.value = applied.value.q
  valid.value = applied.value.is_valid as '' | 'true' | 'false'
  planId.value = applied.value.plan_id ? String(applied.value.plan_id) : ''
}
const actionId = ref<number | null>(null)
let requestSequence = 0
function cycleText(bill: BillOccurrence) {
  if (bill.cycle_type === 'custom_days' && bill.cycle_days === null) return '自定义天数'
  return formatCycle(bill.cycle_type, bill.cycle_days, bill.cycle_interval)
}
const pendingFilters = computed(
  () =>
    keyword.value.trim() !== applied.value.q ||
    valid.value !== applied.value.is_valid ||
    planId.value !== (applied.value.plan_id ? String(applied.value.plan_id) : '') ||
    sort.value !== applied.value.sort ||
    (dateRange.value?.[0] ?? '') !== applied.value.start_date ||
    (dateRange.value?.[1] ?? '') !== applied.value.end_date,
)
const queryRequests = useQueryRequest()
async function load() {
  const signal = queryRequests.next()
  const sequence = ++requestSequence
  const key = JSON.stringify({ ...applied.value, page: page.value, page_size: pageSize.value })
  if (key !== loadedKey) {
    bills.value = []
    hasLoaded.value = false
  }
  loading.value = true
  error.value = null
  try {
    const result = await listBills(
      {
        page: page.value,
        page_size: pageSize.value,
        start_date: applied.value.start_date,
        end_date: applied.value.end_date,
        time_status: applied.value.time_status === 'all' ? undefined : applied.value.time_status,
        sort: applied.value.sort,
        q: applied.value.q,
        is_valid: applied.value.is_valid === '' ? undefined : applied.value.is_valid === 'true',
        plan_id: applied.value.plan_id,
      },
      signal,
    )
    if (signal.aborted || sequence !== requestSequence) return
    total.value = result.total
    const lastPage = Math.max(1, Math.ceil(result.total / pageSize.value))
    if (page.value > lastPage) {
      page.value = lastPage
      await navigate(true)
      return
    }
    bills.value = result.items
    hasLoaded.value = true
    loadedKey = key
    void restorePosition(route.fullPath)
  } catch (cause) {
    if (signal.aborted || sequence !== requestSequence) return
    error.value = asApiError(cause, '无法连接服务器，请检查网络或服务状态。')
  } finally {
    if (!signal.aborted && sequence === requestSequence) loading.value = false
  }
}
async function navigate(replace = false) {
  queryRequests.cancel()
  ++requestSequence
  const query: Record<string, string> = {
    time_status: applied.value.time_status,
    sort: applied.value.sort,
    page: String(page.value),
    page_size: String(pageSize.value),
  }
  for (const key of ['start_date', 'end_date', 'q', 'is_valid', 'plan_id'] as const) {
    const value = applied.value[key]
    if (value !== '' && value !== undefined) query[key] = String(value)
  }
  if (route.query.return_to) query.return_to = String(route.query.return_to)
  if (billId.value) query.bill_id = String(billId.value)
  const target = { query }
  const sameFilters =
    JSON.stringify(readBillQuery(route.query)) === JSON.stringify(readBillQuery(query))
  if (router.resolve(target).fullPath === route.fullPath) {
    restore()
    await load()
  } else {
    if (replace) await router.replace(target)
    else await router.push(target)
    // Adding default URL parameters does not trigger the filter watcher.
    if (sameFilters) {
      restore()
      await load()
    }
  }
}
function query() {
  const [start = '', end = ''] = dateRange.value ?? []
  if ((start && !validDate(start)) || (end && !validDate(end)) || (start && end && start > end)) {
    ElMessage.error('请选择有效日期，开始日期不能晚于结束日期')
    return
  }
  applied.value = {
    ...applied.value,
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
  applied.value = {
    ...applied.value,
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
  applied.value = readBillQuery({})
  page.value = 1
  pageSize.value = 20
  void navigate()
}
function shortcut(kind: 'month' | 'next30' | 'lastMonth') {
  const value = dateShortcut(kind, auth.user?.timezone ?? 'UTC')
  applied.value = {
    ...applied.value,
    start_date: value.range[0]!,
    end_date: value.range[1]!,
    time_status: value.status,
    sort: value.status === 'upcoming' ? 'asc' : 'desc',
  }
  page.value = 1
  void navigate()
}
function clearFilter(key: 'q' | 'date' | 'is_valid' | 'plan_id') {
  if (key === 'date') {
    applied.value.start_date = ''
    applied.value.end_date = ''
  } else if (key === 'plan_id') applied.value.plan_id = undefined
  else applied.value[key] = ''
  page.value = 1
  void navigate()
}

function resize() {
  page.value = 1
  void navigate()
}
async function toggle(bill: BillOccurrence) {
  if (actionId.value !== null) return
  actionId.value = bill.id
  try {
    if (bill.is_valid)
      await ElMessageBox.confirm(
        '标记无效后将不再计入统计、提醒和最近账单倒计时，记录不会被删除。',
        '确认标记无效',
        { type: 'warning', confirmButtonText: '标记无效', cancelButtonText: '取消' },
      )
    operationMessage.value = ''
    await updateBillValidity(bill.id, !bill.is_valid)
    ElMessage.success(bill.is_valid ? '账单已标记无效' : '账单已恢复有效')
    await load()
  } catch (cause) {
    if (cause !== 'cancel' && cause !== 'close') operationMessage.value = writeErrorMessage(cause)
  } finally {
    actionId.value = null
  }
}
watch(
  () => JSON.stringify(readBillQuery(route.query)),
  () => {
    restore()
    void load()
  },
)
const planOptions = useQueryRequest()
onMounted(() => {
  const signal = planOptions.next()
  restore()
  void load()
  void listPlans(signal)
    .then((result) => {
      if (!signal.aborted) plans.value = result
    })
    .catch(() => {
      if (signal.aborted) return
      ElMessage.warning('规则选项加载失败，仍可按名称搜索账单')
    })
})
</script>

<template>
  <div class="page-container">
    <PageHeader title="账单记录" description="查看账单实例并调整有效性"
      ><template #actions
        ><el-button
          v-if="route.query.return_to"
          @click="router.push(returnPath(route.query.return_to))"
          >返回来源</el-button
        ><el-button :loading="loading" @click="load">刷新</el-button></template
      ></PageHeader
    >
    <OperationFeedback :message="operationMessage" action="重新查询核实" @check="load" /><el-card
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
        <el-button type="primary" @click="query">查询</el-button
        ><el-button :aria-expanded="moreFilters" @click="moreFilters = !moreFilters"
          >更多筛选</el-button
        ><el-button @click="reset">重置</el-button>
      </div>
      <div v-show="moreFilters" class="filters" @keyup.enter="query">
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
            :value="String(plan.id)"
        /></el-select>
      </div>
      <div class="filters">
        <el-button @click="shortcut('month')">本月</el-button>
        <el-button @click="shortcut('next30')">未来 30 天</el-button>
        <el-button @click="shortcut('lastMonth')">上月</el-button>
      </div>
      <p v-if="pendingFilters" class="hint" role="status">筛选已修改，点击“查询”后生效</p>
      <div class="filters" aria-label="已生效的查询条件">
        <el-tag v-if="applied.q" closable @close="clearFilter('q')">名称：{{ applied.q }}</el-tag>
        <el-tag v-if="applied.start_date || applied.end_date" closable @close="clearFilter('date')"
          >{{ applied.start_date || '不限' }} 至 {{ applied.end_date || '不限' }}</el-tag
        >
        <el-tag v-if="applied.is_valid" closable @close="clearFilter('is_valid')">{{
          applied.is_valid === 'true' ? '有效' : '无效'
        }}</el-tag>
        <el-tag v-if="applied.plan_id" closable @close="clearFilter('plan_id')"
          >规则 #{{ applied.plan_id }}</el-tag
        >
      </div>
      <LoadingBlock v-if="loading && !hasLoaded" /><ErrorState
        v-if="error"
        :message="hasLoaded ? '刷新失败，以下保留上次结果：' + error.message : error.message"
        :request-id="error.requestId"
        @retry="load" /><EmptyState
        v-if="!loading && !error && !bills.length"
        title="暂无账单实例"
        description="当前筛选条件没有账单记录" />
      <div v-if="!loading && !error && !bills.length" class="filters">
        <el-button @click="reset">清除筛选</el-button>
        <el-button @click="showHistory">查看历史</el-button>
      </div>
      <el-table v-if="bills.length" :data="bills" stripe class="desktop-bill-table"
        ><el-table-column prop="due_date" label="日期" width="130"
          ><template #default="{ row }">{{ formatDate(row.due_date) }}</template></el-table-column
        ><el-table-column prop="plan_name" label="名称" min-width="160"
          ><template #default="{ row }"
            ><el-button link type="primary" @click="openBill(row.id, $event)">{{
              row.plan_name
            }}</el-button></template
          ></el-table-column
        ><el-table-column label="金额" width="130"
          ><template #default="{ row }"
            ><MoneyText
              :value="row.amount"
              :currency="auth.user?.currency_code" /></template></el-table-column
        ><el-table-column label="周期" width="130"
          ><template #default="{ row }">{{
            cycleText(row as BillOccurrence)
          }}</template></el-table-column
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
              :disabled="
                actionId !== null ||
                (!row.is_valid &&
                  row.time_status === 'upcoming' &&
                  row.plan_status &&
                  row.plan_status !== 'enabled')
              "
              @click="toggle(row as BillOccurrence)"
              >{{ row.is_valid ? '标记无效' : '恢复有效' }}</el-button
            ></template
          ></el-table-column
        ></el-table
      >
      <div class="mobile-bill-list">
        <article v-for="bill in bills" :key="bill.id" class="mobile-record">
          <p class="hint">
            {{ bill.due_date }} · {{ bill.time_status === 'upcoming' ? '未过' : '已过' }}
          </p>
          <div class="record-line">
            <el-button link type="primary" @click="openBill(bill.id, $event)">{{
              bill.plan_name
            }}</el-button
            ><MoneyText :value="bill.amount" :currency="auth.user?.currency_code" />
          </div>
          <p class="hint">{{ cycleText(bill) }} · {{ bill.is_valid ? '有效' : '无效' }}</p>
          <el-button @click="openBill(bill.id, $event)">查看详情</el-button>
        </article>
      </div>
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
    <BillDetailDrawer :bill-id="billId" @close="closeBill" @changed="load" />
  </div>
</template>

<style scoped>
.mobile-bill-list {
  display: none;
}
.mobile-record {
  border-bottom: 1px solid #e5e7eb;
  padding: 14px 0;
}
.record-line {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}
.record-line > .el-button {
  min-width: 0;
}
.filters :deep(.el-date-editor) {
  max-width: 100%;
  min-width: 0;
}
.pagination {
  overflow-x: auto;
}
@media (max-width: 700px) {
  .desktop-bill-table {
    display: none;
  }
  .mobile-bill-list {
    display: block;
  }
  .filters :deep(.el-input),
  .filters :deep(.el-select) {
    max-width: 100%;
  }
}

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
