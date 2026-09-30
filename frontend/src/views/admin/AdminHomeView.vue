<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getHealth } from '@/api/users'
import { getAdminSummary } from '@/api/users'
import { ApiError, type AdminSummary, type HealthResponse } from '@/types/api'
import PageHeader from '@/components/common/PageHeader.vue'
import LoadingBlock from '@/components/common/LoadingBlock.vue'

const summary = ref<AdminSummary | null>(null)
const health = ref<HealthResponse | null>(null)
const loading = ref(true)
const error = ref('')
const healthError = ref('')
async function load() {
  loading.value = true
  error.value = ''
  healthError.value = ''
  try {
    summary.value = await getAdminSummary()
  } catch (cause) {
    error.value = cause instanceof ApiError ? cause.message : '无法加载账户统计'
  }
  try {
    health.value = await getHealth()
  } catch (cause) {
    health.value = null
    healthError.value = cause instanceof ApiError ? cause.message : '无法获取系统健康状态'
  } finally {
    loading.value = false
  }
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
        ><el-card
          ><div class="label">剩余可创建</div>
          <strong>{{ summary.remaining_users }}</strong
          ><span>上限 {{ summary.max_users }}</span></el-card
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
          <div
            ><span>应用</span
            ><el-tag :type="health?.application === 'ok' ? 'success' : 'info'">{{
              health?.application === 'ok' ? '正常' : '未能获取'
            }}</el-tag></div
          >
          <div>
            <span>数据库</span
            ><el-tag
              :type="health == null ? 'info' : health.database === 'ok' ? 'success' : 'danger'"
              >{{
              health == null ? '未能获取' : health.database === 'ok' ? '正常' : '异常'
            }}</el-tag>
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
            ><el-tag :type="health == null ? 'info' : health.status === 'ok' ? 'success' : 'danger'">{{
              health == null ? '未能获取' : health.status === 'ok' ? '正常' : '降级'
            }}</el-tag>
          </div>
        </div></el-card
      ></template
    >
  </div>
</template>

<style scoped>
.card-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
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
