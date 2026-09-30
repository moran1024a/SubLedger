<script setup lang="ts">
defineProps<{ message?: string; requestId?: string }>()
defineEmits<{ retry: [] }>()
</script>

<template>
  <el-result
    icon="error"
    title="加载失败"
    :sub-title="message || '无法连接服务器，请检查网络或服务状态。'"
  >
    <template #extra
      ><el-button type="primary" @click="$emit('retry')">重新加载</el-button></template
    >
  </el-result>
  <p v-if="requestId" class="error-request-id">请求 ID：{{ requestId }}</p>
</template>

<style scoped>
.error-request-id {
  text-align: center;
  color: #6b7280;
}
</style>
