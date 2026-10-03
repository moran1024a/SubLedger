<script setup lang="ts">
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/card/style/css'
import 'element-plus/es/components/descriptions/style/css'
import 'element-plus/es/components/descriptions-item/style/css'
import 'element-plus/es/components/divider/style/css'
import 'element-plus/es/components/form/style/css'
import 'element-plus/es/components/form-item/style/css'
import 'element-plus/es/components/input/style/css'
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import 'element-plus/es/components/option/style/css'
import 'element-plus/es/components/select/style/css'

import {
  ElButton,
  ElCard,
  ElDescriptions,
  ElDescriptionsItem,
  ElDivider,
  ElForm,
  ElFormItem,
  ElInput,
  ElOption,
  ElSelect,
} from 'element-plus'
import { useQueryRequest } from '@/composables/useQueryRequest'
import { timezones, currencies } from '@/utils/profileOptions'
import { computed, watch, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { disableUser, enableUser, getUser, resetUserPassword, updateUser } from '@/api/users'
import { ApiError, type CurrentUser } from '@/types/api'
import PageHeader from '@/components/common/PageHeader.vue'
import LoadingBlock from '@/components/common/LoadingBlock.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import { asApiError, getFieldErrors, isUncertainWrite, writeErrorMessage } from '@/utils/apiErrors'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import { useViewScope } from '@/composables/useViewScope'
import { useAuthStore } from '@/stores/auth'
import OperationFeedback from '@/components/common/OperationFeedback.vue'
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const identity = computed(() => `${auth.sessionVersion}:${auth.user?.id ?? ''}:${route.params.id}`)
const user = ref<CurrentUser | null>(null)
const loading = ref(true)
const saving = ref(false)
const resetting = ref(false)
const toggling = ref(false)
const error = ref<ApiError | null>(null)
const fieldErrors = ref<Record<string, string>>({})
const password = reactive({ value: '', confirm: '' })
const form = reactive({ username: '', timezone: '', currency_code: '' })
const profileBaseline = ref('')
const passwordBaseline = JSON.stringify({ value: '', confirm: '' })
const busy = computed(() => saving.value || resetting.value || toggling.value || loading.value)
const { dirty } = useUnsavedChanges()
const scope = useViewScope(() => identity.value)
const operationMessage = ref('')
const uncertain = reactive({ profile: false, password: false, status: false })
const profileDirty = computed(
  () => Boolean(profileBaseline.value) && JSON.stringify(form) !== profileBaseline.value,
)
watch(
  [form, password, profileBaseline],
  () => {
    dirty.value = profileDirty.value || JSON.stringify(password) !== passwordBaseline
  },
  { deep: true, flush: 'sync' },
)
function fillProfile(loaded: CurrentUser) {
  Object.assign(form, {
    username: loaded.username,
    timezone: loaded.timezone,
    currency_code: loaded.currency_code,
  })
  profileBaseline.value = JSON.stringify(form)
}
const queryRequests = useQueryRequest()
async function load() {
  const signal = queryRequests.next()
  const current = scope.capture()
  const targetId = Number(route.params.id)
  loading.value = true
  error.value = null
  try {
    const loaded = await getUser(targetId, signal)
    if (signal.aborted || !current()) return
    user.value = loaded
    if (!profileDirty.value) fillProfile(loaded)
  } catch (cause) {
    if (!signal.aborted && current()) error.value = asApiError(cause)
  } finally {
    if (!signal.aborted && current()) loading.value = false
  }
}
async function check() {
  if (busy.value) return
  const current = scope.capture()
  await load()
  if (!current() || error.value || !user.value) return
  operationMessage.value = `已读取服务器当前资料：用户名 ${user.value.username} / 时区 ${user.value.timezone} / 货币 ${user.value.currency_code} / 状态 ${user.value.is_active ? '启用' : '停用'}。草稿已保留，请核对。${uncertain.profile || uncertain.password || uncertain.status ? '此前操作结果仍待确认。' : ''}读取资料不能确认密码是否重置，请让用户尝试新密码，核实后再次提交会要求确认。`
}
async function confirmAgain(kind: keyof typeof uncertain) {
  if (!uncertain[kind]) return true
  await ElMessageBox.confirm(
    kind === 'password'
      ? '上次密码重置结果待确认。请让用户尝试新密码；读取用户资料不能确认密码。确定已核实并再次重置吗？'
      : '上次操作结果待确认。请先重新读取当前资料和状态并核对，确定已核实并再次提交吗？',
    '确认再次提交',
    { type: 'warning', confirmButtonText: '继续提交', cancelButtonText: '取消' },
  )
  return true
}
async function save() {
  if (!user.value || user.value.id === 0 || busy.value) return
  if (!form.username.trim()) {
    fieldErrors.value = { username: '用户名不能为空' }
    return
  }
  saving.value = true
  fieldErrors.value = {}
  const targetId = user.value.id
  const current = scope.capture()
  const payload = {
    username: form.username.trim(),
    timezone: form.timezone,
    currency_code: form.currency_code,
  }
  try {
    await confirmAgain('profile')
    if (!current()) return
    const updated = await updateUser(targetId, payload)
    if (!current()) return
    user.value = updated
    fillProfile(updated)
    uncertain.profile = false
    operationMessage.value = ''
    ElMessage.success('用户资料已保存')
  } catch (cause) {
    if (!current() || cause === 'cancel' || cause === 'close') return
    fieldErrors.value = getFieldErrors(cause)
    uncertain.profile = isUncertainWrite(cause)
    operationMessage.value = writeErrorMessage(cause)
  } finally {
    if (current()) saving.value = false
  }
}
async function reset() {
  if (!user.value || user.value.id === 0 || busy.value) return
  if (password.value.length < 8 || password.value !== password.confirm) {
    ElMessage.error('请确认至少 8 位且一致的新密码')
    return
  }
  resetting.value = true
  const targetId = user.value.id
  const submitted = password.value
  const current = scope.capture()
  try {
    await confirmAgain('password')
    if (!current()) return
    await ElMessageBox.confirm('重置后该用户的现有会话将失效，需要重新登录。', '确认重置密码', {
      type: 'warning',
      confirmButtonText: '重置',
      cancelButtonText: '取消',
    })
    if (!current()) return
    await resetUserPassword(targetId, submitted)
    if (!current()) return
    Object.assign(password, { value: '', confirm: '' })
    uncertain.password = false
    operationMessage.value = ''
    ElMessage.success('密码已重置')
  } catch (cause) {
    if (!current() || cause === 'cancel' || cause === 'close') return
    uncertain.password = isUncertainWrite(cause)
    operationMessage.value = writeErrorMessage(cause)
    if (uncertain.password)
      operationMessage.value += '请让用户尝试新密码；核实后可明确确认再次重置。'
  } finally {
    if (current()) resetting.value = false
  }
}
async function toggle() {
  if (!user.value || user.value.id === 0 || busy.value) return
  toggling.value = true
  const wasActive = user.value.is_active
  const targetId = user.value.id
  const current = scope.capture()
  try {
    await confirmAgain('status')
    if (!current()) return
    if (wasActive)
      await ElMessageBox.confirm(
        '用户无法继续登录，当前会话失效，数据会保留，账单和提醒会停止，停用期间的历史不会补处理。',
        '确认停用用户',
        { type: 'warning', confirmButtonText: '停用', cancelButtonText: '取消' },
      )
    if (!current()) return
    if (wasActive) await disableUser(targetId)
    else await enableUser(targetId)
    if (!current() || !user.value) return
    user.value.is_active = !wasActive
    uncertain.status = false
    operationMessage.value = ''
    ElMessage.success(wasActive ? '用户已停用' : '用户已启用')
  } catch (cause) {
    if (!current() || cause === 'cancel' || cause === 'close') return
    uncertain.status = isUncertainWrite(cause)
    operationMessage.value = writeErrorMessage(cause)
  } finally {
    if (current()) toggling.value = false
  }
}
watch(
  [identity, () => auth.loading],
  ([session, authLoading], previous) => {
    if (session !== previous?.[0]) {
      user.value = null
      profileBaseline.value = ''
      fieldErrors.value = {}
      operationMessage.value = ''
      Object.assign(uncertain, { profile: false, password: false, status: false })
      Object.assign(password, { value: '', confirm: '' })
      Object.assign(form, { username: '', timezone: '', currency_code: '' })
      saving.value = false
      resetting.value = false
      toggling.value = false
      loading.value = false
      queryRequests.cancel()
    }
    const targetId = Number(route.params.id)
    if (!authLoading && auth.isAdmin && Number.isSafeInteger(targetId) && targetId >= 0) void load()
  },
  { immediate: true },
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
          :disabled="busy"
          @click="toggle"
          >{{ user.is_active ? '停用' : '启用' }}</el-button
        ></template
      ></PageHeader
    ><OperationFeedback
      :message="operationMessage"
      action="重新读取并核对"
      :disabled="busy"
      @check="check"
    />
    <p v-if="dirty" class="hint" role="status">有未保存的修改</p>
    <p
      v-if="uncertain.profile || uncertain.password || uncertain.status"
      class="hint"
      role="status"
    >
      此前有操作结果待确认。资料和状态可重新读取核对；密码需让用户尝试新密码。核实后再次提交会要求确认。
    </p>
    <LoadingBlock v-if="loading" /><ErrorState
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
      ><el-divider /><el-form label-position="top" class="detail-form" :disabled="busy"
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
              :value="item" /></el-select
        ></el-form-item>
        <div class="form-actions">
          <el-button
            type="primary"
            :loading="saving"
            :disabled="user.id === 0 || busy"
            @click="save"
            >保存资料</el-button
          >
        </div></el-form
      ><el-divider />
      <el-form v-if="user.id !== 0" label-position="top" class="detail-form" :disabled="busy">
        <h3>重置密码</h3>
        <el-form-item label="新密码"
          ><el-input v-model="password.value" type="password" show-password /></el-form-item
        ><el-form-item label="确认密码"
          ><el-input v-model="password.confirm" type="password" show-password
        /></el-form-item>
        <div class="form-actions">
          <el-button type="warning" :loading="resetting" :disabled="busy" @click="reset"
            >重置密码</el-button
          >
        </div>
      </el-form></el-card
    >
  </div>
</template>

<style scoped>
.hint {
  color: var(--sl-text-muted);
}
.detail-form {
  max-width: 560px;
}
</style>
