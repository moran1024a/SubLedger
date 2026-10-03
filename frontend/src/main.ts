import { createApp } from 'vue'
import { createPinia } from 'pinia'
import './styles/base.css'
import App from './App.vue'
import router from './router'
import {
  setForbiddenHandler,
  setUnauthorizedHandler,
  setSessionVersionProvider,
} from './api/client'
import { useAuthStore } from './stores/auth'

const app = createApp(App)
const pinia = createPinia()
let authRedirecting = false

app.use(pinia).use(router)
setSessionVersionProvider(() => useAuthStore(pinia).sessionVersion)

setUnauthorizedHandler(async (_error, url) => {
  const auth = useAuthStore(pinia)
  const wasInitialized = auth.initialized
  if (url.endsWith('/auth/login') || (!wasInitialized && url.endsWith('/auth/me'))) return
  auth.clear()
  if (
    url.endsWith('/auth/login') ||
    (!wasInitialized && url.endsWith('/auth/me')) ||
    router.currentRoute.value.name === 'login' ||
    authRedirecting
  )
    return

  authRedirecting = true
  const currentRoute = router.currentRoute.value
  const query = currentRoute.meta.public ? undefined : { redirect: currentRoute.fullPath }
  try {
    await router.replace({ name: 'login', query })
  } finally {
    authRedirecting = false
  }
})

setForbiddenHandler(async () => {
  if (router.currentRoute.value.name !== 'forbidden') await router.replace({ name: 'forbidden' })
})

app.mount('#app')
