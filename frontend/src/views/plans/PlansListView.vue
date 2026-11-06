<script setup lang="ts">
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/card/style/css'
import 'element-plus/es/components/input/style/css'
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import 'element-plus/es/components/option/style/css'
import 'element-plus/es/components/select/style/css'

import {
  ElDropdown,
  ElDropdownMenu,
  ElDropdownItem,
  ElButton,
  ElCard,
  ElInput,
  ElOption,
  ElSelect,
} from 'element-plus'
import { useQueryRequest } from '@/composables/useQueryRequest'
import { asApiError, isUncertainWrite, writeErrorMessage } from '@/utils/apiErrors'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import Draggable from 'vuedraggable'
import { ElMessage, ElMessageBox } from 'element-plus'
import { deletePlan, disablePlan, enablePlan } from '@/api/plans'
import {
  ApiError,
  type BillPlan,
  type BillPlanGroup,
  type CycleType,
  type PlanLayout,
} from '@/types/api'
import {
  getPlanLayout,
  savePlanLayout,
  createPlanGroup,
  renamePlanGroup,
  deletePlanGroup,
} from '@/api/planGroups'
import PageHeader from '@/components/common/PageHeader.vue'
import LoadingBlock from '@/components/common/LoadingBlock.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import MoneyText from '@/components/common/MoneyText.vue'
import NavIcon from '@/components/common/NavIcon.vue'
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
type Group = BillPlanGroup & { plans: BillPlan[] }
const groups = ref<Group[]>([])
const collapsedGroups = ref(new Set<number>())
const version = ref('')
const plans = computed(() => groups.value.flatMap((group) => group.plans))
const saving = ref(false)
const dragging = ref(false)
const layoutStale = ref(false)
const busy = computed(() => saving.value || dragging.value || actionId.value !== null)
const hasFilters = computed(() => !!(search.value || cycle.value || status.value))
const canOrganize = computed(
  () => hasLoaded.value && !loading.value && !error.value && !busy.value && !layoutStale.value,
)
// Do not disable Sortable during its own drag operation.
const dragDisabled = computed(
  () =>
    !hasLoaded.value ||
    loading.value ||
    !!error.value ||
    saving.value ||
    actionId.value !== null ||
    layoutStale.value ||
    hasFilters.value,
)
const canSort = computed(() => canOrganize.value && !hasFilters.value)
const visibleGroups = computed({
  get: () =>
    hasFilters.value
      ? groups.value
          .map((group) => ({ ...group, plans: group.plans.filter(matches) }))
          .filter((group) => group.plans.length)
      : groups.value,
  set: (value: Group[]) => {
    if (!hasFilters.value) groups.value = value
  },
})
function isGroupCollapsed(id: number) {
  // Reveal matching rules during searches without losing the user's folded groups.
  return !hasFilters.value && collapsedGroups.value.has(id)
}
function toggleGroup(id: number) {
  if (busy.value || hasFilters.value) return
  if (collapsedGroups.value.has(id)) collapsedGroups.value.delete(id)
  else collapsedGroups.value.add(id)
}
function applyLayout(layout: PlanLayout) {
  version.value = layout.version
  groups.value = layout.groups.map((group) => ({
    ...group,
    plans: layout.plans.filter(
      (plan) => (plan.group_id ?? null) === (group.is_default ? null : group.id),
    ),
  }))
  collapsedGroups.value = new Set(
    [...collapsedGroups.value].filter((id) => groups.value.some((group) => group.id === id)),
  )
  layoutStale.value = false
}
function orderPayload() {
  return {
    version: version.value,
    groups: groups.value.map((group) => ({
      id: group.id,
      plan_ids: group.plans.map((plan) => plan.id),
    })),
  }
}
function matches(plan: BillPlan) {
  return (
    (!search.value || plan.name.toLowerCase().includes(search.value.toLowerCase())) &&
    (!cycle.value ||
      cycleParts(plan.cycle_type, plan.cycle_days, plan.cycle_interval).type === cycle.value) &&
    (!status.value || (status.value === 'enabled' ? plan.is_enabled : !plan.is_enabled))
  )
}
let previousGroups: Group[] = []
let previousOrder = ''
let dragIsCurrent = () => false
function captureOrder() {
  previousGroups = groups.value.map((group) => ({ ...group, plans: [...group.plans] }))
  previousOrder = JSON.stringify(orderPayload())
}
function startDrag() {
  dragIsCurrent = scope.capture()
  captureOrder()
  dragging.value = true
}
async function endDrag() {
  await nextTick()
  if (!dragIsCurrent()) return
  dragging.value = false
  await persistOrder()
}
async function persistOrder() {
  if (JSON.stringify(orderPayload()) === previousOrder) return
  const current = scope.capture()
  saving.value = true
  operationMessage.value = ''
  try {
    const result = await savePlanLayout(orderPayload())
    if (!current()) return
    applyLayout(result)
    ElMessage.success('分组和顺序已保存')
  } catch (cause) {
    if (!current()) return
    groups.value = previousGroups
    layoutStale.value = true
    operationMessage.value = writeErrorMessage(cause) + ' 请重新查询分组和顺序后再调整。'
  } finally {
    if (current()) saving.value = false
  }
}
async function moveGroup(index: number, delta: number) {
  if (!canSort.value || !groups.value[index + delta]) return
  captureOrder()
  const [group] = groups.value.splice(index, 1)
  groups.value.splice(index + delta, 0, group!)
  await persistOrder()
}
async function movePlan(group: Group, index: number, delta: number) {
  if (!canSort.value || !group.plans[index + delta]) return
  captureOrder()
  const [plan] = group.plans.splice(index, 1)
  group.plans.splice(index + delta, 0, plan!)
  await persistOrder()
}
async function moveToGroup(source: Group, plan: BillPlan, targetId: number) {
  if (!canSort.value || source.id === targetId) return
  const target = groups.value.find((group) => group.id === targetId)
  const index = source.plans.findIndex((row) => row.id === plan.id)
  if (!target || index < 0) return
  captureOrder()
  source.plans.splice(index, 1)
  target.plans.push(plan)
  await persistOrder()
}
async function changeGroup(group?: Group, removeGroup = false) {
  if (!canOrganize.value || group?.is_default) return
  const current = scope.capture()
  saving.value = true
  let submitted = false
  try {
    let result: PlanLayout
    if (removeGroup && group) {
      await ElMessageBox.confirm(
        `删除分组「${group.name}」后，其中 ${group.plans.length} 条规则将移到“未分组”末尾，账单会保留。`,
        '删除分组',
        { type: 'warning', confirmButtonText: '删除分组', cancelButtonText: '取消' },
      )
      if (!current()) return
      submitted = true
      result = await deletePlanGroup(group.id, version.value)
    } else {
      const { value } = await ElMessageBox.prompt(
        '请输入分组名称（最多 64 个字符）',
        group ? '重命名分组' : '新建分组',
        {
          inputValue: group?.name ?? '',
          inputValidator: (value: string) =>
            (!!value?.trim() && [...value.trim()].length <= 64) || '请输入 1 到 64 个字符',
          confirmButtonText: '保存',
          cancelButtonText: '取消',
        },
      )
      if (!current() || (group && value.trim() === group.name)) return
      submitted = true
      result = group
        ? await renamePlanGroup(group.id, value.trim(), version.value)
        : await createPlanGroup(value.trim(), version.value)
    }
    if (!current()) return
    applyLayout(result)
    operationMessage.value = ''
    ElMessage.success(removeGroup ? '分组已删除，规则已移入未分组' : '分组已保存')
  } catch (cause) {
    if (!current() || cause === 'cancel' || cause === 'close') return
    if (
      submitted &&
      (isUncertainWrite(cause) ||
        (cause instanceof ApiError && cause.code === 'BILL_LAYOUT_CHANGED'))
    )
      layoutStale.value = true
    operationMessage.value = writeErrorMessage(cause)
  } finally {
    if (current()) saving.value = false
  }
}
const loading = ref(true)
const error = ref<ApiError | null>(null)
const search = ref('')
const cycle = ref<CycleType | ''>('')
const status = ref<'' | 'enabled' | 'disabled'>('')
const actionId = ref<number | null>(null)
const uncertain = ref(false)
const scope = useViewScope(() => `${auth.sessionVersion}:${route.fullPath}`)
watch(
  () => route.fullPath,
  () => {
    if (saving.value || dragging.value) {
      layoutStale.value = true
      operationMessage.value = '页面已切换，请重新查询核实分组和顺序。'
    } else operationMessage.value = ''
    uncertain.value = false
    actionId.value = null
    saving.value = false
    dragging.value = false
  },
)
const filtered = computed(() => plans.value.filter(matches))
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
  if (busy.value) return
  void router.push({ path: `/plans/${id}`, query: { return_to: route.fullPath } })
}
const queryRequests = useQueryRequest()
async function load() {
  const signal = queryRequests.next()
  loading.value = true
  error.value = null
  try {
    const result = await getPlanLayout(signal)
    if (signal.aborted) return
    applyLayout(result)
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
  if (busy.value) return
  search.value = ''
  cycle.value = ''
  status.value = ''
}
async function toggle(plan: BillPlan) {
  if (busy.value || loading.value) return
  const current = scope.capture()
  const id = plan.id
  actionId.value = plan.id
  const wasEnabled = plan.is_enabled
  try {
    if (wasEnabled)
      await ElMessageBox.confirm(
        `规则「${plan.name}」(#${id})。停用后将不再生成新账单，今日及未来账单将失效，不再计入折算均值。规则会在下一个付款日（单次规则为账单日期）自动移除，并按提醒设置发送周期结束提醒。历史账单会保留。`,
        '确认停用账单规则',
        { type: 'warning', confirmButtonText: '停用', cancelButtonText: '取消' },
      )
    else
      await ElMessageBox.confirm(
        `规则「${plan.name}」(#${id})。启用后会恢复因停用而失效的今日及未来账单，补齐后续账单并恢复提醒。周期规则的自动移除会取消；单次规则仍在账单日期自动移除。手动标记无效的账单不会恢复。`,
        '确认启用账单规则',
        { type: 'info', confirmButtonText: '启用', cancelButtonText: '取消' },
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
  if (busy.value || loading.value) return
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
    <PageHeader title="账单规则" description="管理单次和周期账单规则">
      <template #actions>
        <el-button :disabled="!canOrganize" @click="changeGroup()">新建分组</el-button>
        <el-button type="primary" :disabled="busy" @click="$router.push('/plans/new')"
          >新建规则</el-button
        >
      </template>
    </PageHeader>
    <OperationFeedback
      :message="operationMessage"
      action="重新查询核实"
      :disabled="busy || loading"
      @check="load"
    />
    <el-card class="content-card rules-card">
      <div class="filters filter-bar">
        <el-input
          v-model="search"
          :disabled="busy"
          clearable
          maxlength="128"
          placeholder="搜索名称"
          style="max-width: 240px"
        />
        <el-select
          v-model="cycle"
          :disabled="busy"
          clearable
          placeholder="周期"
          style="width: 150px"
        >
          <el-option label="单次" value="once" /><el-option label="按天" value="day" /><el-option
            label="按周"
            value="week"
          /><el-option label="按月" value="month" /><el-option label="按年" value="year" />
        </el-select>
        <el-select
          v-model="status"
          :disabled="busy"
          clearable
          placeholder="状态"
          style="width: 140px"
        >
          <el-option label="启用" value="enabled" /><el-option label="停用" value="disabled" />
        </el-select>
        <el-button :disabled="busy" @click="resetFilters">重置</el-button>
      </div>
      <div class="list-summary" aria-live="polite">
        <span
          ><strong>{{ filtered.length }}</strong> 条规则</span
        >
        <span class="hint">{{
          saving
            ? '正在保存…'
            : hasFilters
              ? '筛选期间暂停排序，清除筛选后可拖动。'
              : '拖动 ⋮⋮ 排序或跨组移动 · 自动保存'
        }}</span>
      </div>
      <LoadingBlock v-if="loading && !hasLoaded" variant="table" />
      <ErrorState
        v-if="error"
        :message="hasLoaded ? '刷新失败，以下保留上次结果：' + error.message : error.message"
        :request-id="error.requestId"
        @retry="load"
      />
      <EmptyState
        v-if="!loading && !error && hasFilters && !filtered.length"
        title="没有匹配的账单规则"
        description="请调整筛选条件"
      />
      <Draggable
        v-model="visibleGroups"
        item-key="id"
        draggable=".plan-group"
        handle=".group-drag"
        :disabled="dragDisabled"
        :animation="180"
        ghost-class="drag-ghost"
        class="plan-groups"
        @start="startDrag"
        @end="endDrag"
      >
        <template #item="{ element: group, index: groupIndex }">
          <section class="plan-group" :data-group-id="group.id" :aria-label="group.name">
            <div class="group-heading">
              <button
                class="drag-handle group-drag"
                :disabled="dragDisabled"
                :aria-label="`拖动分组 ${group.name}`"
                title="拖动分组"
                type="button"
              >
                ⋮⋮
              </button>
              <h2>
                <button
                  class="group-toggle"
                  type="button"
                  :disabled="busy || hasFilters"
                  :aria-expanded="!isGroupCollapsed(group.id)"
                  :aria-controls="`group-rules-${group.id}`"
                  :aria-label="`${isGroupCollapsed(group.id) ? '展开' : '折叠'}分组 ${group.name}`"
                  :title="hasFilters ? '筛选时自动展开分组' : undefined"
                  @click="toggleGroup(group.id)"
                >
                  <NavIcon name="chevron" />
                  <span>{{ group.name }}</span>
                  <span class="group-count">{{ group.plans.length }}</span>
                </button>
              </h2>
              <el-dropdown trigger="click" :disabled="busy">
                <el-button link :disabled="busy" :aria-label="`管理分组 ${group.name}`"
                  >管理</el-button
                >
                <template #dropdown
                  ><el-dropdown-menu>
                    <el-dropdown-item
                      :disabled="!canSort || groupIndex === 0"
                      @click="moveGroup(groupIndex, -1)"
                      >分组上移</el-dropdown-item
                    >
                    <el-dropdown-item
                      :disabled="!canSort || groupIndex === groups.length - 1"
                      @click="moveGroup(groupIndex, 1)"
                      >分组下移</el-dropdown-item
                    >
                    <el-dropdown-item
                      v-if="!group.is_default"
                      divided
                      :disabled="!canOrganize"
                      @click="changeGroup(group)"
                      >重命名分组</el-dropdown-item
                    >
                    <el-dropdown-item
                      v-if="!group.is_default"
                      :disabled="!canOrganize"
                      @click="
                        changeGroup(
                          groups.find((item) => item.id === group.id),
                          true,
                        )
                      "
                      >删除分组</el-dropdown-item
                    >
                  </el-dropdown-menu></template
                >
              </el-dropdown>
            </div>
            <div :id="`group-rules-${group.id}`" v-show="!isGroupCollapsed(group.id)">
              <div v-if="group.plans.length" class="plan-columns" aria-hidden="true">
                <span></span><span>规则名称</span><span>状态</span><span>账单周期</span>
                <span class="amount-heading">每期金额</span
                ><span class="actions-heading">操作</span>
              </div>
              <Draggable
                v-model="group.plans"
                item-key="id"
                draggable=".plan-row"
                group="billing-rules"
                handle=".rule-drag"
                :disabled="dragDisabled || isGroupCollapsed(group.id)"
                :animation="180"
                :empty-insert-threshold="30"
                ghost-class="drag-ghost"
                class="group-rules"
                @start="startDrag"
                @end="endDrag"
              >
                <template #item="{ element: plan, index: planIndex }">
                  <article
                    class="plan-row"
                    :class="{ 'is-inactive': !plan.is_enabled }"
                    :data-plan-id="plan.id"
                  >
                    <button
                      class="drag-handle rule-drag"
                      :disabled="dragDisabled"
                      :aria-label="`拖动规则 ${plan.name}`"
                      title="拖动规则"
                      type="button"
                    >
                      ⋮⋮
                    </button>
                    <div class="plan-name">
                      <el-button
                        class="plan-title"
                        link
                        type="primary"
                        :disabled="busy"
                        :title="`更新于 ${formatDateTime(plan.updated_at, auth.user?.timezone)}`"
                        @click="viewPlan(plan.id)"
                        ><span>{{ plan.name }}</span>
                        <span class="plan-meta" :class="{ 'ending-date': plan.end_date }">{{
                          plan.end_date
                            ? `${formatDate(plan.end_date)} 到期自动移除`
                            : `首次 ${formatDate(plan.first_due_date)}`
                        }}</span>
                      </el-button>
                    </div>
                    <div class="plan-details">
                      <StatusTag
                        class="plan-status"
                        :class="{ 'is-inactive': !plan.is_enabled }"
                        :active="plan.is_enabled"
                        :tone="plan.is_enabled ? 'success' : 'warning'"
                      />
                      <div class="plan-cycle">
                        <span class="cycle-badge">{{
                          formatCycle(plan.cycle_type, plan.cycle_days, plan.cycle_interval)
                        }}</span>
                      </div>
                    </div>
                    <MoneyText
                      class="plan-amount numeric"
                      :value="plan.amount"
                      :currency="auth.user?.currency_code"
                    />
                    <div class="plan-actions">
                      <el-button
                        class="view-action"
                        link
                        type="primary"
                        :disabled="busy"
                        @click="viewPlan(plan.id)"
                        >查看</el-button
                      >
                      <el-dropdown trigger="click" :disabled="busy"
                        ><el-button
                          link
                          :disabled="busy"
                          :loading="actionId === plan.id"
                          :aria-label="`更多操作 ${plan.name}`"
                          >更多</el-button
                        >
                        <template #dropdown
                          ><el-dropdown-menu>
                            <el-dropdown-item
                              :disabled="!canSort || planIndex === 0"
                              @click="movePlan(group, planIndex, -1)"
                              >规则上移</el-dropdown-item
                            >
                            <el-dropdown-item
                              :disabled="!canSort || planIndex === group.plans.length - 1"
                              @click="movePlan(group, planIndex, 1)"
                              >规则下移</el-dropdown-item
                            >
                            <el-dropdown-item
                              v-for="target in groups.filter((item) => item.id !== group.id)"
                              :key="target.id"
                              :disabled="!canSort"
                              @click="moveToGroup(group, plan, target.id)"
                              >移入 {{ target.name }}</el-dropdown-item
                            >
                            <el-dropdown-item divided @click="toggle(plan)">{{
                              plan.is_enabled ? '停用' : '启用'
                            }}</el-dropdown-item>
                            <el-dropdown-item @click="remove(plan)">删除规则</el-dropdown-item>
                          </el-dropdown-menu></template
                        >
                      </el-dropdown>
                    </div>
                  </article>
                </template>
                <template #footer
                  ><div v-if="!group.plans.length" class="empty-group">
                    暂无规则，可将规则拖到这里，或新建规则时选择此分组。
                  </div></template
                >
              </Draggable>
            </div>
          </section>
        </template>
      </Draggable>
    </el-card>
  </div>
</template>

<style scoped>
.rules-card {
  --plan-columns: 24px minmax(0, 1fr) 80px 140px minmax(115px, 0.5fr) 82px;
  overflow: hidden;
}
.rules-card :deep(.el-card__body) {
  padding: 18px;
}
.hint,
.plan-meta {
  color: var(--sl-text-muted);
  font-size: 12px;
}
.list-summary {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: baseline;
  gap: 4px 16px;
  margin: 12px 0;
  color: var(--sl-text-secondary);
  font-size: 12px;
}
.list-summary strong {
  margin-right: 3px;
  color: var(--sl-text);
  font-size: 14px;
}
.plan-groups {
  display: grid;
  gap: 12px;
}
.plan-group {
  border: 1px solid var(--sl-border);
  border-radius: 8px;
  overflow: hidden;
}
.group-heading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 3px 12px;
  background: var(--sl-primary-soft);
  box-shadow: inset 3px 0 var(--sl-primary);
}
.group-heading h2 {
  flex: 1;
  min-width: 0;
  margin: 0;
  font-size: 14px;
  overflow-wrap: anywhere;
}
.group-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 0;
  border: 0;
  background: transparent;
  color: var(--sl-primary-text);
  font: inherit;
  font-weight: 600;
  text-align: left;
  cursor: pointer;
}
.group-toggle > span {
  min-width: 0;
  overflow-wrap: anywhere;
}
.group-toggle:disabled {
  cursor: default;
}
.group-toggle :deep(svg) {
  width: 14px;
  height: 14px;
  transform: rotate(180deg);
}
.group-toggle[aria-expanded='true'] :deep(svg) {
  transform: rotate(-90deg);
}
.group-count {
  flex-shrink: 0;
  min-width: 22px;
  padding: 0 6px;
  border-radius: 4px;
  background: var(--sl-surface);
  color: var(--sl-primary-text);
  font-size: 12px;
  line-height: 20px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}
.group-heading :deep(.el-button) {
  font-size: 12px;
  color: var(--sl-primary-text);
}
.drag-handle {
  flex: none;
  border: 0;
  background: transparent;
  color: var(--sl-text-muted);
  cursor: grab;
  touch-action: none;
  padding: 8px 3px;
  font-size: 17px;
  line-height: 1;
  border-radius: 4px;
}
.drag-handle:hover:not(:disabled) {
  background: var(--sl-primary-soft);
  color: var(--sl-primary);
}
.drag-handle:active {
  cursor: grabbing;
}
.drag-handle:disabled {
  opacity: 0.35;
  cursor: default;
  touch-action: auto;
}
.drag-handle:focus-visible,
.group-toggle:focus-visible {
  outline: 2px solid var(--sl-primary);
  outline-offset: 1px;
}
.drag-ghost {
  opacity: 0.4;
  background: var(--sl-primary-soft);
}
.group-rules {
  min-height: 52px;
}
.empty-group {
  padding: 16px;
  color: var(--sl-text-muted);
  font-size: 12px;
  pointer-events: none;
}
.plan-columns,
.plan-row {
  display: grid;
  grid-template-columns: var(--plan-columns);
  align-items: center;
  column-gap: 16px;
  padding: 8px 12px;
}
.plan-columns {
  padding-block: 5px;
  border-bottom: 1px solid var(--sl-border);
  background: var(--sl-surface-muted);
  color: var(--sl-text-muted);
  font-size: 12px;
}
.amount-heading {
  text-align: right;
}
.actions-heading {
  text-align: center;
}
.plan-row {
  min-height: 58px;
  background: var(--sl-surface);
}
.plan-row + .plan-row {
  border-top: 1px solid var(--sl-border);
}
.plan-row.is-inactive {
  background: var(--sl-surface-muted);
}
.plan-row:hover {
  background: #f3f7ff;
}
.plan-name {
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
}
.plan-title.el-button {
  max-width: 100%;
  padding: 0;
  color: var(--sl-text);
  font-size: 14px;
  font-weight: 600;
  line-height: 1.4;
  white-space: normal;
  text-align: left;
  justify-content: flex-start;
  overflow-wrap: anywhere;
}
.plan-title.el-button:hover:not(:disabled) {
  color: var(--sl-primary);
}
.plan-title :deep(> span) {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
}
.plan-meta {
  font-weight: 400;
  line-height: 1.4;
}
.ending-date {
  color: var(--sl-warning-text);
}
.plan-details {
  display: contents;
}
.plan-status {
  justify-self: start;
  padding: 2px 8px;
  border-radius: 5px;
  background: var(--sl-success-soft);
  font-size: 12px;
  line-height: 20px;
  white-space: nowrap;
}
.plan-status.is-inactive {
  background: var(--sl-warning-soft);
}
.plan-cycle {
  min-width: 0;
}
.cycle-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 5px;
  background: var(--sl-primary-soft);
  color: var(--sl-primary-text);
  font-size: 12px;
  font-weight: 500;
  line-height: 20px;
  overflow-wrap: anywhere;
}
.plan-amount {
  min-width: 0;
  color: var(--sl-text);
  font-size: 17px;
  font-weight: 650;
  line-height: 1.4;
  text-align: right;
  white-space: normal;
  overflow-wrap: anywhere;
}
.is-inactive .plan-title,
.is-inactive .plan-amount {
  color: var(--sl-text-secondary);
}
.plan-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: flex-end;
}
.plan-actions :deep(.el-button) {
  font-size: 12px;
}
@media (max-width: 1100px) {
  .rules-card {
    --plan-columns: 22px minmax(0, 1fr) 68px 106px 112px 76px;
  }
  .plan-columns,
  .plan-row {
    column-gap: 10px;
  }
}
@media (max-width: 700px) {
  .rules-card :deep(.el-card__body) {
    padding: 12px;
  }
  .group-heading {
    padding-inline: 10px;
  }
  .group-toggle,
  .group-drag {
    min-height: 38px;
  }
  .plan-columns {
    display: none;
  }
  .plan-row {
    grid-template-columns: 22px minmax(0, 1fr) minmax(60px, auto);
    gap: 8px;
    padding: 10px;
  }
  .rule-drag {
    grid-column: 1;
    grid-row: 1 / 3;
    align-self: stretch;
  }
  .plan-name {
    grid-column: 2;
    grid-row: 1;
  }
  .plan-amount {
    grid-column: 3;
    grid-row: 1;
    max-width: 128px;
    font-size: 16px;
    align-self: start;
  }
  .plan-details {
    grid-column: 2;
    grid-row: 2;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
  }
  .plan-status,
  .cycle-badge {
    padding-inline: 6px;
  }
  .plan-actions {
    grid-column: 3;
    grid-row: 2;
  }
  .plan-actions .view-action {
    display: none;
  }
  .plan-actions :deep(.el-button) {
    min-height: 28px;
  }
  .filter-bar {
    gap: 8px;
  }
  .filter-bar > :deep(.el-input) {
    max-width: none !important;
    width: 100% !important;
  }
  .filter-bar > :deep(.el-select) {
    width: calc((100% - 72px) / 2) !important;
    flex: 1;
    min-width: 0;
  }
}
</style>
