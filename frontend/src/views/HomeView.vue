<script setup lang="ts">
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/card/style/css'
import 'element-plus/es/components/empty/style/css'
import { ElButton, ElCard, ElEmpty } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useQueryRequest } from '@/composables/useQueryRequest'
import { useBillDrawer } from '@/composables/useBillDrawer'
import { asApiError } from '@/utils/apiErrors'
import { getSummary } from '@/api/statistics'
import { listBills } from '@/api/bills'
import { ApiError, type StatisticsResponse, type BillOccurrence } from '@/types/api'
import { useAuthStore } from '@/stores/auth'
import { formatMoney, formatCycle } from '@/utils/format'
import { dateShortcut } from '@/utils/billFilters'
import PageHeader from '@/components/common/PageHeader.vue'
import LoadingBlock from '@/components/common/LoadingBlock.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import BillDetailDrawer from '@/components/billing/BillDetailDrawer.vue'
const auth = useAuthStore(),
  router = useRouter()
const data = ref<StatisticsResponse | null>(null),
  upcoming = ref<BillOccurrence[]>([])
const loading = ref(true),
  billsLoading = ref(true),
  billsLoaded = ref(false)
const error = ref<ApiError | null>(null),
  billsError = ref<ApiError | null>(null)
const queries = useQueryRequest(),
  billQueries = useQueryRequest()
