<script setup lang="ts">
import { timezones, currencies } from '@/utils/profileOptions'
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { changePassword, updateProfile } from '@/api/users'
import { ApiError } from '@/types/api'
import { useAuthStore } from '@/stores/auth'
import PageHeader from '@/components/common/PageHeader.vue'
import { getFieldErrors } from '@/utils/apiErrors'

const auth = useAuthStore()
const saving = ref(false)
const passwordSaving = ref(false)
const profileError = ref('')
const profileFieldErrors = ref<Record<string, string>>({})
const profile = reactive({ username: '', timezone: '', currency_code: '' })
const password = reactive({ current: '', next: '', confirm: '' })
onMounted(() => {
  if (auth.user)
    Object.assign(profile, {
      username: auth.user.username,
      timezone: auth.user.timezone,
      currency_code: auth.user.currency_code,
    })
})
async function saveProfile() {
  profileError.value = ''
  profileFieldErrors.value = {}
  if (!profile.username.trim()) {
    profileError.value = '用户名不能为空'
    return
  }
  saving.value = true
  try {
    const updated = await updateProfile({
      username: profile.username.trim(),
      timezone: profile.timezone,
      currency_code: profile.currency_code,
    })
    auth.setUser(updated)
    ElMessage.success('个人资料已保存')
  } catch (cause) {
    profileFieldErrors.value = getFieldErrors(cause)
    profileError.value = cause instanceof ApiError ? cause.message : '保存失败'
  } finally {
    saving.value = false
  }
}
async function savePassword() {
  if (password.next.length < 8) {
    ElMessage.error('新密码至少 8 个字符')
    return
  }
  if (password.next !== password.confirm) {
    ElMessage.error('两次新密码不一致')
    return
  }
  passwordSaving.value = true
  try {
    await changePassword(password.current, password.next)
    auth.clear()
    ElMessage.success('密码已修改，请重新登录')
    window.location.assign('/login')
  } catch (cause) {
    ElMessage.error(cause instanceof ApiError ? cause.message : '密码修改失败')
  } finally {
    passwordSaving.value = false
  }
}
</script>

<template>
  <div class="page-container">
    <PageHeader title="个人设置" />
    <div class="settings-grid">
      <el-card
        ><template #header>基本资料</template
        ><el-form label-position="top"
          ><el-form-item label="用户 ID"
            ><el-input :model-value="auth.user?.id" disabled /></el-form-item
          ><el-form-item label="角色"
            ><el-input
              :model-value="auth.user?.role === 'admin' ? '管理员' : '普通用户'"
              disabled /></el-form-item
          ><el-form-item label="用户名" :error="profileFieldErrors.username"
            ><el-input v-model="profile.username" maxlength="64" /></el-form-item
          ><el-form-item label="时区" :error="profileFieldErrors.timezone"
            ><el-select v-model="profile.timezone" filterable style="width: 100%"
              ><el-option
                v-for="timezone in timezones"
                :key="timezone"
                :label="timezone"
                :value="timezone" /></el-select></el-form-item
          ><el-form-item label="默认货币" :error="profileFieldErrors.currency_code"
            ><el-select v-model="profile.currency_code" style="width: 100%"
              ><el-option
                v-for="currency in currencies"
                :key="currency"
                :label="currency"
                :value="currency" /></el-select></el-form-item
          ><el-alert
            v-if="profileError"
            :title="profileError"
            type="error"
            :closable="false"
          /><el-button type="primary" :loading="saving" @click="saveProfile"
            >保存资料</el-button
          ></el-form
        ></el-card
      ><el-card
        ><template #header>修改密码</template
        ><el-form label-position="top"
          ><el-form-item label="当前密码"
            ><el-input
              v-model="password.current"
              type="password"
              show-password
              autocomplete="current-password" /></el-form-item
          ><el-form-item label="新密码"
            ><el-input
              v-model="password.next"
              type="password"
              show-password
              autocomplete="new-password" /></el-form-item
          ><el-form-item label="确认新密码"
            ><el-input
              v-model="password.confirm"
              type="password"
              show-password
              autocomplete="new-password" /></el-form-item
          ><el-button type="primary" :loading="passwordSaving" @click="savePassword"
            >修改密码</el-button
          ></el-form
        ></el-card
      >
    </div>
  </div>
</template>

<style scoped>
.settings-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
}
.settings-grid .el-card {
  max-width: 720px;
}
@media (max-width: 800px) {
  .settings-grid {
    grid-template-columns: 1fr;
  }
}
</style>
