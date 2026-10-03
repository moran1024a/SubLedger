<script setup lang="ts">
import { ref } from 'vue'
import LoadingBlock from '@/components/common/LoadingBlock.vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import ErrorState from '@/components/common/ErrorState.vue'
import { ElConfigProvider } from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import { asApiError } from '@/utils/apiErrors'
const auth = useAuthStore()
const router = useRouter()
const retrying = ref(false)
async function retry() {
  if (retrying.value) return
  retrying.value = true
  try {
    await auth.initialize()
    await router.replace(router.currentRoute.value.fullPath)
  } catch {
    // Keep the retry screen visible on a repeated network failure.
  } finally {
    retrying.value = false
  }
}
</script>

<template>
  <el-config-provider :locale="zhCn">
    <div v-if="auth.initializationError" class="page-container">
      <ErrorState
        :message="asApiError(auth.initializationError).message"
        :request-id="asApiError(auth.initializationError).requestId"
        @retry="retry"
      />
    </div>
    <div v-else-if="!auth.initialized || retrying" class="page-container"><LoadingBlock /></div>
    <router-view v-else />
  </el-config-provider>
</template>
