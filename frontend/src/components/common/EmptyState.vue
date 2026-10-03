<script setup lang="ts">
import 'element-plus/es/components/empty/style/css'

import { ElEmpty } from 'element-plus'
defineProps<{ title: string; description?: string; compact?: boolean }>()
</script>

<template>
  <div class="state-panel" :class="{ 'state-panel--compact': compact }">
    <el-empty :image-size="compact ? 56 : 80">
      <template #description>
        <h2>{{ title }}</h2>
        <p v-if="description">{{ description }}</p>
      </template>
      <slot />
    </el-empty>
  </div>
</template>
