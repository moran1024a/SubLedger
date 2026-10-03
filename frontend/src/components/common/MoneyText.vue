<script setup lang="ts">
import { formatMoney } from '@/utils/format'
defineProps<{ value: string; currency?: string }>()
</script>

<template>
  <span class="money-text">{{ formatMoney(value, currency) }}</span>
</template>
