<script setup lang="ts">
import { onMounted } from 'vue'
import { downloadMyLog, getMyLogs } from '@/api/logs'
import { useLogFiles } from '@/composables/useLogFiles'
import PageHeader from '@/components/common/PageHeader.vue'
import LoadingBlock from '@/components/common/LoadingBlock.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import LogFileTable from '@/components/logs/LogFileTable.vue'
const { files, loading, error, downloading, load, downloadFile } = useLogFiles(
  getMyLogs,
  downloadMyLog,
)
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
