<script setup lang="ts">
import 'element-plus/es/components/alert/style/css'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/card/style/css'
import 'element-plus/es/components/table/style/css'
import 'element-plus/es/components/table-column/style/css'
import 'element-plus/es/components/tag/style/css'

import { ElAlert, ElButton, ElCard, ElTable, ElTableColumn, ElTag } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useQueryRequest } from '@/composables/useQueryRequest'
import { formatDateTime } from '@/utils/format'
import { getHealth, getRuntime } from '@/api/users'
import { getAdminSummary } from '@/api/users'
import { useAuthStore } from '@/stores/auth'
import {
  ApiError,
  type AdminSummary,
  type HealthResponse,
  type RuntimeResponse,
  type RuntimeTask,
} from '@/types/api'
import PageHeader from '@/components/common/PageHeader.vue'
import LoadingBlock from '@/components/common/LoadingBlock.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import RecordCard from '@/components/common/RecordCard.vue'
import StatusTag from '@/components/common/StatusTag.vue'

const auth = useAuthStore()
const timezoneLabel = computed(() => auth.user?.timezone || '浏览器时区')

const summary = ref<AdminSummary | null>(null)
const health = ref<HealthResponse | null>(null)
const loading = ref(true)
const hasLoaded = ref(false)
const fetchedAt = ref<Date | null>(null)
const error = ref('')
const healthError = ref('')
const runtime = ref<RuntimeResponse | null>(null)
const runtimeError = ref('')
const queries = useQueryRequest()
const taskLabels: Record<RuntimeTask['status'], string> = {
  waiting: '等待首次执行',
  running: '执行中',
  ok: '正常',
  warning: '需关注',
  error: '异常',
  disabled: '未启用',
}
const taskTypes = {
  waiting: 'info',
  running: 'primary',
  ok: 'success',
  warning: 'warning',
  error: 'danger',
  disabled: 'info',
} as const
const dateText = (value: string | null) =>
  value ? formatDateTime(value, auth.user?.timezone) : '—'
const taskResult = (task: RuntimeTask) =>
  task.counts?.removed != null
    ? `已清理 ${task.counts.removed} 条`
    : task.counts?.sent != null
      ? `成功 ${task.counts.sent}，失败 ${task.counts.failed}，未知 ${task.counts.unknown}`
      : '—'
function clockText(value: Date) {
  const options: Intl.DateTimeFormatOptions = {
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }
  try {
    return new Intl.DateTimeFormat('zh-CN', { ...options, timeZone: auth.user?.timezone }).format(
      value,
    )
  } catch (cause) {
    if (!(cause instanceof RangeError)) throw cause
    return new Intl.DateTimeFormat('zh-CN', options).format(value)
  }
}
async function load() {
  const signal = queries.next()
  loading.value = true
  error.value = ''
  healthError.value = ''
  runtimeError.value = ''
  const results = await Promise.allSettled([
    getAdminSummary(signal),
    getHealth(signal),
    getRuntime(signal),
  ])
  if (signal.aborted) return
  fetchedAt.value = new Date()
  const [accountResult, healthResult, runtimeResult] = results
  if (accountResult.status === 'fulfilled') summary.value = accountResult.value
  else {
    summary.value = null
    error.value =
      accountResult.reason instanceof ApiError ? accountResult.reason.message : '无法加载账户统计'
  }
  if (healthResult.status === 'fulfilled') health.value = healthResult.value
  else {
    health.value = null
    healthError.value =
      healthResult.reason instanceof ApiError ? healthResult.reason.message : '无法获取系统健康状态'
  }
  if (runtimeResult.status === 'fulfilled') runtime.value = runtimeResult.value
  else {
    runtime.value = null
    runtimeError.value =
      runtimeResult.reason instanceof ApiError ? runtimeResult.reason.message : '无法获取任务状态'
  }
  loading.value = false
  hasLoaded.value = true
}
onMounted(load)
</script>

