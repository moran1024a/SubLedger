<script setup lang="ts">
import { formatMoney } from '@/utils/format'
defineProps<{ value: string; currency?: string }>()
</script>

<template>{{ formatMoney(value, currency) }}</template>
