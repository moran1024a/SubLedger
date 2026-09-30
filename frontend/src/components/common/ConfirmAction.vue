<script setup lang="ts">
import { ElMessageBox } from 'element-plus'

const props = withDefaults(
  defineProps<{
    title: string
    message: string
    confirmText?: string
    type?: 'warning' | 'error'
  }>(),
  { confirmText: '确认', type: 'warning' },
)
defineEmits<{ confirmed: [] }>()

async function confirm() {
  await ElMessageBox.confirm(props.message, props.title, {
    type: props.type,
    confirmButtonText: props.confirmText,
    cancelButtonText: '取消',
  })
}
</script>

<template>
  <el-button @click="confirm"><slot /></el-button>
</template>
