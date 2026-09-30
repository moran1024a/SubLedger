import { ref } from 'vue'
import { defineStore } from 'pinia'

export const useUiStore = defineStore('ui', () => {
  const sidebarCollapsed = ref(false)
  const mobileMenuOpen = ref(false)
  return { sidebarCollapsed, mobileMenuOpen }
})
