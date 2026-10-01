<script setup lang="ts">
import 'element-plus/es/components/alert/style/css'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/card/style/css'
import 'element-plus/es/components/form/style/css'
import 'element-plus/es/components/form-item/style/css'
import 'element-plus/es/components/input/style/css'
import 'element-plus/es/components/message/style/css'

import { ElAlert, ElButton, ElCard, ElForm, ElFormItem, ElInput } from 'element-plus'
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ApiError } from '@/types/api'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const username = ref('')
const password = ref('')
const error = ref('')
const submitting = ref(false)

async function submit() {
  error.value = ''
  if (!username.value.trim() || !password.value) {
    error.value = '请输入用户名和密码'
    return
  }
  submitting.value = true
  try {
    await auth.login(username.value.trim(), password.value)
    await router.push(
      typeof route.query.redirect === 'string'
        ? route.query.redirect
        : auth.isAdmin
          ? '/admin'
          : '/',
    )
  } catch (cause) {
    const apiError = cause instanceof ApiError ? cause : null
    error.value =
      apiError?.status === 429
        ? '请求过于频繁，请稍后再试'
        : apiError?.status === 500
          ? '服务暂时不可用，请稍后再试'
          : apiError?.status === 0
            ? '无法连接服务器，请检查网络或服务状态。'
            : '用户名或密码错误'
    password.value = ''
    ElMessage.error(error.value)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="login-page">
    <el-card class="login-card"
      ><h1>订阅本</h1>
      <p class="subtitle">SubLedger · 轻量订阅账单管理</p>
      <el-form @submit.prevent="submit">
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
  padding: 16px;
  background: #f5f7fa;
}
.login-card {
  width: min(400px, 100%);
}
.login-card h1 {
  margin: 0;
  text-align: center;
}
.subtitle,
.register-note {
  text-align: center;
  color: #6b7280;
}
.login-error {
  margin-bottom: 18px;
}
.submit-button {
  width: 100%;
}
</style>
