<script setup lang="ts">
import { ElAlert, ElButton } from 'element-plus'
import 'element-plus/es/components/alert/style/css'
import 'element-plus/es/components/button/style/css'
defineProps<{ message: string; action?: string }>()
defineEmits<{ check: [] }>()
</script>
<template>
  <el-alert
    v-if="message"
    :title="message"
    type="warning"
    :closable="false"
    class="operation-feedback"
    role="status"
  >
    <el-button v-if="action" text @click="$emit('check')">{{ action }}</el-button>
  </el-alert>
</template>
<style scoped>
.operation-feedback {
  margin-bottom: 16px;
}
</style>
