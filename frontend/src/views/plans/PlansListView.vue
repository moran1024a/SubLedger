<script setup lang="ts">
import { asApiError } from '@/utils/apiErrors'
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { deletePlan, disablePlan, enablePlan, listPlans } from '@/api/plans'
import { ApiError, type BillPlan, type CycleType } from '@/types/api'
import PageHeader from '@/components/common/PageHeader.vue'
import LoadingBlock from '@/components/common/LoadingBlock.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import MoneyText from '@/components/common/MoneyText.vue'
import { formatCycle, formatDate, formatDateTime } from '@/utils/format'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const plans = ref<BillPlan[]>([])
const loading = ref(true)
const error = ref<ApiError | null>(null)
const search = ref('')
const cycle = ref<CycleType | ''>('')
const status = ref<'' | 'enabled' | 'disabled'>('')
const actionId = ref<number | null>(null)
const actionType = ref<'toggle' | 'delete' | null>(null)
const filtered = computed(() =>
  plans.value.filter(
    (plan) =>
      (!search.value || plan.name.toLowerCase().includes(search.value.toLowerCase())) &&
      (!cycle.value || plan.cycle_type === cycle.value) &&
      (!status.value || (status.value === 'enabled' ? plan.is_enabled : !plan.is_enabled)),
  ),
)
async function load() {
  loading.value = true
  error.value = null
  try {
    plans.value = await listPlans()
  } catch (cause) {
    error.value = asApiError(cause, '无法连接服务器，请检查网络或服务状态。')
  } finally {
    loading.value = false
  }
}
function resetFilters() {
  search.value = ''
  cycle.value = ''
  status.value = ''
}
async function toggle(plan: BillPlan) {
  if (actionId.value !== null) return
  actionId.value = plan.id
  actionType.value = 'toggle'
  const wasEnabled = plan.is_enabled
  try {
    if (wasEnabled)
      await ElMessageBox.confirm(
        '停用后将不再生成新账单，当前未过账单将失效，不再参与月均和日均统计，也不再发送提醒。历史账单会保留。',
        '确认停用账单规则',
        { type: 'warning', confirmButtonText: '停用', cancelButtonText: '取消' },
      )
    if (wasEnabled) await disablePlan(plan.id)
    else await enablePlan(plan.id)
    ElMessage.success(wasEnabled ? '账单规则已停用' : '账单规则已启用')
    await load()
  } catch (cause) {
    if (cause !== 'cancel' && cause !== 'close')
      ElMessage.error(cause instanceof ApiError ? cause.message : '操作失败')
  } finally {
    actionId.value = null
    actionType.value = null
  }
}
async function remove(plan: BillPlan) {
  if (actionId.value !== null) return
  actionId.value = plan.id
  actionType.value = 'delete'
  try {
    await ElMessageBox.confirm(
      '删除后无法恢复。按账户时区，今天以前的已过账单会保留，今天及未来账单会同步删除且不再发送提醒。',
      '确认删除账单规则',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
    await deletePlan(plan.id)
    ElMessage.success('账单规则已删除')
    await load()
  } catch (cause) {
    if (cause instanceof ApiError && cause.code === 'BILL_PLAN_NOT_FOUND') {
      ElMessage.success('账单规则已不存在')
      await load()
    } else if (cause !== 'cancel' && cause !== 'close') {
      ElMessage.error(cause instanceof ApiError ? cause.message : '删除失败')
    }
  } finally {
    actionId.value = null
    actionType.value = null
  }
}
onMounted(load)
</script>

<template>
  <div class="page-container">
    <PageHeader title="账单规则" description="管理单次和周期账单规则"
      ><template #actions
        ><el-button type="primary" @click="$router.push('/plans/new')"
          >新建账单</el-button
        ></template
      ></PageHeader
    ><el-card class="content-card"
      ><div class="filters">
        <el-input
          v-model="search"
          clearable
          placeholder="搜索名称"
          style="max-width: 240px"
        /><el-select v-model="cycle" clearable placeholder="周期" style="width: 150px"
          ><el-option label="单次" value="once" /><el-option
            label="每月"
            value="monthly" /><el-option label="每季度" value="quarterly" /><el-option
            label="每年"
            value="yearly" /><el-option label="自定义天数" value="custom_days" /></el-select
        ><el-select v-model="status" clearable placeholder="状态" style="width: 140px"
          ><el-option label="启用" value="enabled" /><el-option
            label="停用"
            value="disabled" /></el-select
        ><el-button @click="resetFilters">重置</el-button>
      </div>
      <LoadingBlock v-if="loading" /><ErrorState
        v-else-if="error"
        :message="error.message"
        :request-id="error.requestId"
        @retry="load"
      /><EmptyState
        v-else-if="!plans.length"
        title="暂无账单规则"
        description="创建第一条账单规则开始记录订阅"
      /><EmptyState
        v-else-if="!filtered.length"
        title="没有匹配的账单规则"
        description="请调整筛选条件"
      /><el-table v-else :data="filtered" stripe
        ><el-table-column prop="name" label="名称" min-width="160" /><el-table-column
          label="金额"
          width="130"
          ><template #default="{ row }"
            ><MoneyText
              :value="row.amount"
              :currency="auth.user?.currency_code" /></template></el-table-column
        ><el-table-column label="周期" width="130"
          ><template #default="{ row }">{{
            formatCycle(row.cycle_type, row.cycle_days)
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
            formatDateTime(row.updated_at)
          }}</template></el-table-column
        ><el-table-column label="操作" fixed="right" width="230"
          ><template #default="{ row }"
            ><el-button
              link
              type="primary"
              :disabled="actionId !== null"
              @click="$router.push(`/plans/${row.id}`)"
              >查看</el-button
            ><el-button
              link
              :type="row.is_enabled ? 'danger' : 'success'"
              :loading="actionId === row.id && actionType === 'toggle'"
              :disabled="actionId !== null"
              @click="toggle(row)"
              >{{ row.is_enabled ? '停用' : '启用' }}</el-button
            ><el-button
              link
              type="danger"
              :loading="actionId === row.id && actionType === 'delete'"
              :disabled="actionId !== null"
              @click="remove(row)"
              >删除</el-button
            ></template
          ></el-table-column
        ></el-table
      ></el-card
    >
  </div>
</template>

<style scoped>
.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 18px;
}
.content-card {
  overflow: hidden;
}
</style>
