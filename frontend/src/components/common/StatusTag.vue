<script setup lang="ts">
import 'element-plus/es/components/tag/style/css'

import { ElTag } from 'element-plus'
defineProps<{ active: boolean; activeText?: string; inactiveText?: string }>()
</script>

<template>
  <el-tag class="status-tag" :type="active ? 'success' : 'info'">{{
    active ? activeText || '启用' : inactiveText || '停用'
  }}</el-tag>
</template>

<style scoped>
.status-tag {
  font-weight: 500;
  white-space: normal;
  height: auto;
  min-height: 24px;
  padding-block: 2px;
  overflow-wrap: anywhere;
}
</style>
