<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { downloadMyLog, getMyLogs, saveBlob } from '@/api/logs'
import { ApiError, type LogFile } from '@/types/api'
import PageHeader from '@/components/common/PageHeader.vue'
import LoadingBlock from '@/components/common/LoadingBlock.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import LogFileTable from '@/components/logs/LogFileTable.vue'
const files = ref<LogFile[]>([])
const loading = ref(true)
const error = ref<ApiError | null>(null)
const downloading = ref<string | null>(null)
async function load() {
  loading.value = true
  error.value = null
  try {
    files.value = await getMyLogs()
  } catch (cause) {
    error.value =
      cause instanceof ApiError
        ? cause
        : new ApiError({ status: 0, code: 'NETWORK', message: '加载日志失败' })
  } finally {
    loading.value = false
  }
}
async function downloadFile(filename?: string) {
  if (downloading.value) return
  downloading.value = filename ?? 'all'
  try {
    const result = await downloadMyLog(filename)
    saveBlob(result.blob, result.filename)
    ElMessage.success('日志下载已开始')
  } catch (cause) {
    ElMessage.error(cause instanceof ApiError ? cause.message : '下载失败')
  } finally {
    downloading.value = null
  }
}
onMounted(load)
</script>

<template>
  <div class="page-container">
    <PageHeader title="我的日志"
      ><template #actions
        ><el-button
          :disabled="!files.length || downloading !== null"
          :loading="downloading === 'all'"
          @click="downloadFile()"
          >下载全部</el-button
        ></template
      ></PageHeader
    ><LoadingBlock v-if="loading" /><ErrorState
      v-else-if="error"
      :message="error.message"
      :request-id="error.requestId"
      @retry="load"
    /><EmptyState v-else-if="!files.length" title="暂无日志文件" /><el-card v-else
      ><LogFileTable :files="files" :downloading="downloading" @download="downloadFile"
    /></el-card>
  </div>
</template>
