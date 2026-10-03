<script setup lang="ts">
import 'element-plus/es/components/skeleton/style/css'

import { ElSkeleton } from 'element-plus'
withDefaults(defineProps<{ label?: string; compact?: boolean }>(), {
  label: '正在加载，请稍候',
  compact: false,
})
</script>
<template>
  <div
    class="state-panel loading-state"
    :class="{ 'state-panel--compact': compact }"
    role="status"
    aria-busy="true"
  >
    <p class="loading-label">{{ label }}</p>
    <el-skeleton :rows="compact ? 2 : 4" animated aria-hidden="true" />
  </div>
</template>
<style scoped>
.loading-state .loading-label {
  margin: 0 0 var(--sl-space-4);
}
</style>
