<script setup lang="ts">
import 'element-plus/es/components/tag/style/css'

import { ElTag } from 'element-plus'
defineProps<{ active: boolean; activeText?: string; inactiveText?: string }>()
</script>

<template>
  <el-tag :type="active ? 'success' : 'info'">{{
    active ? activeText || '启用' : inactiveText || '停用'
  }}</el-tag>
</template>
