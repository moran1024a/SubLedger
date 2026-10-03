<script setup lang="ts">
import { ElAlert, ElButton } from 'element-plus'
import 'element-plus/es/components/alert/style/css'
import 'element-plus/es/components/button/style/css'
defineProps<{ message: string; action?: string; disabled?: boolean; loading?: boolean }>()
defineEmits<{ check: [] }>()
</script>
<template>
  <el-alert
    v-if="message"
    :title="message"
    type="warning"
    :closable="false"
    show-icon
    class="operation-feedback"
    role="status"
    aria-live="polite"
  >
    <el-button v-if="action" text :disabled="disabled" :loading="loading" @click="$emit('check')">{{
      action
    }}</el-button>
  </el-alert>
</template>
<style scoped>
.operation-feedback {
  margin-bottom: var(--sl-space-4);
  align-items: flex-start;
  overflow-wrap: anywhere;
}
.operation-feedback :deep(.el-alert__title) {
  font-size: var(--sl-font-size);
  line-height: var(--sl-line-height);
}
.operation-feedback :deep(.el-alert__content) {
  min-width: 0;
}
.operation-feedback :deep(.el-button) {
  margin-top: var(--sl-space-1);
  white-space: normal;
}
</style>
