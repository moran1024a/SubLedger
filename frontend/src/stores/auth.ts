import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import * as authApi from '@/api/auth'
import { ApiError, type CurrentUser } from '@/types/api'
import { clearPositions } from '@/utils/navigation'
import { clearUnsavedChanges } from '@/composables/useUnsavedChanges'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<CurrentUser | null>(null)
  const initialized = ref(false)
  const loading = ref(false)
  const isAdmin = computed(() => user.value?.id === 0 && user.value?.role === 'admin')

  const initializationError = ref<unknown>(null)
  let pending: Promise<void> | null = null
  let generation = 0

  function initialize(): Promise<void> {
    if (initialized.value) return Promise.resolve()
    if (pending) return pending
    const version = generation
    loading.value = true
    initializationError.value = null
    pending = (async () => {
      try {
        const current = await authApi.getCurrentUser()
        if (version !== generation) return
        user.value = current
        initialized.value = true
      } catch (error) {
        if (version !== generation) return
        if (error instanceof ApiError && error.status === 401) {
          user.value = null
          initialized.value = true
        } else {
          initializationError.value = error
          throw error
        }
      } finally {
        if (version === generation) loading.value = false
        pending = null
      }
    })()
    return pending
  }

  async function login(username: string, password: string) {
    generation += 1
    loading.value = true
    initializationError.value = null
    try {
      user.value = await authApi.login(username, password)
      initialized.value = true
    } finally {
      loading.value = false
    }
  }

  async function logout() {
    try {
      await authApi.logout()
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 401) throw error
    } finally {
      clear()
    }
  }

  function clear() {
    clearUnsavedChanges()
    clearPositions()
    generation += 1
    loading.value = false
    initializationError.value = null
    user.value = null
    initialized.value = true
  }

  function setUser(nextUser: CurrentUser) {
    user.value = nextUser
  }

  return {
    user,
    initializationError,
    initialized,
    loading,
    isAdmin,
    initialize,
    login,
    logout,
    clear,
    setUser,
  }
})
