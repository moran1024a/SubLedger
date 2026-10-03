<script setup lang="ts">
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/card/style/css'
import 'element-plus/es/components/input/style/css'
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import 'element-plus/es/components/option/style/css'
import 'element-plus/es/components/select/style/css'
import 'element-plus/es/components/table/style/css'
import 'element-plus/es/components/table-column/style/css'

import {
  ElDropdown,
  ElDropdownMenu,
  ElDropdownItem,
  ElButton,
  ElCard,
  ElInput,
  ElOption,
  ElSelect,
  ElTable,
  ElTableColumn,
} from 'element-plus'
import { useQueryRequest } from '@/composables/useQueryRequest'
import { asApiError, isUncertainWrite, writeErrorMessage } from '@/utils/apiErrors'
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { deletePlan, disablePlan, enablePlan, listPlans } from '@/api/plans'
import { ApiError, type BillPlan, type CycleType } from '@/types/api'
import PageHeader from '@/components/common/PageHeader.vue'
import LoadingBlock from '@/components/common/LoadingBlock.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import MoneyText from '@/components/common/MoneyText.vue'
import { cycleParts, formatCycle, formatDate, formatDateTime } from '@/utils/format'
import { useAuthStore } from '@/stores/auth'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import { rememberPosition, restorePosition } from '@/utils/navigation'
import OperationFeedback from '@/components/common/OperationFeedback.vue'
import { useViewScope } from '@/composables/useViewScope'
import 'element-plus/es/components/dropdown/style/css'
import 'element-plus/es/components/dropdown-menu/style/css'
import 'element-plus/es/components/dropdown-item/style/css'

const auth = useAuthStore(),
  route = useRoute(),
  router = useRouter()
const operationMessage = ref(''),
  hasLoaded = ref(false)
