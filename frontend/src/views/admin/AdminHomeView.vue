<script setup lang="ts">
import 'element-plus/es/components/alert/style/css'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/card/style/css'
import 'element-plus/es/components/table/style/css'
import 'element-plus/es/components/table-column/style/css'
import 'element-plus/es/components/tag/style/css'

import { ElAlert, ElButton, ElCard, ElTable, ElTableColumn, ElTag } from 'element-plus'
import { onMounted, ref } from 'vue'
import { useQueryRequest } from '@/composables/useQueryRequest'
import { formatDateTime } from '@/utils/format'
import { getHealth, getRuntime } from '@/api/users'
import { getAdminSummary } from '@/api/users'
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

const summary = ref<AdminSummary | null>(null)
const health = ref<HealthResponse | null>(null)
const loading = ref(true)
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
const dateText = (value: string | null) => (value ? formatDateTime(value) : '—')
const taskResult = (task: RuntimeTask) =>
  task.last_error ||
  (task.counts?.removed != null
    ? `已清理 ${task.counts.removed} 条`
    : task.counts?.sent != null
      ? `成功 ${task.counts.sent}，失败 ${task.counts.failed}，未知 ${task.counts.unknown}`
      : '—')
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
}
onMounted(load)
</script>

<template>
  <div class="page-container">
    <PageHeader title="管理首页" description="查看账户数量和系统健康状态"
      ><template #actions
        ><el-button :loading="loading" @click="load">刷新</el-button></template
      ></PageHeader
    ><LoadingBlock v-if="loading" label="正在读取账户与系统状态" /><template v-else
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
          <el-table-column label="执行结果" min-width="170"
            ><template #default="{ row }">{{
              taskResult(row as RuntimeTask)
            }}</template></el-table-column
          >
        </el-table>
        <ul v-if="runtime.tasks.length" class="task-cards" aria-label="定时任务">
          <li v-for="task in runtime.tasks" :key="task.id" class="task-card">
            <div class="task-card-header">
              <h3>{{ task.name }}</h3>
              <el-tag :type="taskTypes[task.status]">{{ taskLabels[task.status] }}</el-tag>
            </div>
            <dl>
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
              <div class="task-result">
                <dt>执行结果</dt>
                <dd>{{ taskResult(task) }}</dd>
              </div>
            </dl>
          </li>
        </ul>
      </el-card>
    </template>
  </div>
</template>

<style scoped>
.card-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--sl-space-4);
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
.task-cards {
  display: none;
  margin: 0;
  padding: 0;
  list-style: none;
}
.task-card {
  padding: var(--sl-space-4) 0;
  border-top: 1px solid var(--sl-border);
}
.task-card:last-child {
  padding-bottom: 0;
}
.task-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--sl-space-3);
}
.task-card-header h3 {
  margin: 0;
  font-size: var(--sl-font-size);
  min-width: 0;
  overflow-wrap: anywhere;
}
.task-card dl {
  margin: var(--sl-space-3) 0 0;
}
.task-card dl > div {
  display: flex;
  justify-content: space-between;
  gap: var(--sl-space-4);
  margin-top: var(--sl-space-2);
}
.task-card dt {
  color: var(--sl-text-muted);
  flex-shrink: 0;
}
.task-card dd {
  margin: 0;
  min-width: 0;
  text-align: right;
  overflow-wrap: anywhere;
}
.task-card .task-result {
  display: block;
}
.task-result dd {
  margin-top: var(--sl-space-1);
  text-align: left;
}
@media (max-width: 700px) {
  .card-grid,
  .health-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .task-table {
    display: none;
  }
  .task-cards {
    display: block;
  }
}
@media (max-width: 420px) {
  .card-grid,
  .health-grid {
    grid-template-columns: 1fr;
  }
}
</style>
