<script setup lang="ts">
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/result/style/css'

import { ElButton, ElResult } from 'element-plus'
defineProps<{ message?: string; requestId?: string; compact?: boolean }>()
defineEmits<{ retry: [] }>()
</script>

<template>
  <div class="state-panel" :class="{ 'state-panel--compact': compact }" role="alert">
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
  </div>
</template>

<style scoped>
.error-request-id {
  text-align: center;
  font-size: 12px;
}
</style>
