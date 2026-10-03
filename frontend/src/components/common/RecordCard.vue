<script setup lang="ts">
defineSlots<{
  badge?: () => unknown
  title?: () => unknown
  meta?: () => unknown
  amount?: () => unknown
  actions?: () => unknown
}>()
</script>

<template>
  <div class="record-card">
    <div class="record-head">
      <span v-if="$slots.badge" class="record-badge"><slot name="badge" /></span>
      <div class="record-title"><slot name="title" /></div>
      <div v-if="$slots.amount" class="record-amount"><slot name="amount" /></div>
    </div>
    <div v-if="$slots.meta" class="record-meta"><slot name="meta" /></div>
    <div v-if="$slots.actions" class="record-actions"><slot name="actions" /></div>
  </div>
</template>

<style scoped>
.record-card {
  display: flex;
  flex-direction: column;
  gap: var(--sl-space-2);
  padding: var(--sl-space-4);
  border: 1px solid var(--sl-border);
  border-radius: var(--sl-radius);
  background: var(--sl-surface);
  box-shadow: var(--sl-shadow-1);
  min-width: 0;
}
.record-head {
  display: flex;
  align-items: flex-start;
  gap: var(--sl-space-2);
  min-width: 0;
}
.record-badge {
  flex-shrink: 0;
}
.record-title {
  flex: 1;
  min-width: 0;
  font-weight: 600;
  overflow-wrap: anywhere;
}
.record-amount {
  margin-left: auto;
  text-align: right;
  font-weight: 600;
  white-space: nowrap;
}
.record-meta {
  color: var(--sl-text-muted);
  font-size: var(--sl-font-size-sm);
  overflow-wrap: anywhere;
}
.record-actions {
  display: flex;
  gap: var(--sl-space-2);
  margin-top: var(--sl-space-1);
}
.record-actions > * {
  flex: 1 1 0;
  min-width: 0;
}
.record-actions :deep(.el-button) {
  width: 100%;
  margin-left: 0;
}
</style>
