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
  const sessionVersion = ref(0)

  function initialize(): Promise<void> {
    if (initialized.value) return Promise.resolve()
    if (pending) return pending
    const version = sessionVersion.value
    loading.value = true
    initializationError.value = null
    pending = (async () => {
      try {
        const current = await authApi.getCurrentUser()
        if (version !== sessionVersion.value) return
        user.value = current
        initialized.value = true
      } catch (error) {
        if (version !== sessionVersion.value) return
        if (error instanceof ApiError && error.status === 401) {
          user.value = null
          initialized.value = true
        } else {
          initializationError.value = error
          throw error
        }
      } finally {
        if (version === sessionVersion.value) {
          loading.value = false
          pending = null
        }
      }
    })()
    return pending
  }

  async function login(username: string, password: string) {
    const version = ++sessionVersion.value
    pending = null
    loading.value = true
    initializationError.value = null
    try {
      const loggedIn = await authApi.login(username, password)
      if (version !== sessionVersion.value) return false
      user.value = loggedIn
      initialized.value = true
      return true
    } finally {
      if (version === sessionVersion.value) loading.value = false
    }
  }

  async function logout() {
    const version = sessionVersion.value
    try {
      await authApi.logout()
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 401) throw error
    } finally {
      if (version === sessionVersion.value) clear()
    }
  }

  function clear() {
    clearUnsavedChanges()
    clearPositions()
    sessionVersion.value += 1
    pending = null
    loading.value = false
    initializationError.value = null
    user.value = null
    initialized.value = true
  }

  function setUser(nextUser: CurrentUser, expectedVersion?: number): boolean {
    if (expectedVersion !== undefined && expectedVersion !== sessionVersion.value) return false
    user.value = nextUser
    return true
  }

  return {
    user,
    sessionVersion,
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
