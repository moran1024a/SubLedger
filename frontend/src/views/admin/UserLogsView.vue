<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { downloadUserLog, getUserLogs, saveBlob } from '@/api/logs'
import { listUsers } from '@/api/users'
import { ApiError, type CurrentUser, type LogFile } from '@/types/api'
import PageHeader from '@/components/common/PageHeader.vue'
import LogFileTable from '@/components/logs/LogFileTable.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import LoadingBlock from '@/components/common/LoadingBlock.vue'
import ErrorState from '@/components/common/ErrorState.vue'
const route = useRoute()
const router = useRouter()
const users = ref<CurrentUser[]>([])
const selectedId = ref<number | undefined>()
const files = ref<LogFile[]>([])
const loading = ref(false)
const error = ref<ApiError | null>(null)
const downloading = ref<string | null>(null)
let requestSequence = 0
async function loadUsers() {
  try {
    users.value = (await listUsers()).filter((user) => user.role === 'user')
  } catch (cause) {
    ElMessage.error(cause instanceof ApiError ? cause.message : '加载用户失败')
  }
}
async function loadLogs() {
  const sequence = ++requestSequence
  const userId = selectedId.value
  files.value = []
  error.value = null
  if (!userId) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    const result = await getUserLogs(userId)
    if (sequence !== requestSequence) return
    files.value = result
  } catch (cause) {
    if (sequence !== requestSequence) return
    error.value =
      cause instanceof ApiError
        ? cause
        : new ApiError({
            status: 0,
            code: 'NETWORK',
            message: '无法连接服务器，请检查网络或服务状态。',
          })
  } finally {
    if (sequence === requestSequence) loading.value = false
  }
}
async function downloadFile(filename?: string) {
  if (!selectedId.value || loading.value || error.value || !files.value.length || downloading.value)
    return
  downloading.value = filename ?? 'all'
  try {
    const result = await downloadUserLog(selectedId.value, filename)
    saveBlob(result.blob, result.filename)
  } catch (cause) {
    ElMessage.error(cause instanceof ApiError ? cause.message : '下载失败')
  } finally {
    downloading.value = null
  }
}
watch(
  selectedId,
  (value) => {
    void loadLogs()
    void router.replace({ query: value ? { user_id: String(value) } : {} })
  },
  { flush: 'sync' },
)
onMounted(async () => {
  await loadUsers()
  const queryId = Number(route.query.user_id)
  if (queryId && users.value.some((user) => user.id === queryId)) selectedId.value = queryId
})
</script>
<template>
  <div class="page-container">
    <PageHeader title="用户日志"
      ><template #actions
        ><el-select v-model="selectedId" clearable placeholder="选择用户" style="width: 220px"
          ><el-option
            v-for="user in users"
            :key="user.id"
            :label="user.username"
            :value="user.id" /></el-select
        ><el-button
          :disabled="loading || error !== null || !files.length || downloading !== null"
          :loading="downloading === 'all'"
          @click="downloadFile()"
          >下载全部</el-button
        ></template
      ></PageHeader
    ><LoadingBlock v-if="loading" /><ErrorState
      v-else-if="error"
      :message="error.message"
      :request-id="error.requestId"
      @retry="loadLogs"
    /><EmptyState v-else-if="!selectedId" title="请选择用户" /><EmptyState
      v-else-if="!files.length"
      title="暂无日志文件"
    /><el-card v-else
      ><LogFileTable :files="files" :downloading="downloading" @download="downloadFile"
    /></el-card>
  </div>
</template>