<template>
  <div class="page-container">
    <PageHeader
      title="管理首页"
      :description="`查看账户数量和系统健康状态。时间按账户时区 ${timezoneLabel} 显示`"
      ><template #actions
        ><span v-if="fetchedAt" class="fetched-at tabular-nums"
          >数据获取于 {{ clockText(fetchedAt) }}</span
        ><el-button :loading="loading" @click="load">刷新</el-button></template
      ></PageHeader
    ><LoadingBlock v-if="!hasLoaded" label="正在读取账户与系统状态" /><template v-else
      ><el-alert
        v-if="error"
        :title="error"
        type="error"
        :closable="false"
        show-icon
        class="content-card"
      />
      <div v-if="summary" class="card-grid">
        <el-card
          ><div class="label">账户总数</div>
          <strong class="tabular-nums">{{ summary.total_users }}</strong></el-card
        ><el-card
          ><div class="label">启用普通账户</div>
          <strong class="tabular-nums">{{ summary.active_users }}</strong></el-card
        ><el-card
          ><div class="label">停用普通账户</div>
          <strong class="tabular-nums">{{ summary.inactive_users }}</strong></el-card
        >
      </div>
      <el-alert
        v-if="healthError"
        :title="healthError"
        type="error"
        :closable="false"
        show-icon
        class="content-card"
      />
      <el-card class="content-card health-card"
        ><template #header><h2 class="section-title">系统健康状态</h2></template>
        <div class="health-grid">
          <div>
            <span>应用</span
            ><el-tag :type="health?.application === 'ok' ? 'success' : 'info'">{{
              health?.application === 'ok' ? '正常' : '未能获取'
            }}</el-tag>
          </div>
          <div>
            <span>数据库</span
            ><el-tag
              :type="health == null ? 'info' : health.database === 'ok' ? 'success' : 'danger'"
              >{{
                health == null ? '未能获取' : health.database === 'ok' ? '正常' : '异常'
              }}</el-tag
            >
          </div>
          <div>
            <span>调度器</span
            ><el-tag
              :type="
                health == null
                  ? 'info'
                  : health.scheduler === 'ok' || health.scheduler === 'disabled'
                    ? 'success'
                    : 'danger'
              "
              >{{
                health == null
                  ? '未能获取'
                  : health.scheduler === 'disabled'
                    ? '未启用'
                    : health.scheduler === 'ok'
                      ? '运行中'
                      : '异常'
              }}</el-tag
            >
          </div>
          <div>
            <span>整体</span
            ><el-tag
              :type="health == null ? 'info' : health.status === 'ok' ? 'success' : 'danger'"
              >{{ health == null ? '未能获取' : health.status === 'ok' ? '正常' : '降级' }}</el-tag
            >
          </div>
        </div></el-card
      >
      <el-alert
        v-if="runtimeError"
        :title="runtimeError"
        type="error"
        :closable="false"
        class="content-card"
      />
      <el-card v-if="runtime" class="content-card health-card">
        <template #header><h2 class="section-title">定时任务</h2></template>
        <p class="hint">显示本次服务启动后的执行情况。单个通知渠道失败会标记为需关注。</p>
        <EmptyState v-if="!runtime.tasks.length" title="暂无定时任务" compact />
        <el-table v-else :data="runtime.tasks" row-key="id" class="task-table">
          <el-table-column prop="name" label="任务" min-width="120" />
          <el-table-column label="状态" min-width="120"
            ><template #default="{ row }"
              ><el-tag :type="taskTypes[row.status as RuntimeTask['status']]">{{
                taskLabels[row.status as RuntimeTask['status']]
              }}</el-tag></template
            ></el-table-column
          >
          <el-table-column label="最近成功" min-width="170" class-name="tabular-nums"
            ><template #default="{ row }">{{
              dateText(row.last_success_at)
            }}</template></el-table-column
          >
          <el-table-column label="下次执行" min-width="170" class-name="tabular-nums"
            ><template #default="{ row }">{{
              dateText(row.next_run_at)
            }}</template></el-table-column
          >
          <el-table-column label="耗时" min-width="85" align="right" class-name="tabular-nums"
            ><template #default="{ row }">{{
              row.duration_seconds == null ? '—' : `${row.duration_seconds} 秒`
            }}</template></el-table-column
          >
          <el-table-column
            prop="consecutive_failures"
            label="连续失败"
            width="100"
            align="right"
            class-name="tabular-nums"
          />
          <el-table-column label="执行结果" min-width="190"
            ><template #default="{ row }"
              ><span class="task-result-text"
                >{{ taskResult(row as RuntimeTask)
                }}<StatusTag
                  v-if="row.last_error"
                  class="error-tag"
                  active
                  active-text="出错"
                  tone="danger"
                  :title="row.last_error"
                /><small v-if="row.last_error" class="error-class">{{
                  row.last_error
                }}</small></span
              ></template
            ></el-table-column
          >
        </el-table>
        <div v-if="runtime.tasks.length" class="task-cards sl-stagger">
          <RecordCard
            v-for="(task, index) in runtime.tasks"
            :key="task.id"
            :style="{ '--i': Math.min(index, 8) }"
          >
            <template #title
              ><h3>{{ task.name }}</h3></template
            >
            <template #amount
              ><el-tag :type="taskTypes[task.status]">{{
                taskLabels[task.status]
              }}</el-tag></template
            >
            <template #meta
              ><dl>
                <div>
                  <dt>最近成功</dt>
                  <dd class="tabular-nums">{{ dateText(task.last_success_at) }}</dd>
                </div>
                <div>
                  <dt>下次执行</dt>
                  <dd class="tabular-nums">{{ dateText(task.next_run_at) }}</dd>
                </div>
                <div>
                  <dt>耗时</dt>
                  <dd class="tabular-nums">
                    {{ task.duration_seconds == null ? '—' : `${task.duration_seconds} 秒` }}
                  </dd>
                </div>
                <div>
                  <dt>连续失败</dt>
                  <dd class="tabular-nums">{{ task.consecutive_failures }}</dd>
                </div>
                <div>
                  <dt>执行结果</dt>
                  <dd class="task-result-text">
                    {{ taskResult(task)
                    }}<StatusTag
                      v-if="task.last_error"
                      class="error-tag"
                      active
                      active-text="出错"
                      tone="danger"
                      :title="task.last_error"
                    /><small v-if="task.last_error" class="error-class">{{
                      task.last_error
                    }}</small>
                  </dd>
                </div>
              </dl></template
            >
          </RecordCard>
        </div>
      </el-card>
    </template>
  </div>
