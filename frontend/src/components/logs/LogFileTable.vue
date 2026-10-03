<script setup lang="ts">
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/table/style/css'
import 'element-plus/es/components/table-column/style/css'

import { ElButton, ElTable, ElTableColumn } from 'element-plus'
import type { LogFile } from '@/types/api'
import { formatDateTime, formatFileSize } from '@/utils/format'
defineProps<{ files: LogFile[]; downloading?: string | null }>()
defineEmits<{ download: [filename?: string] }>()
</script>

<template>
  <div class="log-files">
    <el-table :data="files" stripe row-key="filename" class="log-table">
      <el-table-column prop="date" label="日期" width="128" class-name="tabular-nums" />
      <el-table-column prop="filename" label="文件名" min-width="180" />
      <el-table-column label="大小" width="110" align="right" class-name="tabular-nums">
        <template #default="{ row }">{{ formatFileSize(row.size) }}</template>
      </el-table-column>
      <el-table-column label="最后修改" width="180" class-name="tabular-nums">
        <template #default="{ row }">{{ formatDateTime(row.modified_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="90" align="right">
        <template #default="{ row }">
          <el-button
            link
            type="primary"
            :aria-label="`下载 ${row.filename}`"
            :loading="downloading === row.filename"
            :disabled="downloading != null"
            @click="$emit('download', row.filename)"
            >下载</el-button
          >
        </template>
      </el-table-column>
    </el-table>
    <ul class="log-cards" aria-label="日志文件">
      <li v-for="file in files" :key="file.filename" class="log-card">
        <div class="log-card-header">
          <h2>{{ file.filename }}</h2>
          <el-button
            link
            type="primary"
            :aria-label="`下载 ${file.filename}`"
            :loading="downloading === file.filename"
            :disabled="downloading != null"
            @click="$emit('download', file.filename)"
            >下载</el-button
          >
        </div>
        <dl>
          <div>
            <dt>日期</dt>
            <dd class="tabular-nums">{{ file.date }}</dd>
          </div>
          <div>
            <dt>大小</dt>
            <dd class="tabular-nums">{{ formatFileSize(file.size) }}</dd>
          </div>
          <div>
            <dt>最后修改</dt>
            <dd class="tabular-nums">{{ formatDateTime(file.modified_at) }}</dd>
          </div>
        </dl>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.log-files {
  min-width: 0;
}
.log-cards {
  display: none;
  list-style: none;
  margin: 0;
  padding: 0;
}
.log-card {
  padding: var(--sl-space-4) 0;
  border-bottom: 1px solid var(--sl-border);
}
.log-card:first-child {
  padding-top: 0;
}
.log-card:last-child {
  border-bottom: 0;
  padding-bottom: 0;
}
.log-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--sl-space-3);
}
.log-card-header h2 {
  margin: 0;
  font-size: var(--sl-font-size);
  font-weight: 600;
  min-width: 0;
  overflow-wrap: anywhere;
}
.log-card-header :deep(.el-button) {
  flex-shrink: 0;
}
dl {
  margin: var(--sl-space-3) 0 0;
}
dl > div {
  display: flex;
  justify-content: space-between;
  gap: var(--sl-space-4);
  margin-top: var(--sl-space-1);
}
dt {
  color: var(--sl-text-muted);
  flex-shrink: 0;
}
dd {
  margin: 0;
  min-width: 0;
  text-align: right;
  overflow-wrap: anywhere;
}
@media (max-width: 700px) {
  .log-table {
    display: none;
  }
  .log-cards {
    display: block;
  }
}
</style>
