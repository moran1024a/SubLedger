<script setup lang="ts">
import 'element-plus/es/components/empty/style/css'

import { ElEmpty } from 'element-plus'
defineProps<{ title: string; description?: string }>()
</script>

<template><el-empty :description="description || title" /></template>
