<script setup lang="ts">
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/result/style/css'

import { ElButton, ElMessage, ElResult } from 'element-plus'
const props = defineProps<{ message?: string; requestId?: string; compact?: boolean }>()
defineEmits<{ retry: [] }>()

async function copyRequestId() {
  if (!props.requestId) return
  try {
    await window.navigator.clipboard.writeText(props.requestId)
    ElMessage.success('已复制')
  } catch {
    ElMessage.error('复制失败，请手动复制')
  }
}
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
    <p v-if="requestId" class="error-request-id">
      请求 ID：{{ requestId
      }}<el-button link type="primary" class="copy-button" @click="copyRequestId">复制</el-button>
    </p>
  </div>
</template>

<style scoped>
.error-request-id {
  text-align: center;
  font-size: var(--sl-font-size-xs);
}
.copy-button {
  margin-left: var(--sl-space-2);
  font-size: var(--sl-font-size-xs);
}
</style>
