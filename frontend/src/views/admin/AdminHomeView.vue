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
const dateText = (value: string | null) => (value ? formatDateTime(value) : '—')
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
    ><LoadingBlock v-if="loading" /><template v-else
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
          <strong>{{ summary.total_users }}</strong></el-card
        ><el-card
          ><div class="label">启用普通账户</div>
          <strong>{{ summary.active_users }}</strong></el-card
        ><el-card
          ><div class="label">停用普通账户</div>
          <strong>{{ summary.inactive_users }}</strong></el-card
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
        ><template #header>系统健康状态</template>
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
        <template #header>定时任务</template>
        <p class="hint">显示本次服务启动后的执行情况。单个通知渠道失败会标记为需关注。</p>
        <el-table :data="runtime.tasks" row-key="id">
          <el-table-column prop="name" label="任务" min-width="120" />
          <el-table-column label="状态" min-width="120"
            ><template #default="{ row }"
              ><el-tag
                :type="
                  row.status === 'error' ? 'danger' : row.status === 'warning' ? 'warning' : 'info'
                "
                >{{ taskLabels[row.status as RuntimeTask['status']] }}</el-tag
              ></template
            ></el-table-column
          >
          <el-table-column label="最近成功" min-width="170"
            ><template #default="{ row }">{{
              dateText(row.last_success_at)
            }}</template></el-table-column
          >
          <el-table-column label="下次执行" min-width="170"
            ><template #default="{ row }">{{
              dateText(row.next_run_at)
            }}</template></el-table-column
          >
          <el-table-column label="耗时" min-width="85"
            ><template #default="{ row }">{{
              row.duration_seconds == null ? '—' : `${row.duration_seconds} 秒`
            }}</template></el-table-column
          >
          <el-table-column prop="consecutive_failures" label="连续失败" width="100" />
          <el-table-column label="执行结果" min-width="170"
            ><template #default="{ row }">{{
              row.last_error ||
              (row.counts?.removed != null
                ? `已清理 ${row.counts.removed} 条`
                : row.counts?.sent != null
                  ? `成功 ${row.counts.sent}，失败 ${row.counts.failed}，未知 ${row.counts.unknown}`
                  : '—')
            }}</template></el-table-column
          >
        </el-table>
      </el-card>
    </template>
  </div>
</template>

<style scoped>
.card-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}
.card-grid strong {
  display: block;
  font-size: 28px;
  margin: 12px 0 4px;
}
.card-grid span,
.label {
  color: #6b7280;
}
.health-card {
  margin-top: 20px;
}
.health-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
}
.health-grid > div {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}
@media (max-width: 700px) {
  .card-grid,
  .health-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
