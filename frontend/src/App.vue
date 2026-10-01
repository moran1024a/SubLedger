<script setup lang="ts">
import { ref } from 'vue'
import LoadingBlock from '@/components/common/LoadingBlock.vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import ErrorState from '@/components/common/ErrorState.vue'
const auth = useAuthStore()
const router = useRouter()
const retrying = ref(false)
async function retry() {
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
  <ErrorState v-if="auth.initializationError" @retry="retry" />
  <LoadingBlock v-else-if="!auth.initialized || retrying" />
  <router-view v-else />
</template>
