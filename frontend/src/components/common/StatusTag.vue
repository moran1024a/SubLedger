<script setup lang="ts">
defineProps<{ active: boolean; activeText?: string; inactiveText?: string }>()
</script>

<template>
  <el-tag :type="active ? 'success' : 'info'">{{
    active ? activeText || '启用' : inactiveText || '停用'
  }}</el-tag>
</template>
