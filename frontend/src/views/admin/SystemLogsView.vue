<script setup lang="ts">
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/card/style/css'

import { ElButton, ElCard } from 'element-plus'
import { onMounted } from 'vue'
import { downloadSystemLog, getSystemLogs } from '@/api/logs'
import { useLogFiles } from '@/composables/useLogFiles'
import PageHeader from '@/components/common/PageHeader.vue'
import LogFileTable from '@/components/logs/LogFileTable.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import LoadingBlock from '@/components/common/LoadingBlock.vue'
import ErrorState from '@/components/common/ErrorState.vue'
const { files, loading, error, downloading, load, downloadFile } = useLogFiles(
  getSystemLogs,
  downloadSystemLog,
)
onMounted(load)
</script>
<template>
  <div class="page-container">
    <PageHeader title="系统日志"
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
    /><EmptyState v-else-if="!files.length" title="暂无系统日志" /><el-card v-else
      ><LogFileTable :files="files" :downloading="downloading" @download="downloadFile"
    /></el-card>
  </div>
</template>
