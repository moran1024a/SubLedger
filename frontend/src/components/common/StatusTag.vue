<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{
  active: boolean
  activeText?: string
  inactiveText?: string
  tone?: 'success' | 'info' | 'warning' | 'danger'
}>()
const tone = computed(() => props.tone ?? (props.active ? 'success' : 'info'))
</script>

<template>
  <span class="status-tag" :class="`status-tag--${tone}`"
    ><span class="status-dot" aria-hidden="true"></span
    >{{ active ? activeText || '启用' : inactiveText || '停用' }}</span
  >
</template>

<style scoped>
.status-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--sl-font-size-sm);
  font-weight: 500;
  /* Same line box as the surrounding text so the label sits level with it (e.g. table cells). */
  line-height: inherit;
  vertical-align: top;
  overflow-wrap: anywhere;
  color: var(--sl-info-text);
}
.status-dot {
  flex-shrink: 0;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}
.status-tag--success {
  color: var(--sl-success-text);
}
.status-tag--info {
  color: var(--sl-info-text);
}
.status-tag--warning {
  color: var(--sl-warning-text);
}
.status-tag--danger {
  color: var(--sl-danger-text);
}
</style>
