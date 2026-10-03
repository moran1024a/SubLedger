<script setup lang="ts">
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/card/style/css'

import { ElButton, ElCard } from 'element-plus'
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
    <PageHeader title="我的日志" description="按日期查看日志文件，或下载全部日志"
      ><template #actions
        ><el-button
          type="primary"
          :disabled="loading || error !== null || !files.length || downloading !== null"
          :loading="downloading === 'all'"
          @click="downloadFile()"
          >下载全部</el-button
        ></template
      ></PageHeader
    ><LoadingBlock v-if="loading" label="正在读取日志文件" /><ErrorState
      v-else-if="error"
      :message="error.message"
      :request-id="error.requestId"
      @retry="load"
    /><EmptyState
      v-else-if="!files.length"
      title="暂无日志文件"
      description="产生日志后，文件会显示在这里。"
    /><el-card v-else class="content-card"
      ><template #header
        ><span
          >日志文件 <span class="text-muted tabular-nums">（{{ files.length }}）</span></span
        ></template
      ><LogFileTable :files="files" :downloading="downloading" @download="downloadFile"
    /></el-card>
  </div>
</template>
