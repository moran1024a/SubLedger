<script setup lang="ts">
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/card/style/css'
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/option/style/css'
import 'element-plus/es/components/select/style/css'

import { ElButton, ElCard, ElOption, ElSelect } from 'element-plus'
import { useQueryRequest } from '@/composables/useQueryRequest'
import { useLogFiles } from '@/composables/useLogFiles'
import { onMounted, ref, watch } from 'vue'
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
const route = useRoute()
const router = useRouter()
const users = ref<CurrentUser[]>([])
const selectedId = ref<number | undefined>()
const {
  files,
  loading,
  error,
  downloading,
  load: loadLogs,
  downloadFile,
} = useLogFiles(
  (signal) => (selectedId.value ? getUserLogs(selectedId.value, signal) : []),
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
    users.value = result.items.filter((user) => user.role === 'user')
  } catch (cause) {
    if (signal.aborted || sequence !== userSearchSequence) return
    ElMessage.error(cause instanceof ApiError ? cause.message : '加载用户失败')
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
const linkedQueries = useQueryRequest()
onMounted(async () => {
  const signal = linkedQueries.next()
  await loadUsers()
  if (signal.aborted) return
  const queryId = Number(route.query.user_id)
  if (Number.isSafeInteger(queryId) && queryId > 0) {
    try {
      const target =
        users.value.find((user) => user.id === queryId) ?? (await getUser(queryId, signal))
      if (signal.aborted) return
      if (target.role === 'user') {
        if (!users.value.some((user) => user.id === queryId)) users.value.push(target)
        selectedId.value = queryId
      }
    } catch {
      if (!signal.aborted) ElMessage.error('指定用户不存在或无法加载')
    }
  }
})
</script>
<template>
  <div class="page-container">
    <PageHeader title="用户日志"
      ><template #actions
        ><el-select
          v-model="selectedId"
          filterable
          remote
          :remote-method="loadUsers"
          clearable
          placeholder="选择用户"
          style="width: 220px"
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