const { billId, openBill, closeBill } = useBillDrawer()
const money = (value: string) => formatMoney(value, auth.user?.currency_code)
async function load() {
  const signal = queries.next()
  loading.value = true
  error.value = null
  try {
    const result = await getSummary(signal)
    if (!signal.aborted) data.value = result
  } catch (cause) {
    if (!signal.aborted) error.value = asApiError(cause)
  } finally {
    if (!signal.aborted) loading.value = false
  }
}
async function loadBills() {
  const signal = billQueries.next()
  billsLoading.value = true
  billsError.value = null
  try {
    const result = await listBills(
      { time_status: 'upcoming', is_valid: true, sort: 'asc', page_size: 10 },
      signal,
    )
    if (!signal.aborted) {
      upcoming.value = result.items
      billsLoaded.value = true
    }
  } catch (cause) {
    if (!signal.aborted) billsError.value = asApiError(cause)
  } finally {
    if (!signal.aborted) billsLoading.value = false
  }
}
function refresh() {
  void load()
  void loadBills()
}
const totals = computed(() =>
  data.value
    ? [
        {
          key: 'today',
          title: '今日有效账单',
          amount: data.value.today.amount,
          count: data.value.today.count,
        },
        {
          key: 'month',
          title: '本月预计金额',
          amount: data.value.current_month.amount,
          count: data.value.current_month.count,
        },
        {
          key: 'year',
          title: '全年预计金额',
          amount: data.value.current_year.amount,
          count: data.value.current_year.count,
        },
      ]
    : [],
)
function viewPeriod(kind: string) {
  const today = data.value?.date ?? dateShortcut('next30', auth.user?.timezone ?? 'UTC').range[0]!
  const monthEnd = new Date(
    Date.UTC(Number(today.slice(0, 4)), Number(today.slice(5, 7)), 0),
  ).getUTCDate()
  const range =
    kind === 'today'
      ? [today, today]
      : kind === 'month'
        ? [today.slice(0, 7) + '-01', today.slice(0, 7) + '-' + monthEnd]
        : [today.slice(0, 4) + '-01-01', today.slice(0, 4) + '-12-31']
  void router.push({
    path: '/bills',
    query: {
      time_status: 'all',
      is_valid: 'true',
      start_date: range[0],
      end_date: range[1],
      sort: 'asc',
    },
  })
}
onMounted(refresh)
</script>
<template>
  <div class="page-container">
    <PageHeader title="首页" description="查看有效账单与预计金额，日期按账户时区划分">
      <template #actions
        ><el-button :loading="loading || billsLoading" @click="refresh">刷新</el-button
        ><el-button type="primary" @click="router.push('/plans/new')">新建规则</el-button></template
      >
    </PageHeader>
    <LoadingBlock v-if="loading && !data" />
    <ErrorState
      v-if="error"
      :message="data ? '统计刷新失败，以下保留上次结果：' + error.message : error.message"
      :request-id="error.requestId"
      @retry="load"
    />
    <template v-if="data">
      <div class="card-grid">
        <el-card v-for="metric in totals" :key="metric.key"
          ><div class="metric-label">{{ metric.title }}</div>
          <strong>{{ money(metric.amount) }}</strong
          ><span>{{ metric.count }} 笔{{ metric.key === 'today' ? '' : '（含未来推算）' }}</span>
          <div>
            <el-button text type="primary" @click="viewPeriod(metric.key)"
              >查看已生成账单</el-button
            >
          </div></el-card
        >
      </div>
      <el-card class="content-card"
        ><div class="average-row">
          <span>折算月均 {{ money(data.averages.monthly) }}</span
          ><span>折算日均 {{ money(data.averages.daily) }}</span>
        </div>
        <details>
          <summary>统计口径说明</summary>
          <p>
            预计金额包含已生成的有效账单和未来按规则推算的金额，可能不同于明细合计；月均、日均按启用的周期规则折算，排除单次账单。所有金额均不代表付款状态。
          </p>
        </details></el-card
      >
    </template>
    <el-card class="content-card"
      ><template #header
        ><div class="next-content">
          <span>近期账单 · 已生成</span
          ><el-button
            text
            type="primary"
            @click="
              router.push({ path: '/bills', query: { time_status: 'upcoming', is_valid: 'true' } })
            "
            >查看全部</el-button
          >
        </div></template
      >
      <LoadingBlock v-if="billsLoading && !billsLoaded" />
      <ErrorState
        v-if="billsError"
        :message="
          billsLoaded ? '账单刷新失败，以下保留上次结果：' + billsError.message : billsError.message
        "
        :request-id="billsError.requestId"
        @retry="loadBills"
      />
      <div v-for="bill in upcoming" :key="bill.id" class="upcoming-row">
        <div>
          <el-button link type="primary" @click="openBill(bill.id, $event)">{{
            bill.plan_name
          }}</el-button>
          <p>
            {{ bill.due_date }}{{ bill.due_date === data?.date ? ' · 今天' : '' }} ·
            {{ formatCycle(bill.cycle_type, bill.cycle_days, bill.cycle_interval) }}
          </p>
        </div>
        <strong>{{ money(bill.amount) }}</strong
        ><el-button @click="openBill(bill.id, $event)">查看</el-button>
      </div>
      <el-empty
        v-if="!billsLoading && !billsError && !upcoming.length"
        description="暂无有效未过账单"
        ><el-button @click="router.push('/plans/new')">新建规则</el-button
        ><el-button @click="router.push({ path: '/bills', query: { time_status: 'passed' } })"
          >查看历史</el-button
        ></el-empty
      >
      <p class="muted">最多展示最近 10 笔有效未过账单。</p>
    </el-card>
    <div class="quick-grid">
      <router-link to="/plans"><el-card shadow="hover">管理账单规则</el-card></router-link
      ><router-link to="/bills"><el-card shadow="hover">查询账单</el-card></router-link
      ><router-link to="/settings/notifications"
        ><el-card shadow="hover">配置提醒</el-card></router-link
      >
    </div>
    <BillDetailDrawer :bill-id="billId" @close="closeBill" @changed="refresh" />
  </div>
</template>
<style scoped>
.upcoming-row {
  display: flex;
  gap: 16px;
  align-items: center;
  border-bottom: 1px solid #e5e7eb;
  padding: 14px 0;
}
.upcoming-row > div {
  flex: 1;
  min-width: 0;
}
.upcoming-row p,
.muted,
details {
  color: #6b7280;
  font-size: 13px;
}
.upcoming-row p {
  margin: 6px 0 0;
}
.average-row {
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
  margin-bottom: 12px;
}
summary {
  cursor: pointer;
}

.card-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
.card-grid strong {
  display: block;
  font-size: 22px;
  margin: 12px 0 5px;
}
.card-grid span {
  color: #6b7280;
  font-size: 13px;
}
.metric-label {
  color: #6b7280;
}
.next-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}
.next-content p {
  color: #6b7280;
}
.quick-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}
.quick-grid .el-card {
  text-align: center;
}
.content-card {
  margin-top: 20px;
}
@media (max-width: 1100px) {
  .card-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}
@media (max-width: 640px) {
  .card-grid,
  .quick-grid {
    grid-template-columns: 1fr;
  }
  .next-content {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