onBeforeRouteLeave(() => {
  rememberPosition(route.fullPath)
})
const plans = ref<BillPlan[]>([])
const loading = ref(true)
const error = ref<ApiError | null>(null)
const search = ref('')
const cycle = ref<CycleType | ''>('')
const status = ref<'' | 'enabled' | 'disabled'>('')
const actionId = ref<number | null>(null)
const uncertain = ref(false)
const scope = useViewScope(() => route.fullPath)
watch(
  () => route.fullPath,
  () => {
    operationMessage.value = ''
    uncertain.value = false
    actionId.value = null
  },
)
const filtered = computed(() =>
  plans.value.filter(
    (plan) =>
      (!search.value || plan.name.toLowerCase().includes(search.value.toLowerCase())) &&
      (!cycle.value ||
        cycleParts(plan.cycle_type, plan.cycle_days, plan.cycle_interval).type === cycle.value) &&
      (!status.value || (status.value === 'enabled' ? plan.is_enabled : !plan.is_enabled)),
  ),
)
function restoreFilters() {
  search.value = typeof route.query.q === 'string' ? route.query.q.slice(0, 128) : ''
  cycle.value = ['once', 'day', 'week', 'month', 'year'].includes(String(route.query.cycle))
    ? (route.query.cycle as CycleType)
    : ''
  status.value = ['enabled', 'disabled'].includes(String(route.query.status))
    ? (route.query.status as 'enabled' | 'disabled')
    : ''
}
watch(() => route.query, restoreFilters, { immediate: true })
watch([search, cycle, status], () => {
  const target = {
    query: {
      ...(search.value ? { q: search.value } : {}),
      ...(cycle.value ? { cycle: cycle.value } : {}),
      ...(status.value ? { status: status.value } : {}),
    },
  }
  if (router.resolve(target).fullPath !== route.fullPath) void router.replace(target)
})
function viewPlan(id: number) {
  if (actionId.value !== null) return
  void router.push({ path: `/plans/${id}`, query: { return_to: route.fullPath } })
}
const queryRequests = useQueryRequest()
async function load() {
  const signal = queryRequests.next()
  loading.value = true
  error.value = null
  try {
    const result = await listPlans(signal)
    if (signal.aborted) return
    plans.value = result
    hasLoaded.value = true
    if (!uncertain.value) operationMessage.value = ''
    else
      operationMessage.value =
        '已重新查询当前规则列表。原操作结果仍待确认，请打开目标规则核对内容和状态。'
    void restorePosition(route.fullPath)
  } catch (cause) {
    if (signal.aborted) return
    error.value = asApiError(cause, '无法连接服务器，请检查网络或服务状态。')
  } finally {
    if (!signal.aborted) loading.value = false
  }
}
function resetFilters() {
  if (actionId.value !== null) return
  search.value = ''
  cycle.value = ''
  status.value = ''
}
async function toggle(plan: BillPlan) {
  if (actionId.value !== null || loading.value) return
  const current = scope.capture()
  const id = plan.id
  actionId.value = plan.id
  const wasEnabled = plan.is_enabled
  try {
    if (wasEnabled)
      await ElMessageBox.confirm(
        `规则「${plan.name}」(#${id})。停用后将不再生成新账单，当前未过账单将失效，不再参与月均和日均统计，也不再发送提醒。历史账单会保留。`,
        '确认停用账单规则',
        { type: 'warning', confirmButtonText: '停用', cancelButtonText: '取消' },
      )
    if (!current() || plans.value.find((row) => row.id === id)?.is_enabled !== wasEnabled) return
    operationMessage.value = ''
    uncertain.value = false
    if (wasEnabled) await disablePlan(id)
    else await enablePlan(id)
    if (!current()) return
    ElMessage.success(wasEnabled ? '账单规则已停用' : '账单规则已启用')
    await load()
  } catch (cause) {
    if (current() && cause !== 'cancel' && cause !== 'close') {
      uncertain.value = isUncertainWrite(cause)
      operationMessage.value = writeErrorMessage(cause)
    }
  } finally {
    if (current()) actionId.value = null
  }
}
async function remove(plan: BillPlan) {
  if (actionId.value !== null || loading.value) return
  const current = scope.capture()
  const id = plan.id
  actionId.value = plan.id
  try {
    await ElMessageBox.confirm(
      `规则「${plan.name}」(#${id})。删除后无法恢复。按账户时区，今天以前的已过账单会保留，今天及未来账单会同步删除且不再发送提醒。`,
      '确认删除账单规则',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
    if (!current() || !plans.value.some((row) => row.id === id)) return
    operationMessage.value = ''
    uncertain.value = false
    await deletePlan(id)
    if (!current()) return
    ElMessage.success('账单规则已删除')
    await load()
  } catch (cause) {
    if (!current()) return
    if (cause instanceof ApiError && cause.code === 'BILL_PLAN_NOT_FOUND') {
      ElMessage.success('账单规则已不存在')
      await load()
    } else if (cause !== 'cancel' && cause !== 'close') {
      uncertain.value = isUncertainWrite(cause)
      operationMessage.value = writeErrorMessage(cause)
    }
  } finally {
    if (current()) actionId.value = null
  }
}
onMounted(load)
</script>

<template>
  <div class="page-container">
    <PageHeader title="账单规则" description="管理单次和周期账单规则"
      ><template #actions
        ><el-button type="primary" :disabled="actionId !== null" @click="$router.push('/plans/new')"
          >新建规则</el-button
        ></template
      ></PageHeader
    ><OperationFeedback
      :message="operationMessage"
      action="重新查询核实"
      :disabled="actionId !== null || loading"
      @check="load"
    /><el-card class="content-card"
      ><div class="filters filter-bar">
        <el-input
          v-model="search"
          :disabled="actionId !== null"
          clearable
          placeholder="搜索名称"
          style="max-width: 240px"
        /><el-select
          v-model="cycle"
          :disabled="actionId !== null"
          clearable
          placeholder="周期"
          style="width: 150px"
          ><el-option label="单次" value="once" /><el-option label="按天" value="day" /><el-option
            label="按周"
            value="week" /><el-option label="按月" value="month" /><el-option
            label="按年"
            value="year" /></el-select
        ><el-select
          v-model="status"
          :disabled="actionId !== null"
          clearable
          placeholder="状态"
          style="width: 140px"
          ><el-option label="启用" value="enabled" /><el-option
            label="停用"
            value="disabled" /></el-select
        ><el-button :disabled="actionId !== null" @click="resetFilters">重置</el-button>
      </div>
      <p class="hint">{{ filtered.length }} 条规则；名称搜索即时生效。</p>
      <LoadingBlock v-if="loading && !hasLoaded" /><ErrorState
        v-if="error"
        :message="hasLoaded ? '刷新失败，以下保留上次结果：' + error.message : error.message"
        :request-id="error.requestId"
        @retry="load"
      /><EmptyState
        v-if="!loading && !error && !plans.length"
        title="暂无账单规则"
        description="创建第一条账单规则开始记录订阅"
      /><EmptyState
        v-if="!loading && !error && plans.length > 0 && !filtered.length"
        title="没有匹配的账单规则"
        description="请调整筛选条件"
      /><el-table v-if="filtered.length" :data="filtered" stripe class="desktop-plans"
        ><el-table-column prop="name" label="名称" min-width="160" /><el-table-column
          label="金额"
          width="150"
          align="right"
          class-name="numeric"
          ><template #default="{ row }"
            ><MoneyText
              :value="row.amount"
              :currency="auth.user?.currency_code" /></template></el-table-column
        ><el-table-column label="周期" width="130"
          ><template #default="{ row }">{{
            formatCycle(row.cycle_type, row.cycle_days, row.cycle_interval)
          }}</template></el-table-column
        ><el-table-column label="首次日期" width="130"
          ><template #default="{ row }">{{
            formatDate(row.first_due_date)
          }}</template></el-table-column
        ><el-table-column label="状态" width="100"
          ><template #default="{ row }"
            ><StatusTag :active="row.is_enabled" /></template></el-table-column
        ><el-table-column label="更新时间" width="180"
          ><template #default="{ row }">{{
            formatDateTime(row.updated_at, auth.user?.timezone)
          }}</template></el-table-column
        ><el-table-column label="操作" fixed="right" width="230"
          ><template #default="{ row }"
            ><el-button link type="primary" :disabled="actionId !== null" @click="viewPlan(row.id)"
              >查看</el-button
            ><el-dropdown trigger="click" :disabled="actionId !== null"
              ><el-button link :disabled="actionId !== null">更多</el-button
              ><template #dropdown
                ><el-dropdown-menu
                  ><el-dropdown-item @click="toggle(row as BillPlan)">{{
                    row.is_enabled ? '停用' : '启用'
                  }}</el-dropdown-item
                  ><el-dropdown-item divided @click="remove(row as BillPlan)"
                    >删除</el-dropdown-item
                  ></el-dropdown-menu
                ></template
              ></el-dropdown
            ></template
          ></el-table-column
        ></el-table
      >
      <div class="mobile-plans">
        <article v-for="plan in filtered" :key="plan.id" class="mobile-plan">
          <div class="record-line">
            <el-button
              link
              type="primary"
              :disabled="actionId !== null"
              @click="viewPlan(plan.id)"
              >{{ plan.name }}</el-button
            ><MoneyText class="numeric" :value="plan.amount" :currency="auth.user?.currency_code" />
          </div>
          <p class="hint">
            {{ formatCycle(plan.cycle_type, plan.cycle_days, plan.cycle_interval) }} ·
            {{ plan.is_enabled ? '启用' : '停用' }}
          </p>
          <div class="record-actions">
            <el-button :disabled="actionId !== null" @click="viewPlan(plan.id)">查看规则</el-button
            ><el-dropdown trigger="click" :disabled="actionId !== null"
              ><el-button :disabled="actionId !== null" :loading="actionId === plan.id"
                >更多</el-button
              ><template #dropdown
                ><el-dropdown-menu
                  ><el-dropdown-item @click="toggle(plan)">{{
                    plan.is_enabled ? '停用' : '启用'
                  }}</el-dropdown-item
                  ><el-dropdown-item divided @click="remove(plan)"
                    >删除</el-dropdown-item
                  ></el-dropdown-menu
                ></template
              ></el-dropdown
            >
          </div>
        </article>
      </div>
      <div v-if="!loading && !error && !filtered.length" class="filters">
        <el-button @click="resetFilters">清除筛选</el-button
        ><el-button @click="router.push('/plans/new')">新建规则</el-button>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.hint {
  color: var(--sl-text-muted);
  font-size: 13px;
}
.mobile-plans {
  display: none;
}
.mobile-plan {
  padding: 16px 0;
  border-bottom: 1px solid var(--sl-border);
}
.record-line {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}
.record-line > .el-button {
  flex: 1;
  min-width: 0;
  white-space: normal;
  text-align: left;
  justify-content: flex-start;
  overflow-wrap: anywhere;
}
.record-line > .numeric {
  flex-shrink: 0;
  text-align: right;
}
.record-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.record-actions .el-button {
  margin-left: 0;
}
.desktop-plans :deep(.cell) {
  overflow-wrap: anywhere;
}
@media (max-width: 700px) {
  .desktop-plans {
    display: none;
  }
  .mobile-plans {
    display: block;
  }
  .filter-bar > :deep(.el-input),
  .filter-bar > :deep(.el-select) {
    max-width: none !important;
    width: 100% !important;
  }
}
.filters:not(.filter-bar) {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sl-space-2);
  margin-bottom: var(--sl-space-4);
}
.content-card {
  overflow: hidden;
}
</style>
