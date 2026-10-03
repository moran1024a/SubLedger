<script setup lang="ts">
import 'element-plus/es/components/alert/style/css'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/card/style/css'
import 'element-plus/es/components/form/style/css'
import 'element-plus/es/components/form-item/style/css'
import 'element-plus/es/components/input/style/css'

import { ElAlert, ElButton, ElCard, ElForm, ElFormItem, ElInput } from 'element-plus'
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError } from '@/types/api'
import { useAuthStore } from '@/stores/auth'
import { useViewScope } from '@/composables/useViewScope'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const username = ref('')
const password = ref('')
const error = ref('')
const submitting = ref(false)
const scope = useViewScope()

// Only an internal route the signed-in role may actually open is followed.
function safeRedirect(): string | null {
  const redirect = route.query.redirect
  if (typeof redirect !== 'string') return null
  if (!redirect.startsWith('/') || redirect.startsWith('//') || redirect.includes('\\')) return null
  const resolved = router.resolve(redirect)
  if (!resolved.matched.some((record) => record.meta.requiresAuth)) return null
  if (resolved.matched.some((record) => record.meta.public)) return null
  const role = auth.isAdmin ? 'admin' : 'user'
  const denied = resolved.matched.some((record) => {
    const roles = record.meta.roles as string[] | undefined
    return roles !== undefined && !roles.includes(role)
  })
  return denied ? null : redirect
}

function loginErrorMessage(apiError: ApiError | null): string {
  if (apiError?.code === 'REQUEST_TIMEOUT') return '登录请求超时，请刷新页面确认是否已登录'
  if (apiError?.status === 422) return '用户名或密码格式不正确'
  if (apiError?.status === 429) return '请求过于频繁，请稍后再试'
  if (apiError && apiError.status >= 500) return '服务暂时不可用，请稍后再试'
  if (apiError?.status === 0) return '无法连接服务器，请检查网络或服务状态。'
  return '用户名或密码错误'
}

async function submit() {
  if (submitting.value) return
  error.value = ''
  if (!username.value.trim() || !password.value) {
    error.value = '请输入用户名和密码'
    return
  }
  submitting.value = true
  const current = scope.capture()
  try {
    const loggedIn = await auth.login(username.value.trim(), password.value)
    if (!current() || !loggedIn) return
    await router.push(safeRedirect() ?? (auth.isAdmin ? '/admin' : '/'))
  } catch (cause) {
    if (!current()) return
    const apiError = cause instanceof ApiError ? cause : null
    error.value = loginErrorMessage(apiError)
    if (apiError?.status === 401) password.value = ''
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="login-page">
    <el-card class="login-card"
      ><div class="brand-mark" aria-hidden="true">订</div>
      <h1>订阅本</h1>
      <p class="subtitle">SubLedger · 轻量订阅账单管理</p>
      <el-form label-position="top" :disabled="submitting" @submit.prevent="submit">
        <el-form-item label="用户名"
          ><el-input v-model="username" autocomplete="username"
        /></el-form-item>
        <el-form-item label="密码"
          ><el-input
            v-model="password"
            type="password"
            show-password
            autocomplete="current-password"
        /></el-form-item>
        <el-alert v-if="error" :title="error" type="error" :closable="false" class="login-error" />
        <el-button native-type="submit" type="primary" :loading="submitting" class="submit-button"
          >登录</el-button
        >
      </el-form>
      <p class="register-note">系统不开放注册，新账户请联系管理员创建</p></el-card
    >
  </main>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: var(--sl-space-4);
  background: linear-gradient(160deg, #eef3ff, #f7f9fc 60%);
}
.login-card {
  width: min(400px, 100%);
  border-radius: var(--sl-radius-lg);
  box-shadow: var(--sl-shadow-3);
  animation: sl-fade-up var(--sl-duration-slow) var(--sl-ease-out) both;
}
.brand-mark {
  width: 48px;
  height: 48px;
  margin: 0 auto var(--sl-space-3);
  border-radius: 50%;
  background: var(--sl-primary);
  color: #fff;
  font-size: var(--sl-font-size-lg);
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}
.login-card h1 {
  margin: 0;
  text-align: center;
}
.subtitle,
.register-note {
  text-align: center;
  color: var(--sl-text-muted);
}
.login-error {
  margin-bottom: 18px;
}
.submit-button {
  width: 100%;
}
</style>
