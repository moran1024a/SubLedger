<script setup lang="ts">
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/card/style/css'
import { ElButton, ElCard } from 'element-plus'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getBillCalendar } from '@/api/calendar'
import { useQueryRequest } from '@/composables/useQueryRequest'
import { useAuthStore } from '@/stores/auth'
import { asApiError } from '@/utils/apiErrors'
import { dateShortcut } from '@/utils/billFilters'
import {
  dayInMonth,
  monthCells,
  shiftDay,
  shiftMonth,
  MIN_CALENDAR_MONTH,
  MAX_CALENDAR_MONTH,
} from '@/utils/calendar'
import { formatCycle, formatMoney } from '@/utils/format'
import type { ApiError, BillCalendarResponse, CalendarBill } from '@/types/api'
import ErrorState from '@/components/common/ErrorState.vue'
import LoadingBlock from '@/components/common/LoadingBlock.vue'
import NavIcon from '@/components/common/NavIcon.vue'

const props = defineProps<{ refreshKey?: number; disabled?: boolean }>()
const emit = defineEmits<{ openBill: [id: number, event: globalThis.Event] }>()
const auth = useAuthStore()
const router = useRouter(),
  route = useRoute()
const today = ref(dateShortcut('next30', auth.user?.timezone ?? 'UTC').range[0]!)
const month = ref(today.value.slice(0, 7))
const selected = ref(today.value)
const data = ref<BillCalendarResponse | null>(null)
const loading = ref(true)
const error = ref<ApiError | null>(null)
const grid = ref<HTMLElement | null>(null)
const requests = useQueryRequest()
const weekdays = ['一', '二', '三', '四', '五', '六', '日']
const current = computed(() => (data.value?.month === month.value ? data.value : null))
const days = computed(() => new Map(current.value?.days.map((day) => [day.date, day]) ?? []))
const selectedDay = computed(() => days.value.get(selected.value))
const weeks = computed(() => {
  const cells = monthCells(month.value)
  return Array.from({ length: 6 }, (_, index) => cells.slice(index * 7, index * 7 + 7))
})
const monthLabel = computed(
  () => `${Number(month.value.slice(0, 4))} 年 ${Number(month.value.slice(5))} 月`,
)
const selectedLabel = computed(
  () => `${Number(selected.value.slice(5, 7))} 月 ${Number(selected.value.slice(8))} 日`,
)
const money = (amount: string) => formatMoney(amount, auth.user?.currency_code)
function timing(day: string) {
  return day < today.value ? 'past' : day === today.value ? 'today' : 'future'
}
function timingLabel(day: string) {
  return day < today.value ? '历史' : day === today.value ? '今天' : '未来'
}
function cellLabel(day: string) {
  if (!day.startsWith(month.value)) return `${day}，切换月份`
  const value = days.value.get(day)
  const description = !current.value
    ? '账单尚未加载'
    : value
      ? `${value.count} 笔账单，合计 ${money(value.amount)}${value.estimated_count ? `，其中 ${value.estimated_count} 笔预计` : ''}`
      : '无有效账单'
  return `${day}，${timingLabel(day)}，${description}`
}
async function load(goToCurrentMonth = false) {
  const signal = requests.next()
  loading.value = true
  error.value = null
  try {
    const result = await getBillCalendar(goToCurrentMonth ? undefined : month.value, signal)
    if (signal.aborted) return
    today.value = result.today
    if (goToCurrentMonth) {
      month.value = result.month
      selected.value = result.today
    }
    data.value = result
  } catch (cause) {
    if (!signal.aborted) error.value = asApiError(cause)
  } finally {
    if (!signal.aborted) loading.value = false
  }
}
function selectDay(day: string) {
  if (props.disabled) return
  selected.value = day
  const targetMonth = day.slice(0, 7)
  if (targetMonth !== month.value) {
    month.value = targetMonth
    void load()
  }
}
function changeMonth(offset: number) {
  if (props.disabled) return
  const target = shiftMonth(month.value, offset)
  if (!target) return
  month.value = target
  selected.value = today.value.startsWith(target) ? today.value : `${target}-01`
  void load()
}
function goToday() {
  if (props.disabled) return
  // Ask the server again so a page left open overnight uses the current account date.
  month.value = today.value.slice(0, 7)
  selected.value = today.value
  void load(true)
}
async function onDayKey(event: globalThis.KeyboardEvent, day: string) {
  if (props.disabled) return
  let target: string | null = null
  const offsets: Record<string, number> = {
    ArrowLeft: -1,
    ArrowRight: 1,
    ArrowUp: -7,
    ArrowDown: 7,
  }
  if (event.key in offsets) target = shiftDay(day, offsets[event.key]!)
  else if (event.key === 'Home' || event.key === 'End') {
    const weekday = (new Date(`${day}T00:00:00Z`).getUTCDay() + 6) % 7
    target = shiftDay(day, event.key === 'Home' ? -weekday : 6 - weekday)
  } else if (event.key === 'PageUp' || event.key === 'PageDown') {
    const targetMonth = shiftMonth(day.slice(0, 7), event.key === 'PageUp' ? -1 : 1)
    if (targetMonth) target = dayInMonth(day, targetMonth)
  } else return
  event.preventDefault()
  if (!target) return
  selectDay(target)
  await nextTick()
  grid.value?.querySelector<HTMLElement>(`[data-date="${target}"]`)?.focus()
}
function openEntry(bill: CalendarBill, event: globalThis.Event) {
  if (props.disabled || loading.value || error.value) return
  if (bill.bill_id != null) emit('openBill', bill.bill_id, event)
  else void router.push({ path: `/plans/${bill.plan_id}`, query: { return_to: route.fullPath } })
}
watch(
  () => props.refreshKey,
  () => {
    void load()
  },
)
onMounted(() => {
  void load(true)
})
</script>

