<script setup lang="ts">
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/card/style/css'
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/option/style/css'
import 'element-plus/es/components/select/style/css'

import { ElButton, ElCard, ElOption, ElSelect } from 'element-plus'
import { useQueryRequest } from '@/composables/useQueryRequest'
import { useLogFiles } from '@/composables/useLogFiles'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { downloadUserLog, getUserLogs } from '@/api/logs'
import { getUser, listUsers } from '@/api/users'
import { ApiError, type CurrentUser } from '@/types/api'
import PageHeader from '@/components/common/PageHeader.vue'
import LogFileTable from '@/components/logs/LogFileTable.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import LoadingBlock from '@/components/common/LoadingBlock.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import { useAuthStore } from '@/stores/auth'
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const users = ref<CurrentUser[]>([])
const selectedId = ref<number | undefined>()
// Kept apart from the search results so a remote search cannot rename the open log card.
const selectedUser = ref<CurrentUser | null>(null)
const hasSelection = computed(() => typeof selectedId.value === 'number')
const options = computed(() =>
  selectedUser.value && !users.value.some((user) => user.id === selectedUser.value!.id)
    ? [selectedUser.value, ...users.value]
    : users.value,
)
const userLabel = (user: CurrentUser) => (user.role === 'admin' ? '管理员（自己）' : user.username)
const {
  files,
  loading,
  error,
  downloading,
  load: loadLogs,
  downloadFile,
} = useLogFiles(
  (signal) => (typeof selectedId.value === 'number' ? getUserLogs(selectedId.value, signal) : []),
  (filename, signal) => downloadUserLog(selectedId.value!, filename, signal),
)
const userQueries = useQueryRequest()
let userSearchSequence = 0
async function loadUsers(q = '') {
  const signal = userQueries.next()
  const sequence = ++userSearchSequence
  try {
    const result = await listUsers({ q, page_size: 100 }, signal)
    if (signal.aborted || sequence !== userSearchSequence) return
    users.value = result.items
  } catch (cause) {
    if (signal.aborted || sequence !== userSearchSequence) return
    ElMessage.error(cause instanceof ApiError ? cause.message : '加载用户失败')
  }
}
watch(
  selectedId,
  (value) => {
    selectedUser.value =
      typeof value === 'number' ? (options.value.find((user) => user.id === value) ?? null) : null
    void loadLogs()
    void router.replace({ query: typeof value === 'number' ? { user_id: String(value) } : {} })
  },
  { flush: 'sync' },
)
const linkedQueries = useQueryRequest()
onMounted(async () => {
  const signal = linkedQueries.next()
  await loadUsers()
  if (signal.aborted) return
  const raw = route.query.user_id
  const queryId = typeof raw === 'string' && /^\d+$/.test(raw) ? Number(raw) : NaN
  if (Number.isSafeInteger(queryId)) {
    try {
      const target =
        users.value.find((user) => user.id === queryId) ?? (await getUser(queryId, signal))
      if (signal.aborted) return
      if (!users.value.some((user) => user.id === queryId)) users.value.push(target)
      selectedId.value = queryId
    } catch {
      if (!signal.aborted) ElMessage.error('指定用户不存在或无法加载')
    }
  }
})
</script>
<template>
  <div class="page-container">
    <PageHeader title="用户日志" description="选择账户，查看或下载该账户的日志"
      ><template #actions
        ><el-button
          :loading="loading"
          :disabled="!hasSelection || downloading !== null"
          @click="loadLogs"
          >刷新</el-button
        ><el-button
          type="primary"
          :disabled="loading || error !== null || !files.length || downloading !== null"
          :loading="downloading === 'all'"
          @click="downloadFile()"
          >下载全部</el-button
        ></template
      ></PageHeader
    >
    <div class="filter-bar user-log-filter">
      <label for="log-user-select">用户</label>
      <el-select
        id="log-user-select"
        v-model="selectedId"
        filterable
        remote
        :remote-method="loadUsers"
        clearable
        placeholder="选择用户"
        aria-label="选择日志用户"
        class="user-select"
        ><el-option
          v-for="user in options"
          :key="user.id"
          :label="userLabel(user)"
          :value="user.id"
      /></el-select>
    </div>
    <LoadingBlock v-if="loading" label="正在读取用户日志" /><ErrorState
      v-else-if="error"
      :message="error.message"
      :request-id="error.requestId"
      @retry="loadLogs"
    /><EmptyState
      v-else-if="!hasSelection"
      title="请选择用户"
      description="选择账户后，将显示该账户的日志文件。"
    /><EmptyState
      v-else-if="!files.length"
      title="暂无日志文件"
      description="该账户尚未生成日志文件。"
    /><el-card v-else class="content-card"
      ><template #header
        ><span
          >{{ selectedUser ? userLabel(selectedUser) : '用户' }}的日志
          <span class="text-muted tabular-nums">（{{ files.length }}）</span></span
        ></template
      ><LogFileTable
        :files="files"
        :downloading="downloading"
        :timezone="auth.user?.timezone"
        @download="downloadFile"
    /></el-card>
  </div>
</template>

<style scoped>
.user-log-filter label {
  font-weight: 500;
}
.user-select {
  width: 280px;
}
@media (max-width: 700px) {
  .user-select {
    width: 100%;
  }
}
</style>
