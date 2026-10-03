<script setup lang="ts">
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/card/style/css'
import 'element-plus/es/components/empty/style/css'
import { ElButton, ElCard, ElEmpty } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useQueryRequest } from '@/composables/useQueryRequest'
import { useBillDrawer } from '@/composables/useBillDrawer'
import { useCountUp } from '@/composables/useCountUp'
import { asApiError } from '@/utils/apiErrors'
import { getSummary } from '@/api/statistics'
import { listBills } from '@/api/bills'
import { ApiError, type StatisticsResponse, type BillOccurrence } from '@/types/api'
import { useAuthStore } from '@/stores/auth'
import { formatMoney, formatCycle, formatDaysRemaining } from '@/utils/format'
import { dateShortcut } from '@/utils/billFilters'
import PageHeader from '@/components/common/PageHeader.vue'
import LoadingBlock from '@/components/common/LoadingBlock.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import BillDetailDrawer from '@/components/billing/BillDetailDrawer.vue'
import OperationFeedback from '@/components/common/OperationFeedback.vue'
import NavIcon from '@/components/common/NavIcon.vue'
import DateBadge from '@/components/common/DateBadge.vue'
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
const { billId, invalidBillId, openBill, closeBill } = useBillDrawer()
const drawerBusy = ref(false)
const refreshKey = ref(0)
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
      refreshKey.value += 1
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
// Count-up only plays when statistics first arrive; later refreshes replace the numbers.
const todayAmount = useCountUp(computed(() => data.value?.today.amount ?? null))
const monthAmount = useCountUp(computed(() => data.value?.current_month.amount ?? null))
const yearAmount = useCountUp(computed(() => data.value?.current_year.amount ?? null))
const metrics = computed(() =>
  data.value
    ? [
        {
          key: 'today',
          title: '今日',
          icon: 'calendar',
          amount: todayAmount.value,
          count: `${data.value.today.count} 笔有效账单`,
        },
        {
          key: 'month',
          title: '本月预计',
          icon: 'bills',
          amount: monthAmount.value,
          count: `${data.value.current_month.count} 笔（含未来推算）`,
        },
        {
          key: 'year',
          title: '全年预计',
          icon: 'logs',
          amount: yearAmount.value,
          count: `${data.value.current_year.count} 笔（含未来推算）`,
        },
      ]
    : [],
)
const nextBill = computed(() => data.value?.next_bill ?? null)
const canOpenNext = computed(() => nextBill.value?.bill_id != null && !drawerBusy.value)
function openNext(event?: Parameters<typeof openBill>[1]) {
  const id = nextBill.value?.bill_id
  if (id != null) void openBill(id, event)
}
const quickEntries = [
  {
    to: '/plans',
    icon: 'calendar',
    title: '管理账单规则',
    description: '新建、编辑、停用或删除规则',
  },
  { to: '/bills', icon: 'bills', title: '查询账单', description: '按日期、规则和有效性查找账单' },
  {
    to: '/settings/notifications',
    icon: 'bell',
    title: '配置提醒',
    description: '设置邮件、飞书和提醒时间',
  },
]
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
        ><el-button :disabled="drawerBusy" :loading="loading || billsLoading" @click="refresh"
          >刷新</el-button
        ><el-button type="primary" :disabled="drawerBusy" @click="router.push('/plans/new')"
          >新建规则</el-button
        ></template
      >
    </PageHeader>
    <OperationFeedback
      v-if="invalidBillId"
      message="账单详情链接无效，请清除链接后重新选择账单。"
      action="清除无效链接"
      @check="closeBill"
    />
    <LoadingBlock v-if="loading && !data" variant="stats" />
    <ErrorState
      v-if="error"
      :message="data ? '统计刷新失败，以下保留上次结果：' + error.message : error.message"
      :request-id="error.requestId"
      @retry="load"
    />
    <template v-if="data">
      <div class="card-grid metric-grid sl-stagger">
        <el-card
          v-for="(metric, index) in metrics"
          :key="metric.key"
          class="metric-card"
          :style="{ '--i': index }"
          ><div class="metric-head">
            <span class="metric-icon"><NavIcon :name="metric.icon" /></span
            ><span class="metric-label">{{ metric.title }}</span>
          </div>
          <strong class="metric-number tabular-nums">{{ money(metric.amount || '0') }}</strong
          ><span class="metric-count">{{ metric.count }}</span>
          <div class="metric-footer">
            <el-button text type="primary" @click="viewPeriod(metric.key)"
              >查看已生成账单</el-button
            >
          </div></el-card
        ><el-card
          class="metric-card next-card"
          :class="{ 'sl-lift': nextBill?.bill_id != null }"
          :style="{ '--i': 3 }"
          ><div class="metric-head">
            <span class="metric-icon"><NavIcon name="bell" /></span
            ><span class="metric-label">下一笔账单</span>
          </div>
          <button
            v-if="nextBill"
            type="button"
            class="next-bill"
            title="查看账单详情"
            :disabled="!canOpenNext"
            @click="openNext"
          >
            <span class="next-name">{{ nextBill.name }}</span
            ><strong class="metric-number tabular-nums">{{ money(nextBill.amount) }}</strong
            ><span class="metric-count"
              >{{ nextBill.due_date }} · {{ formatDaysRemaining(nextBill.days_remaining) }}</span
            >
          </button>
          <template v-else>
            <p class="metric-empty">暂无未过账单</p>
            <div class="metric-footer">
              <el-button text type="primary" @click="router.push('/plans/new')">新建规则</el-button>
            </div>
          </template></el-card
        >
      </div>
      <el-card class="content-card"
        ><div class="average-row">
          <span class="stat-chip"
            >折算月均<strong class="tabular-nums">{{ money(data.averages.monthly) }}</strong></span
          ><span class="stat-chip"
            >折算日均<strong class="tabular-nums">{{ money(data.averages.daily) }}</strong></span
          >
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
      <LoadingBlock v-if="billsLoading && !billsLoaded" variant="table" />
      <ErrorState
        v-if="billsError"
        :message="
          billsLoaded ? '账单刷新失败，以下保留上次结果：' + billsError.message : billsError.message
        "
        :request-id="billsError.requestId"
        @retry="loadBills"
      />
      <div class="upcoming-list sl-stagger">
        <div
          v-for="(bill, index) in upcoming"
          :key="bill.id"
          class="upcoming-row"
          :style="{ '--i': Math.min(index, 8) }"
        >
          <DateBadge :date="bill.due_date" :today="bill.due_date === data?.date" />
          <div class="upcoming-main">
            <el-button
              link
              type="primary"
              :disabled="drawerBusy"
              @click="openBill(bill.id, $event)"
              >{{ bill.plan_name }}</el-button
            >
            <p>
              {{ bill.due_date }}{{ bill.due_date === data?.date ? ' · 今天' : '' }} ·
              {{ formatCycle(bill.cycle_type, bill.cycle_days, bill.cycle_interval) }}
            </p>
          </div>
          <strong class="numeric">{{ money(bill.amount) }}</strong
          ><el-button :disabled="drawerBusy" @click="openBill(bill.id, $event)">查看</el-button>
        </div>
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
      <router-link
        v-for="entry in quickEntries"
        :key="entry.to"
        :to="entry.to"
        class="quick-link sl-lift"
        ><el-card class="quick-card"
          ><span class="metric-icon"><NavIcon :name="entry.icon" /></span>
          <div>
            <strong>{{ entry.title }}</strong>
            <p>{{ entry.description }}</p>
          </div></el-card
        ></router-link
      >
    </div>
    <BillDetailDrawer
      :bill-id="billId"
      :refresh-key="refreshKey"
      @busy="drawerBusy = $event"
      @close="closeBill"
      @changed="refresh"
    />
  </div>
