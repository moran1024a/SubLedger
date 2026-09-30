<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <el-result status="404" title="页面不存在" sub-title="请检查访问地址"
    ><template #extra
      ><el-button type="primary" @click="router.push('/')">返回首页</el-button></template
    ></el-result
  >
</template>
