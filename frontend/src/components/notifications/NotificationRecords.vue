<script setup lang="ts">
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/card/style/css'
import 'element-plus/es/components/date-picker/style/css'
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/option/style/css'
import 'element-plus/es/components/pagination/style/css'
import 'element-plus/es/components/select/style/css'
import 'element-plus/es/components/table/style/css'
import 'element-plus/es/components/table-column/style/css'
import 'element-plus/es/components/tag/style/css'

import {
  ElButton,
  ElCard,
  ElDatePicker,
  ElOption,
  ElPagination,
  ElSelect,
  ElTable,
  ElTableColumn,
  ElTag,
} from 'element-plus'
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listNotificationRecords, type NotificationFilters } from '@/api/notifications'
import { ApiError, type NotificationRecord, type NotificationStatus } from '@/types/api'
import { useQueryRequest } from '@/composables/useQueryRequest'
import { useAuthStore } from '@/stores/auth'
import { asApiError } from '@/utils/apiErrors'
import { formatDateTime } from '@/utils/format'
import LoadingBlock from '@/components/common/LoadingBlock.vue'
import ErrorState from '@/components/common/ErrorState.vue'

const auth = useAuthStore()
const channel = ref<'' | 'email' | 'feishu'>('')
const status = ref<'' | NotificationStatus>('')
const dates = ref<string[] | null>(null)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const records = ref<NotificationRecord[]>([])
const loading = ref(false)
const error = ref<ApiError | null>(null)
const queries = useQueryRequest()
let applied: NotificationFilters = {}
const labels: Record<NotificationStatus, string> = {
  pending: '待处理',
  retry_wait: '等待重试',
  sent: '已发送',
  failed: '失败',
  unknown: '结果未知',
  expired: '已过提醒日期',
}
const dateText = (value: string | null) =>
  value ? formatDateTime(value, auth.user?.timezone) : '—'
async function load() {
  const signal = queries.next()
  loading.value = true
  error.value = null
  try {
    const result = await listNotificationRecords(
      { ...applied, page: page.value, page_size: pageSize.value },
      signal,
    )
    if (signal.aborted) return
    total.value = result.total
    const lastPage = Math.max(1, Math.ceil(result.total / pageSize.value))
    if (page.value > lastPage) {
      page.value = lastPage
      await load()
      return
    }
    records.value = result.items
  } catch (cause) {
    if (!signal.aborted) error.value = asApiError(cause)
  } finally {
    if (!signal.aborted) loading.value = false
  }
}
function query() {
  const [start, end] = dates.value ?? []
  if (start && end && start > end) {
    ElMessage.error('开始日期不能晚于结束日期')
    return
  }
  applied = {
    channel: channel.value || undefined,
    status: status.value || undefined,
    start_date: start,
    end_date: end,
  }
  page.value = 1
  void load()
}
function resize() {
  page.value = 1
  void load()
}
onMounted(load)
</script>

<template>
  <el-card class="content-card">
    <p class="hint">
      按账户时区筛选提醒日期。结果未知表示渠道未确认送达，请先核实是否收到消息。测试发送不计入账单提醒记录。
    </p>
    <div class="filters" @keyup.enter="query">
      <el-select v-model="channel" clearable placeholder="通知渠道" style="width: 140px"
        ><el-option label="邮件" value="email" /><el-option label="飞书" value="feishu"
      /></el-select>
      <el-select v-model="status" clearable placeholder="发送状态" style="width: 160px"
        ><el-option v-for="(label, key) in labels" :key="key" :label="label" :value="key"
      /></el-select>
      <el-date-picker
        v-model="dates"
        type="daterange"
        value-format="YYYY-MM-DD"
        start-placeholder="提醒开始日期"
        end-placeholder="提醒结束日期"
      />
      <el-button type="primary" @click="query">查询</el-button
      ><el-button @click="load">刷新</el-button>
    </div>
    <LoadingBlock v-if="loading" />
    <ErrorState
      v-else-if="error"
      :message="error.message"
      :request-id="error.requestId"
      @retry="load"
    />
    <template v-else>
      <el-table :data="records" row-key="id" empty-text="暂无通知记录">
        <el-table-column prop="plan_name" label="账单规则" min-width="140" />
        <el-table-column prop="due_date" label="账单日期" min-width="115" />
        <el-table-column label="渠道 / 提醒" min-width="125"
          ><template #default="{ row }"
            >{{ row.channel === 'email' ? '邮件' : '飞书' }} /
            {{ row.reminder_type === 'advance' ? '提前' : '当日' }}</template
          ></el-table-column
        >
        <el-table-column label="状态" min-width="120"
          ><template #default="{ row }"
            ><el-tag
              :type="
                row.status === 'sent' ? 'success' : row.status === 'failed' ? 'danger' : 'warning'
              "
              >{{ labels[row.status as NotificationStatus] }}</el-tag
            ></template
          ></el-table-column
        >
        <el-table-column prop="attempt_count" label="尝试次数" width="100" />
        <el-table-column label="计划提醒" min-width="170"
          ><template #default="{ row }">{{ dateText(row.scheduled_at) }}</template></el-table-column
        >
        <el-table-column label="最近尝试" min-width="170"
          ><template #default="{ row }">{{
            dateText(row.last_attempt_at)
          }}</template></el-table-column
        >
        <el-table-column label="发送成功" min-width="170"
          ><template #default="{ row }">{{ dateText(row.sent_at) }}</template></el-table-column
        >
        <el-table-column label="下次重试" min-width="170"
          ><template #default="{ row }">{{
            dateText(row.next_retry_at)
          }}</template></el-table-column
        >
        <el-table-column prop="error_message" label="原因" min-width="220" />
      </el-table>
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :page-sizes="[20, 50, 100]"
        :total="total"
        layout="total, sizes, prev, pager, next"
        @current-change="load"
        @size-change="resize"
      />
    </template>
  </el-card>
</template>

<style scoped>
.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}
.filters :deep(.el-date-editor) {
  max-width: 100%;
  min-width: 0;
}
.hint {
  color: #6b7280;
  font-size: 14px;
}
.el-pagination {
  margin-top: 16px;
  overflow-x: auto;
}
</style>
