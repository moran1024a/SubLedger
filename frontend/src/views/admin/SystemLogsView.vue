<script setup lang="ts">
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/card/style/css'

import { ElButton, ElCard } from 'element-plus'
import { onMounted } from 'vue'
import { downloadSystemLog, getSystemLogs } from '@/api/logs'
import { useLogFiles } from '@/composables/useLogFiles'
import PageHeader from '@/components/common/PageHeader.vue'
import LogFileTable from '@/components/logs/LogFileTable.vue'
import { useAuthStore } from '@/stores/auth'
const auth = useAuthStore()
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
    <PageHeader title="系统日志" description="查看系统日志文件和最近修改时间"
      ><template #actions
        ><el-button :loading="loading" :disabled="downloading !== null" @click="load"
          >刷新</el-button
        ><el-button
          type="primary"
          :disabled="loading || error !== null || !files.length || downloading !== null"
          :loading="downloading === 'all'"
          @click="downloadFile()"
          >下载全部</el-button
        ></template
      ></PageHeader
    ><LoadingBlock v-if="loading" label="正在读取系统日志" /><ErrorState
      v-else-if="error"
      :message="error.message"
      :request-id="error.requestId"
      @retry="load"
    /><EmptyState
      v-else-if="!files.length"
      title="暂无系统日志"
      description="产生日志后，文件会显示在这里。"
    /><el-card v-else class="content-card"
      ><template #header
        ><span
          >日志文件 <span class="text-muted tabular-nums">（{{ files.length }}）</span></span
        ></template
      ><LogFileTable
        :files="files"
        :downloading="downloading"
        :timezone="auth.user?.timezone"
        @download="downloadFile"
    /></el-card>
  </div>
</template>
