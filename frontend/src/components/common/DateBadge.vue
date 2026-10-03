<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ date: string; today?: boolean }>()
const parts = computed(() => /^(\d{4})-(\d{2})-(\d{2})$/.exec(props.date))
const day = computed(() => (parts.value ? String(Number(parts.value[3])) : props.date))
const month = computed(() => (parts.value ? `${Number(parts.value[2])} 月` : ''))
</script>

<template>
  <time class="date-badge" :class="{ 'date-badge--today': today }" :datetime="date" :title="date">
    <span class="date-badge-day">{{ day }}</span>
    <span v-if="month" class="date-badge-month">{{ month }}</span>
  </time>
</template>

<style scoped>
.date-badge {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 44px;
  padding: 4px 0 6px;
  border-radius: var(--sl-radius-sm);
  background: var(--sl-surface-muted);
  color: var(--sl-text-secondary);
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
}
.date-badge--today {
  background: var(--sl-warning-soft);
  color: var(--sl-warning-text);
}
.date-badge-day {
  font-size: var(--sl-font-size-lg);
  font-weight: 600;
}
.date-badge-month {
  font-size: var(--sl-font-size-xs);
}
</style>
