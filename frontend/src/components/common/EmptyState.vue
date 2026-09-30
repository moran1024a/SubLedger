<script setup lang="ts">
defineProps<{ title: string; description?: string }>()
</script>

<template><el-empty :description="description || title" /></template>