<template>
  <el-card class="content-card bill-calendar">
    <div class="calendar-heading">
      <div class="calendar-title">
        <span class="calendar-icon"><NavIcon name="calendar" /></span>
        <div>
          <h2>账单日历</h2>
          <p class="calendar-caption" aria-live="polite">
            <template v-if="loading">正在加载账单…</template>
            <template v-else-if="current"
              >当月 {{ current.count }} 笔 · 合计 {{ money(current.amount)
              }}<span v-if="current.estimated_count">
                · 含 {{ current.estimated_count }} 笔预计</span
              ></template
            >
            <template v-else>选择日期查看账单</template>
          </p>
        </div>
      </div>
      <div class="month-navigation">
        <el-button
          class="month-arrow"
          :disabled="disabled || month === MIN_CALENDAR_MONTH"
          aria-label="上个月"
          title="上个月"
          @click="changeMonth(-1)"
          ><NavIcon name="chevron"
        /></el-button>
        <strong class="month-label" aria-live="polite"
          >{{ monthLabel
          }}<span v-if="month === today.slice(0, 7)" class="current-month">本月</span></strong
        >
        <el-button
          class="month-arrow next-month"
          :disabled="disabled || month === MAX_CALENDAR_MONTH"
          aria-label="下个月"
          title="下个月"
          @click="changeMonth(1)"
          ><NavIcon name="chevron"
        /></el-button>
        <el-button class="today-button" :disabled="disabled" @click="goToday">回到本月</el-button>
      </div>
    </div>
    <ErrorState
      v-if="error"
      compact
      :message="current ? `刷新失败，保留上次结果：${error.message}` : error.message"
      :request-id="error.requestId"
      @retry="load()"
    />
    <div class="calendar-layout">
      <div class="calendar-month" :aria-busy="loading">
        <div class="calendar-legend" aria-label="账单日期标记">
          <span><i class="date-dot past" />历史账单</span>
          <span><i class="date-dot today" />今日账单</span>
          <span><i class="date-dot future" />未来账单</span>
        </div>
        <table ref="grid" class="month-grid" role="grid" :aria-label="`${monthLabel}账单日历`">
          <thead>
            <tr>
              <th v-for="weekday in weekdays" :key="weekday" scope="col">{{ weekday }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(week, index) in weeks" :key="index">
              <td
                v-for="(day, dayIndex) in week"
                :key="day ?? dayIndex"
                :aria-selected="day === selected"
              >
                <button
                  v-if="day"
                  type="button"
                  class="calendar-day"
                  :class="{
                    'outside-month': !day.startsWith(month),
                    'is-today': day === today,
                    'is-selected': day === selected,
                    'has-bills': days.has(day),
                    [`tone-${timing(day)}`]: days.has(day),
                  }"
                  :data-date="day"
                  :aria-label="cellLabel(day)"
                  :aria-current="day === today ? 'date' : undefined"
                  :tabindex="day === selected ? 0 : -1"
                  :disabled="disabled"
                  @click="selectDay(day)"
                  @keydown="onDayKey($event, day)"
                >
                  <span class="day-number">{{ Number(day.slice(8)) }}</span>
                  <span v-if="days.has(day)" class="day-count"
                    ><i class="date-dot" :class="timing(day)" />{{ days.get(day)!.count
                    }}<span class="count-unit"> 笔</span></span
                  >
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <section class="day-panel" :aria-label="`${selectedLabel}账单`" :aria-busy="loading">
        <div class="day-panel-heading">
          <div>
            <h3>{{ selectedLabel }}</h3>
            <span class="day-status" :class="timing(selected)">{{ timingLabel(selected) }}</span>
          </div>
          <p v-if="current" aria-live="polite">
            {{ selectedDay?.count ?? 0 }} 笔账单<strong>{{
              money(selectedDay?.amount ?? '0.00')
            }}</strong>
          </p>
        </div>
        <LoadingBlock v-if="loading && !current" />
        <ul v-else-if="selectedDay?.bills.length" class="day-bills">
          <li v-for="bill in selectedDay.bills" :key="bill.plan_id">
            <button
              type="button"
              class="day-bill"
              :disabled="disabled || loading || !!error"
              :aria-label="`${bill.plan_name}，${money(bill.amount)}，${bill.is_estimated ? '预计账单，查看规则' : '查看账单详情'}`"
              @click="openEntry(bill, $event)"
            >
              <span class="bill-info"
                ><strong>{{ bill.plan_name }}</strong
                ><span
                  >{{ formatCycle(bill.cycle_type, null, bill.cycle_interval)
                  }}<span v-if="bill.plan_status !== 'enabled'">
                    · {{ bill.plan_status === 'deleted' ? '规则已删除' : '规则已停用' }}</span
                  ></span
                ></span
              >
              <span class="bill-value"
                ><strong class="tabular-nums">{{ money(bill.amount) }}</strong
                ><span :class="{ 'estimate-tag': bill.is_estimated }">{{
                  bill.is_estimated ? '预计 · 查看规则' : '查看详情'
                }}</span></span
              >
            </button>
          </li>
        </ul>
        <div v-else-if="!error && !loading" class="day-empty">
          <NavIcon name="calendar" />
          <p>这一天没有有效账单</p>
          <span>选择有标记的日期查看明细</span>
        </div>
      </section>
    </div>
  </el-card>