</template>
<style scoped>
.metric-card :deep(.el-card__body) {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-width: 0;
}
.metric-head {
  display: flex;
  align-items: center;
  gap: var(--sl-space-3);
}
.metric-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: var(--sl-radius-sm);
  background: var(--sl-primary-soft);
  color: var(--sl-primary);
}
.metric-label {
  color: var(--sl-text-secondary);
  font-weight: 500;
}
.metric-number {
  display: block;
  margin: var(--sl-space-3) 0 var(--sl-space-1);
  font-size: var(--sl-number-size);
  font-weight: 600;
  line-height: 1.25;
  overflow-wrap: anywhere;
}
.metric-count,
.metric-empty {
  color: var(--sl-text-muted);
  font-size: var(--sl-font-size-sm);
}
.metric-empty {
  margin: var(--sl-space-4) 0 0;
}
.metric-footer {
  margin-top: auto;
  padding-top: var(--sl-space-2);
}
.metric-footer .el-button {
  padding-inline: 0;
}
.next-bill {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  width: 100%;
  margin: var(--sl-space-3) 0 0;
  padding: 0;
  border: 0;
  background: none;
  color: inherit;
  text-align: left;
  cursor: pointer;
}
.next-bill:disabled {
  cursor: default;
}
.next-bill .metric-number {
  margin: var(--sl-space-1) 0;
}
.next-name {
  max-width: 100%;
  font-weight: 600;
  overflow-wrap: anywhere;
}
.next-bill:not(:disabled):hover .next-name {
  color: var(--sl-primary);
}
.upcoming-row {
  display: flex;
  gap: var(--sl-space-4);
  align-items: center;
  border-bottom: 1px solid var(--sl-border);
  padding: var(--sl-space-3) 0;
}
.upcoming-main {
  flex: 1;
  min-width: 0;
}
.upcoming-row p,
.muted,
details {
  color: var(--sl-text-muted);
  font-size: var(--sl-font-size-sm);
}
.upcoming-row p {
  margin: 4px 0 0;
}
.average-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sl-space-3);
  margin-bottom: var(--sl-space-3);
}
.stat-chip {
  display: inline-flex;
  align-items: baseline;
  gap: var(--sl-space-2);
  padding: 6px var(--sl-space-3);
  border-radius: 999px;
  background: var(--sl-surface-muted);
  border: 1px solid var(--sl-border);
  color: var(--sl-text-secondary);
  font-size: var(--sl-font-size-sm);
}
.stat-chip strong {
  color: var(--sl-text);
  font-size: var(--sl-font-size);
  font-weight: 600;
}
summary {
  cursor: pointer;
}
.next-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}
.quick-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--sl-space-4);
}
.quick-link {
  display: block;
  border-radius: var(--sl-radius);
}
.quick-card {
  height: 100%;
}
.quick-card :deep(.el-card__body) {
  display: flex;
  align-items: flex-start;
  gap: var(--sl-space-3);
}
.quick-card strong {
  font-weight: 600;
}
.quick-card p {
  margin: 2px 0 0;
  color: var(--sl-text-muted);
  font-size: var(--sl-font-size-sm);
}
.content-card {
  margin-top: 20px;
}
.upcoming-row :deep(.el-button.is-link) {
  white-space: normal;
  text-align: left;
  overflow-wrap: anywhere;
}
.upcoming-row > strong {
  text-align: right;
  min-width: 100px;
  overflow-wrap: anywhere;
}
@media (max-width: 700px) {
  .quick-grid {
    grid-template-columns: 1fr;
  }
  .next-content {
    align-items: flex-start;
    flex-direction: column;
  }
  .upcoming-row {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    gap: 10px;
  }
  .upcoming-row > .date-badge {
    grid-row: span 2;
  }
  .upcoming-row > strong {
    min-width: 0;
  }
  .upcoming-row > .el-button {
    grid-column: 3;
    justify-self: end;
  }
}
</style>
