<script setup lang="ts">
import { timezones, currencies } from '@/utils/profileOptions'
import { onBeforeUnmount, watch, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { disableUser, enableUser, getUser, resetUserPassword, updateUser } from '@/api/users'
import { ApiError, type CurrentUser } from '@/types/api'
import PageHeader from '@/components/common/PageHeader.vue'
import LoadingBlock from '@/components/common/LoadingBlock.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import { asApiError, getFieldErrors } from '@/utils/apiErrors'
const route = useRoute()
const router = useRouter()
const user = ref<CurrentUser | null>(null)
const loading = ref(true)
const saving = ref(false)
const resetting = ref(false)
const toggling = ref(false)
const error = ref<ApiError | null>(null)
const fieldErrors = ref<Record<string, string>>({})
const password = reactive({ value: '', confirm: '' })
const form = reactive({ username: '', timezone: '', currency_code: '' })
let generation = 0
let requestSequence = 0
onBeforeUnmount(() => {
  generation += 1
  requestSequence += 1
})
async function load() {
  const sequence = ++requestSequence
  const targetId = Number(route.params.id)
  loading.value = true
  error.value = null
  try {
    const loaded = await getUser(targetId)
    if (sequence !== requestSequence) return
    user.value = loaded
    Object.assign(form, {
      username: loaded.username,
      timezone: loaded.timezone,
      currency_code: loaded.currency_code,
    })
  } catch (cause) {
    if (sequence !== requestSequence) return
    error.value = asApiError(cause, '无法连接服务器，请检查网络或服务状态。')
  } finally {
    if (sequence === requestSequence) loading.value = false
  }
}
async function save() {
  if (!user.value || saving.value || resetting.value || toggling.value) return
  fieldErrors.value = {}
  saving.value = true
  const targetId = user.value.id
  const version = generation
  const current = () => version === generation && Number(route.params.id) === targetId
  try {
    const updated = await updateUser(targetId, {
      username: form.username.trim(),
      timezone: form.timezone,
      currency_code: form.currency_code,
    })
    if (!current()) return
    user.value = updated
    ElMessage.success('用户资料已保存')
  } catch (cause) {
    if (!current()) return
    fieldErrors.value = getFieldErrors(cause)
    ElMessage.error(cause instanceof ApiError ? cause.message : '保存失败')
  } finally {
    saving.value = false
  }
}
async function reset() {
  if (resetting.value || saving.value || toggling.value) return
  if (!user.value || password.value.length < 8 || password.value !== password.confirm) {
    ElMessage.error('请确认至少 8 位且一致的新密码')
    return
  }
  const targetId = user.value.id
  const version = generation
  const current = () => version === generation && Number(route.params.id) === targetId
  resetting.value = true
  try {
    await ElMessageBox.confirm('重置后该用户的现有会话将失效，需要重新登录。', '确认重置密码', {
      type: 'warning',
      confirmButtonText: '重置',
      cancelButtonText: '取消',
    })
    if (!current()) return
    resetting.value = true
    await resetUserPassword(targetId, password.value)
    if (!current()) return
    password.value = ''
    password.confirm = ''
    ElMessage.success('密码已重置')
  } catch (cause) {
    if (!current()) return
    if (cause !== 'cancel' && cause !== 'close')
      ElMessage.error(cause instanceof ApiError ? cause.message : '重置失败')
  } finally {
    resetting.value = false
  }
}
async function toggle() {
  if (!user.value || toggling.value || saving.value || resetting.value) return
  toggling.value = true
  const wasActive = user.value.is_active
  const targetId = user.value.id
  const version = generation
  const current = () => version === generation && Number(route.params.id) === targetId
  try {
    if (wasActive)
      await ElMessageBox.confirm(
        '用户无法继续登录，当前会话失效，数据会保留，账单和提醒会停止，停用期间的历史不会补处理。',
        '确认停用用户',
        { type: 'warning', confirmButtonText: '停用', cancelButtonText: '取消' },
      )
    if (!current()) return
    toggling.value = true
    if (wasActive) await disableUser(targetId)
    else await enableUser(targetId)
    if (!current()) return
    ElMessage.success(wasActive ? '用户已停用' : '用户已启用')
    await load()
  } catch (cause) {
    if (!current()) return
    if (cause !== 'cancel' && cause !== 'close')
      ElMessage.error(cause instanceof ApiError ? cause.message : '操作失败')
  } finally {
    toggling.value = false
  }
}
watch(
  () => route.params.id,
  () => {
    generation += 1
    user.value = null
    fieldErrors.value = {}
    password.value = ''
    password.confirm = ''
    Object.assign(form, { username: '', timezone: '', currency_code: '' })
    const targetId = Number(route.params.id)
    requestSequence += 1
    if (Number.isSafeInteger(targetId) && targetId >= 0) void load()
  },
  { immediate: true, flush: 'sync' },
)
</script>

<template>
  <div class="page-container">
    <PageHeader title="用户详情"
      ><template #actions
        ><el-button @click="router.push('/admin/users')">返回列表</el-button
        ><el-button
          v-if="user && user.id !== 0"
          @click="router.push({ path: '/admin/logs/users', query: { user_id: user.id } })"
          >查看日志</el-button
        ><el-button
          v-if="user && user.id !== 0"
          :type="user.is_active ? 'danger' : 'success'"
          :loading="toggling"
          @click="toggle"
          >{{ user.is_active ? '停用' : '启用' }}</el-button
        ></template
      ></PageHeader
    ><LoadingBlock v-if="loading" /><ErrorState
      v-else-if="error"
      :message="error.message"
      :request-id="error.requestId"
      @retry="load"
    /><el-card v-else-if="user"
      ><el-descriptions :column="1" border
        ><el-descriptions-item label="ID">{{ user.id }}</el-descriptions-item
        ><el-descriptions-item label="角色">{{
          user.role === 'admin' ? '管理员' : '普通用户'
        }}</el-descriptions-item
        ><el-descriptions-item label="状态"
          ><StatusTag :active="user.is_active" /></el-descriptions-item></el-descriptions
      ><el-divider /><el-form label-position="top" class="detail-form"
        ><el-form-item label="用户名" :error="fieldErrors.username"
          ><el-input v-model="form.username" :disabled="user.id === 0" /></el-form-item
        ><el-form-item label="时区" :error="fieldErrors.timezone"
          ><el-select v-model="form.timezone" filterable style="width: 100%"
            ><el-option
              v-for="item in timezones"
              :key="item"
              :label="item"
              :value="item" /></el-select></el-form-item
        ><el-form-item label="货币" :error="fieldErrors.currency_code"
          ><el-select v-model="form.currency_code" style="width: 100%"
            ><el-option
              v-for="item in currencies"
              :key="item"
              :label="item"
              :value="item" /></el-select></el-form-item
        ><el-button type="primary" :loading="saving" :disabled="user.id === 0" @click="save"
          >保存资料</el-button
        ></el-form
      ><el-divider />
      <div v-if="user.id !== 0" class="detail-form">
        <h3>重置密码</h3>
        <el-form-item label="新密码"
          ><el-input v-model="password.value" type="password" show-password /></el-form-item
        ><el-form-item label="确认密码"
          ><el-input v-model="password.confirm" type="password" show-password /></el-form-item
        ><el-button type="warning" :loading="resetting" @click="reset">重置密码</el-button>
      </div></el-card
    >
  </div>
</template>

<style scoped>
.detail-form {
  max-width: 560px;
}
</style>