</template>

<style scoped>
.calendar-heading,
.calendar-title,
.month-navigation {
  display: flex;
  align-items: center;
}
.calendar-heading {
  justify-content: space-between;
  gap: 20px;
  flex-wrap: wrap;
  margin-bottom: 22px;
}
.calendar-title {
  gap: 12px;
  min-width: 0;
}
.calendar-icon {
  color: var(--sl-primary);
  background: var(--sl-primary-soft);
  padding: 10px;
  border-radius: var(--sl-radius-sm);
}
h2,
h3,
p {
  margin: 0;
}
h2 {
  font-size: 17px;
  font-weight: 600;
}
.calendar-caption {
  margin-top: 5px;
  color: var(--sl-text-muted);
  font-size: 12px;
}
.month-navigation {
  gap: 8px;
}
.month-navigation .el-button + .el-button {
  margin-left: 0;
}
.month-label {
  display: inline-flex;
  justify-content: center;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  min-width: 140px;
  white-space: nowrap;
}
.current-month {
  background: var(--sl-primary-soft);
  color: var(--sl-primary-text);
  padding: 2px 6px;
  border-radius: 5px;
  font-size: 11px;
  font-weight: 500;
}
.month-arrow {
  padding: 8px;
}
.next-month :deep(svg) {
  transform: rotate(180deg);
}
.calendar-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) minmax(260px, 1fr);
  gap: 28px;
}
.calendar-month {
  min-width: 0;
}
.calendar-legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 18px;
  margin-bottom: 14px;
  color: var(--sl-text-secondary);
  font-size: 12px;
}
.calendar-legend > span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.date-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  flex-shrink: 0;
  border-radius: 50%;
}
.date-dot.past {
  background: #64748b;
}
.date-dot.today {
  background: #b45309;
}
.date-dot.future {
  background: var(--sl-primary);
}
.month-grid {
  width: 100%;
  border-collapse: separate;
  border-spacing: 4px;
  table-layout: fixed;
}
.month-grid th {
  color: var(--sl-text-muted);
  font-weight: 500;
  font-size: 12px;
  height: 30px;
}
.month-grid td {
  padding: 0;
  vertical-align: top;
}
.calendar-day {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  width: 100%;
  height: 63px;
  padding: 5px 2px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 8px;
  color: var(--sl-text);
  cursor: pointer;
  font: inherit;
}
.calendar-day:hover {
  background: var(--sl-surface-muted);
}
.calendar-day.outside-month {
  color: var(--sl-text-muted);
  opacity: 0.45;
}
.calendar-day.tone-past {
  background: #f1f5f9;
}
.calendar-day.tone-today {
  background: #fff7ed;
}
.calendar-day.tone-future {
  background: var(--sl-primary-soft);
}
.calendar-day.is-selected {
  border-color: var(--sl-primary);
  box-shadow: inset 0 0 0 1px var(--sl-primary);
}
.calendar-day:disabled {
  cursor: default;
}
.day-number {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 26px;
  width: 26px;
  border-radius: 50%;
  font-size: 13px;
}
.is-today .day-number {
  background: var(--sl-primary);
  color: white;
  font-weight: 600;
}
.day-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 3px;
  font-size: 10px;
  white-space: nowrap;
  color: var(--sl-text-secondary);
  max-width: 100%;
}
.day-panel {
  border-left: 1px solid var(--sl-border);
  padding-left: 28px;
  min-width: 0;
}
.day-panel-heading {
  padding: 2px 0 16px;
  border-bottom: 1px solid var(--sl-border);
}
.day-panel-heading > div {
  display: flex;
  align-items: center;
  gap: 10px;
}
h3 {
  font-size: 17px;
  font-weight: 600;
}
.day-status {
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 5px;
}
.day-status.past {
  color: #475569;
  background: #f1f5f9;
}
.day-status.today {
  color: #9a3412;
  background: #fff7ed;
}
.day-status.future {
  color: var(--sl-primary-text);
  background: var(--sl-primary-soft);
}
.day-panel-heading p {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  color: var(--sl-text-muted);
  font-size: 12px;
  margin-top: 12px;
}
.day-panel-heading p strong {
  color: var(--sl-text);
  font-size: 16px;
  overflow-wrap: anywhere;
}
.day-bills {
  margin: 0;
  padding: 0;
  list-style: none;
  max-height: 365px;
  overflow-y: auto;
}
.day-bills li + li {
  border-top: 1px solid var(--sl-border);
}
.day-bill {
  width: 100%;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  border: 0;
  text-align: left;
  background: transparent;
  padding: 15px 2px;
  color: inherit;
  font: inherit;
  cursor: pointer;
}
.day-bill:hover {
  background: var(--sl-surface-muted);
}
.day-bill:disabled {
  cursor: default;
}
.bill-info {
  min-width: 0;
  flex: 1;
}
.bill-info strong {
  display: block;
  overflow-wrap: anywhere;
  font-size: 13px;
  font-weight: 500;
}
.bill-info > span {
  display: block;
  color: var(--sl-text-muted);
  font-size: 11px;
  margin-top: 6px;
}
.bill-value {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  flex-shrink: 0;
  gap: 6px;
}
.bill-value strong {
  font-size: 13px;
  font-weight: 600;
}
.bill-value > span {
  color: var(--sl-text-muted);
  font-size: 11px;
}
.bill-value .estimate-tag {
  color: var(--sl-primary-text);
}
.day-empty {
  padding: 72px 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  color: var(--sl-text-muted);
  text-align: center;
}
.day-empty :deep(svg) {
  width: 30px;
  height: 30px;
  opacity: 0.5;
  margin-bottom: 12px;
}
.day-empty p {
  font-size: 13px;
}
.day-empty > span {
  font-size: 12px;
  margin-top: 6px;
}
@media (max-width: 1000px) {
  .calendar-layout {
    grid-template-columns: minmax(0, 1fr);
    gap: 20px;
  }
  .day-panel {
    padding: 0;
    border-left: 0;
    border-top: 1px solid var(--sl-border);
    padding-top: 20px;
  }
  .day-empty {
    padding: 28px 0;
  }
}
@media (max-width: 500px) {
  .calendar-heading {
    gap: 16px;
  }
  .calendar-title {
    align-items: flex-start;
  }
  .month-navigation {
    width: 100%;
    gap: 4px;
  }
  .month-label {
    min-width: 0;
    flex: 1;
    gap: 4px;
    font-size: 13px;
  }
  .month-arrow {
    padding: 6px;
  }
  .today-button {
    padding: 8px;
    font-size: 12px;
  }
  .current-month {
    font-size: 10px;
    padding: 2px 4px;
  }
  .calendar-legend {
    gap: 12px;
    margin-bottom: 8px;
  }
  .month-grid {
    border-spacing: 2px;
  }
  .calendar-day {
    height: 59px;
    border-radius: 6px;
  }
  .count-unit {
    display: none;
  }
}
</style>
