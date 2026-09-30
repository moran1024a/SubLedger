<script setup lang="ts">
import type { LogFile } from '@/types/api'
import { formatDateTime, formatFileSize } from '@/utils/format'
defineProps<{ files: LogFile[]; downloading?: string | null }>()
defineEmits<{ download: [filename?: string] }>()
</script>

<template>
  <el-table :data="files" stripe
    ><el-table-column prop="date" label="日期" width="140" /><el-table-column
      prop="filename"
      label="文件名"
      min-width="180"
    /><el-table-column label="大小" width="120"
      ><template #default="{ row }">{{ formatFileSize(row.size) }}</template></el-table-column
    ><el-table-column label="最后修改" width="180"
      ><template #default="{ row }">{{
        formatDateTime(row.modified_at)
      }}</template></el-table-column
    ><el-table-column label="操作" width="110"
      ><template #default="{ row }"
        ><el-button
          link
          type="primary"
          :loading="downloading === row.filename"
          :disabled="downloading != null"
          @click="$emit('download', row.filename)"
          >下载</el-button
        ></template
      ></el-table-column
    ></el-table
  >
</template>
