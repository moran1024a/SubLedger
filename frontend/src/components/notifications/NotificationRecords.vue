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
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { listNotificationRecords, type NotificationFilters } from '@/api/notifications'
import { ApiError, type NotificationRecord, type NotificationStatus } from '@/types/api'
import { useQueryRequest } from '@/composables/useQueryRequest'
import { useAuthStore } from '@/stores/auth'
import { asApiError } from '@/utils/apiErrors'
import { formatDateTime } from '@/utils/format'
import { isNavigationFailure, useRoute, useRouter } from 'vue-router'
import { notificationLabels as labels, readNotificationQuery } from '@/utils/notificationFilters'
import LoadingBlock from '@/components/common/LoadingBlock.vue'
import ErrorState from '@/components/common/ErrorState.vue'

const auth = useAuthStore(),
  route = useRoute(),
  router = useRouter()
const hasLoaded = ref(false)
let loadedKey = ''
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
const dateText = (value: string | null) =>
  value ? formatDateTime(value, auth.user?.timezone) : '—'
async function load() {
  const signal = queries.next()
  const key = JSON.stringify({ ...applied, page: page.value, page_size: pageSize.value })
  if (key !== loadedKey) {
    records.value = []
    hasLoaded.value = false
  }
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
      await navigate(true)
      return
    }
    records.value = result.items
    loadedKey = key
    hasLoaded.value = true
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
  void navigate()
}
function resize() {
  page.value = 1
  void navigate()
}
async function navigate(replace = false) {
  const query: Record<string, string> = {
    tab: 'records',
    page: String(page.value),
    page_size: String(pageSize.value),
  }
  Object.entries(applied).forEach(([key, value]) => {
    if (value !== undefined && key !== 'page' && key !== 'page_size') query[key] = String(value)
  })
  const sameFilters =
    JSON.stringify(readNotificationQuery(query)) ===
    JSON.stringify(readNotificationQuery(route.query))
  if (router.resolve({ query }).fullPath === route.fullPath) await load()
  else {
    const result = replace ? await router.replace({ query }) : await router.push({ query })
    if (!isNavigationFailure(result) && sameFilters) await load()
  }
}
function reset() {
  channel.value = ''
  status.value = ''
  dates.value = null
  applied = {}
  page.value = 1
  pageSize.value = 20
  void navigate()
}
watch(
  () => JSON.stringify(readNotificationQuery(route.query)),
  () => {
    applied = readNotificationQuery(route.query)
    page.value = applied.page ?? 1
    pageSize.value = applied.page_size ?? 20
    channel.value = applied.channel ?? ''
    status.value = applied.status ?? ''
    dates.value =
      applied.start_date || applied.end_date
        ? [applied.start_date ?? '', applied.end_date ?? '']
        : null
    void load()
  },
  { immediate: true },
)
</script>

<template>
  <el-card class="content-card">
    <p class="hint">
      按账户时区
      {{ auth.user?.timezone || '当前时区' }}
      筛选提醒日期。结果未知表示渠道未确认送达，请先核实是否收到消息。测试发送不计入账单提醒记录。
    </p>
    <div class="filter-bar" @keyup.enter="query">
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
      ><el-button :loading="loading" @click="load">刷新</el-button
      ><el-button @click="reset">重置</el-button>
    </div>
    <LoadingBlock v-if="loading && !hasLoaded" />
    <ErrorState
      v-if="error"
      :message="hasLoaded ? '刷新失败，以下保留上次结果：' + error.message : error.message"
      :request-id="error.requestId"
      @retry="load"
    />
    <template v-if="hasLoaded">
      <el-table class="desktop-records" :data="records" row-key="id" empty-text="暂无通知记录">
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
        <el-table-column label="计划提醒" min-width="170"
          ><template #default="{ row }">{{ dateText(row.scheduled_at) }}</template></el-table-column
        >
        <el-table-column label="更多信息" min-width="200"
          ><template #default="{ row }"
            ><details>
              <summary>查看发送详情</summary>
              <p>尝试 {{ row.attempt_count }} 次</p>
              <p>最近尝试：{{ dateText(row.last_attempt_at) }}</p>
              <p>发送成功：{{ dateText(row.sent_at) }}</p>
              <p>下次重试：{{ dateText(row.next_retry_at) }}</p>
              <p>{{ row.error_message || '无错误信息' }}</p>
            </details></template
          ></el-table-column
        >
      </el-table>
      <div class="mobile-records">
        <article v-for="record in records" :key="record.id">
          <strong>{{ record.plan_name }}</strong>
          <p>{{ record.channel === 'email' ? '邮件' : '飞书' }} · {{ labels[record.status] }}</p>
          <p>
            账单：{{ record.due_date }} ·
            {{ record.reminder_type === 'advance' ? '提前提醒' : '当日提醒' }}
          </p>
          <p>计划提醒：{{ dateText(record.scheduled_at) }}</p>
          <details>
            <summary>查看发送详情</summary>
            <p>尝试 {{ record.attempt_count }} 次</p>
            <p>最近尝试：{{ dateText(record.last_attempt_at) }}</p>
            <p>发送成功：{{ dateText(record.sent_at) }}</p>
            <p>下次重试：{{ dateText(record.next_retry_at) }}</p>
            <p>{{ record.error_message || '无错误信息' }}</p>
          </details>
        </article>
        <p v-if="!records.length">暂无通知记录，可调整筛选条件。</p>
      </div>
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :page-sizes="[20, 50, 100]"
        :total="total"
        layout="total, sizes, prev, pager, next"
        @current-change="navigate()"
        @size-change="resize"
      />
    </template>
  </el-card>
</template>

<style scoped>
summary {
  cursor: pointer;
}
.mobile-records {
  display: none;
}
.mobile-records article {
  padding: 16px 0;
  border-bottom: 1px solid var(--sl-border);
  overflow-wrap: anywhere;
}
.mobile-records p {
  color: var(--sl-text-muted);
  font-size: 13px;
}
@media (max-width: 700px) {
  .desktop-records {
    display: none;
  }
  .mobile-records {
    display: block;
  }
}

.filter-bar :deep(.el-date-editor) {
  max-width: 100%;
  min-width: 0;
}
.hint {
  color: var(--sl-text-muted);
  font-size: 14px;
}
.el-pagination {
  margin-top: 16px;
  overflow-x: auto;
}
</style>
