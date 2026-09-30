import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import * as authApi from '@/api/auth'
import { ApiError, type CurrentUser } from '@/types/api'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<CurrentUser | null>(null)
  const initialized = ref(false)
  const loading = ref(false)
  const isAdmin = computed(() => user.value?.id === 0 && user.value?.role === 'admin')

  async function initialize() {
    if (initialized.value) return
    loading.value = true
    try {
      user.value = await authApi.getCurrentUser()
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 401) throw error
      user.value = null
    } finally {
      initialized.value = true
      loading.value = false
    }
  }

  async function login(username: string, password: string) {
    loading.value = true
    try {
      await authApi.login(username, password)
      user.value = await authApi.getCurrentUser()
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
    user.value = null
    initialized.value = true
  }

  function setUser(nextUser: CurrentUser) {
    user.value = nextUser
  }

  return { user, initialized, loading, isAdmin, initialize, login, logout, clear, setUser }
})
