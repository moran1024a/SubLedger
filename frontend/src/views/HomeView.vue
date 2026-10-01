<script setup lang="ts">
import { asApiError } from '@/utils/apiErrors'
import { onMounted, ref } from 'vue'
import { getSummary } from '@/api/statistics'
import { ApiError, type StatisticsResponse } from '@/types/api'
import { useAuthStore } from '@/stores/auth'
import { formatDate, formatDaysRemaining, formatMoney } from '@/utils/format'
import PageHeader from '@/components/common/PageHeader.vue'
import LoadingBlock from '@/components/common/LoadingBlock.vue'
import ErrorState from '@/components/common/ErrorState.vue'

const auth = useAuthStore()
const data = ref<StatisticsResponse | null>(null)
const loading = ref(true)
const error = ref<ApiError | null>(null)
async function load() {
  loading.value = true
  error.value = null
  try {
    data.value = await getSummary()
  } catch (cause) {
    error.value = asApiError(cause, '无法连接服务器，请检查网络或服务状态。')
  } finally {
    loading.value = false
  }
}
onMounted(load)
const money = (value: string) => formatMoney(value, auth.user?.currency_code)
</script>

<template>
  <div class="page-container">
    <PageHeader title="首页" description="查看近期订阅账单和金额统计"
      ><template #actions
        ><el-button type="primary" @click="$router.push('/plans/new')"
          >新建账单</el-button
        ></template
      ></PageHeader
    >
    <LoadingBlock v-if="loading" /><ErrorState
      v-else-if="error"
      :message="error.message"
      :request-id="error.requestId"
      @retry="load"
    />
    <template v-else-if="data"
      ><div class="card-grid">
        <el-card
          ><div class="metric-label">今日金额</div>
          <strong>{{ money(data.today.amount) }}</strong
          ><span>{{ data.today.count }} 笔</span></el-card
        ><el-card
          ><div class="metric-label">本月金额</div>
          <strong>{{ money(data.current_month.amount) }}</strong
          ><span>{{ data.current_month.count }} 笔</span></el-card
        ><el-card
          ><div class="metric-label">月均金额</div>
          <strong>{{ money(data.averages.monthly) }}</strong></el-card
        ><el-card
          ><div class="metric-label">日均金额</div>
          <strong>{{ money(data.averages.daily) }}</strong></el-card
        ><el-card
          ><div class="metric-label">年度累计</div>
          <strong>{{ money(data.current_year.amount) }}</strong
          ><span>{{ data.current_year.count }} 笔</span></el-card
        >
      </div>
      <el-card class="content-card next-card"
        ><template #header>最近账单</template
        ><template v-if="data.next_bill"
          ><div class="next-content">
            <div>
              <strong>{{ data.next_bill.name }}</strong>
              <p>
                {{ formatDate(data.next_bill.due_date) }} ·
                {{ formatDaysRemaining(data.next_bill.days_remaining) }}
              </p>
            </div>
            <strong>{{ money(data.next_bill.amount) }}</strong>
          </div></template
        ><el-empty v-else description="暂无未过账单"
      /></el-card>
      <div class="quick-grid">
        <router-link to="/plans/new"><el-card shadow="hover">新建账单</el-card></router-link
        ><router-link to="/plans"><el-card shadow="hover">查看账单规则</el-card></router-link
        ><router-link to="/bills"><el-card shadow="hover">查看账单记录</el-card></router-link
        ><router-link to="/settings/notifications"
          ><el-card shadow="hover">配置提醒</el-card></router-link
        >
      </div></template
    >
  </div>
</template>

<style scoped>
.card-grid {
  grid-template-columns: repeat(5, minmax(0, 1fr));
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
  grid-template-columns: repeat(4, 1fr);
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
    grid-template-columns: repeat(2, 1fr);
  }
  .next-content {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
