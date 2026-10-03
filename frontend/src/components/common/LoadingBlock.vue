<script setup lang="ts">
import 'element-plus/es/components/skeleton/style/css'

import { ElSkeleton } from 'element-plus'
withDefaults(
  defineProps<{ label?: string; compact?: boolean; variant?: 'block' | 'table' | 'stats' }>(),
  {
    label: '正在加载，请稍候',
    compact: false,
    variant: 'block',
  },
)
</script>
<template>
  <div
    class="state-panel loading-state"
    :class="{ 'state-panel--compact': compact }"
    role="status"
    aria-busy="true"
  >
    <p class="loading-label">{{ label }}</p>
    <div v-if="variant === 'table'" class="skeleton-table" aria-hidden="true">
      <div v-for="row in 5" :key="row" class="skeleton-row">
        <span v-for="cell in 4" :key="cell" class="skeleton-bar"></span>
      </div>
    </div>
    <div v-else-if="variant === 'stats'" class="card-grid" aria-hidden="true">
      <div v-for="card in 4" :key="card" class="skeleton-card">
        <span class="skeleton-bar skeleton-bar--label"></span>
        <span class="skeleton-bar skeleton-bar--number"></span>
      </div>
    </div>
    <el-skeleton v-else :rows="compact ? 2 : 4" animated aria-hidden="true" />
  </div>
</template>
<style scoped>
.loading-state .loading-label {
  margin: 0 0 var(--sl-space-4);
}
.skeleton-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--sl-space-4);
  padding: 10px 0;
}
.skeleton-card {
  display: flex;
  flex-direction: column;
  gap: var(--sl-space-3);
  padding: var(--sl-space-4);
  border: 1px solid var(--sl-border);
  border-radius: var(--sl-radius);
  background: var(--sl-surface);
}
.skeleton-bar {
  display: block;
  height: 14px;
  border-radius: var(--sl-radius-sm);
  background: var(--sl-surface-muted);
  animation: skeleton-pulse 1.4s var(--sl-ease) infinite;
}
.skeleton-bar--label {
  width: 40%;
}
.skeleton-bar--number {
  height: 24px;
  width: 70%;
}
@keyframes skeleton-pulse {
  50% {
    opacity: 0.45;
  }
}
</style>