</template>

<style scoped>
/* Three account metrics; column breakpoints follow the global .card-grid (900px / 480px). */
.card-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-bottom: var(--sl-space-5);
}
.card-grid strong {
  display: block;
  font-size: var(--sl-number-size);
  line-height: 1.3;
  font-weight: 600;
  margin: var(--sl-space-3) 0 var(--sl-space-1);
}
.card-grid span,
.label {
  color: var(--sl-text-muted);
}
.health-card {
  margin-top: var(--sl-space-5);
}
.section-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}
.hint {
  margin: 0 0 var(--sl-space-4);
  color: var(--sl-text-muted);
  overflow-wrap: anywhere;
}
.health-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--sl-space-5);
}
.health-grid > div {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--sl-space-3);
  min-width: 0;
  flex-wrap: wrap;
}
.fetched-at {
  color: var(--sl-text-muted);
  font-size: var(--sl-font-size-sm);
}
.task-result-text {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sl-space-2);
}
.error-tag {
  font-size: var(--sl-font-size-xs);
  cursor: help;
}
.error-class {
  flex-basis: 100%;
  color: var(--sl-danger-text);
  font-size: var(--sl-font-size-xs);
  overflow-wrap: anywhere;
}
.task-cards {
  display: none;
  flex-direction: column;
  gap: var(--sl-space-3);
}
.task-cards h3 {
  margin: 0;
  font-size: var(--sl-font-size);
}
.task-cards dl {
  margin: 0;
}
.task-cards dl > div {
  display: flex;
  justify-content: space-between;
  gap: var(--sl-space-4);
  margin-top: var(--sl-space-1);
}
.task-cards dt {
  flex-shrink: 0;
}
.task-cards dd {
  margin: 0;
  min-width: 0;
  color: var(--sl-text);
  text-align: right;
  overflow-wrap: anywhere;
}
.task-cards dd.task-result-text {
  justify-content: flex-end;
}
@media (max-width: 900px) {
  .card-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 700px) {
  .health-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .task-table {
    display: none;
  }
  .task-cards {
    display: flex;
  }
}
@media (max-width: 480px) {
  .card-grid,
  .health-grid {
    grid-template-columns: 1fr;
  }
}
</style>
