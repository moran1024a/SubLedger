<script setup lang="ts">
import 'element-plus/es/components/alert/style/css'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/card/style/css'
import 'element-plus/es/components/form/style/css'
import 'element-plus/es/components/form-item/style/css'
import 'element-plus/es/components/input/style/css'
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import 'element-plus/es/components/option/style/css'
import 'element-plus/es/components/select/style/css'

import {
  ElAlert,
  ElButton,
  ElCard,
  ElForm,
  ElFormItem,
  ElInput,
  ElOption,
  ElSelect,
} from 'element-plus'
import { timezones, currencies } from '@/utils/profileOptions'
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { changePassword, updateProfile } from '@/api/users'
import { getCurrentUser } from '@/api/auth'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import { useViewScope } from '@/composables/useViewScope'
import { useAuthStore } from '@/stores/auth'
import PageHeader from '@/components/common/PageHeader.vue'
import OperationFeedback from '@/components/common/OperationFeedback.vue'
import { asApiError, getFieldErrors, isUncertainWrite, writeErrorMessage } from '@/utils/apiErrors'
import { useRouter } from 'vue-router'
import { isValidCurrencyCode } from '@/utils/validation'

const auth = useAuthStore()
const router = useRouter()
const saving = ref(false)
const passwordSaving = ref(false)
const checking = ref(false)
const busy = computed(() => saving.value || passwordSaving.value || checking.value)
const passwordError = ref('')
const { dirty } = useUnsavedChanges()
const baseline = ref('')
const profileUncertain = ref(false)
const passwordUncertain = ref(false)
const profileError = ref('')
const profileFieldErrors = ref<Record<string, string>>({})
const passwordFieldErrors = ref<Record<string, string>>({})
const pageRoot = ref<HTMLElement | null>(null)
const profile = reactive({ username: '', timezone: '', currency_code: '' })
const password = reactive({ current: '', next: '', confirm: '' })
const scope = useViewScope(() => `${auth.sessionVersion}:${auth.user?.id ?? ''}`)
const profileDirty = computed(
  () => Boolean(baseline.value) && JSON.stringify(profile) !== baseline.value,
)
watch(
  () => `${auth.sessionVersion}:${auth.user?.id ?? ''}`,
  () => {
    saving.value = false
    passwordSaving.value = false
    checking.value = false
    if (auth.user) {
      Object.assign(profile, {
        username: auth.user.username,
        timezone: auth.user.timezone,
        currency_code: auth.user.currency_code,
      })
    } else Object.assign(profile, { username: '', timezone: '', currency_code: '' })
    Object.assign(password, { current: '', next: '', confirm: '' })
    profileError.value = ''
    passwordError.value = ''
    profileFieldErrors.value = {}
    passwordFieldErrors.value = {}
    profileUncertain.value = false
    passwordUncertain.value = false
    baseline.value = JSON.stringify(profile)
  },
  { immediate: true, flush: 'sync' },
)
watch(
  [profile, password, baseline],
  () => {
    dirty.value =
      Boolean(baseline.value) &&
      (JSON.stringify(profile) !== baseline.value ||
        Boolean(password.current || password.next || password.confirm))
  },
  { deep: true, flush: 'sync' },
)
async function confirm(message: string) {
  try {
    await ElMessageBox.confirm(message, '确认操作', {
      type: 'warning',
      confirmButtonText: '继续',
      cancelButtonText: '取消',
    })
    return true
  } catch {
    return false
  }
}
function setCurrency(value: unknown) {
  profile.currency_code = String(value ?? '')
    .trim()
    .toUpperCase()
}
async function focusError() {
  const current = scope.capture()
  await nextTick()
  if (current()) pageRoot.value?.querySelector<HTMLElement>('.is-error input')?.focus()
}
async function saveProfile() {
  if (busy.value || !auth.user) return
  if (!profileUncertain.value) profileError.value = ''
  profileFieldErrors.value = {}
  if (!profile.username.trim()) {
    profileError.value = '用户名不能为空'
    return
  }
  if (!isValidCurrencyCode(profile.currency_code)) {
    profileFieldErrors.value = { currency_code: '货币代码需为 3 到 8 位大写字母' }
    void focusError()
    return
  }
  saving.value = true
  const current = scope.capture()
  const version = auth.sessionVersion
  try {
    if (
      profileUncertain.value &&
      !(await confirm('上次保存结果待确认。请先重新读取资料并核对，确定已核实并再次保存吗？'))
    )
      return
    if (!current()) return
    const updated = await updateProfile({
      username: profile.username.trim(),
      timezone: profile.timezone,
      currency_code: profile.currency_code,
    })
    if (!current() || !auth.setUser(updated, version)) return
    Object.assign(profile, {
      username: updated.username,
      timezone: updated.timezone,
      currency_code: updated.currency_code,
    })
    baseline.value = JSON.stringify(profile)
    dirty.value = Boolean(password.current || password.next || password.confirm)
    profileUncertain.value = false
    profileError.value = ''
    ElMessage.success('个人资料已保存')
  } catch (cause) {
    if (!current()) return
    profileFieldErrors.value = getFieldErrors(cause)
    profileUncertain.value = isUncertainWrite(cause)
    profileError.value = writeErrorMessage(cause)
    void focusError()
  } finally {
    if (current()) saving.value = false
  }
}
async function savePassword() {
  if (busy.value || !auth.user) return
  if (!passwordUncertain.value) passwordError.value = ''
  const errors: Record<string, string> = {}
  if (!password.current) errors.current = '请输入当前密码'
  if (password.next.length < 8) errors.next = '新密码至少 8 个字符'
  else if (password.next !== password.confirm) errors.confirm = '两次新密码不一致'
  passwordFieldErrors.value = errors
  if (Object.keys(errors).length) {
    void focusError()
    return
  }
  passwordSaving.value = true
  const current = scope.capture()
  try {
    if (
      profileDirty.value &&
      !(await confirm(
        '个人资料有未保存的修改。密码修改成功后将退出登录，这些资料修改会丢失。确定继续修改密码吗？',
      ))
    )
      return
    if (!current()) return
    if (
      passwordUncertain.value &&
      !(await confirm(
        '上次密码修改结果待确认。请先在隐私窗口登录页尝试新密码；无法登录时可联系管理员重置。确定已核实并再次修改吗？',
      ))
    )
      return
    if (!current()) return
    await changePassword(password.current, password.next)
    if (!current()) return
    auth.clear()
    ElMessage.success('密码已修改，请重新登录')
    await router.replace('/login')
  } catch (cause) {
    if (!current()) return
    const fields = getFieldErrors(cause)
    passwordFieldErrors.value = Object.fromEntries(
      Object.entries({ current: fields.current_password, next: fields.new_password }).filter(
        ([, message]) => message,
      ),
    )
    passwordUncertain.value = isUncertainWrite(cause)
    passwordError.value = writeErrorMessage(cause)
    if (Object.keys(passwordFieldErrors.value).length) void focusError()
  } finally {
    if (current()) passwordSaving.value = false
  }
}
async function checkProfile() {
  if (busy.value || !auth.user) return
  checking.value = true
  const current = scope.capture()
  const version = auth.sessionVersion
  try {
    const server = await getCurrentUser()
    if (!current() || !auth.setUser(server, version)) return
    profileError.value = `已读取当前资料：${server.username} / ${server.timezone} / ${server.currency_code}。草稿已保留，请核对后再保存。`
  } catch (cause) {
    if (current()) profileError.value = asApiError(cause).message
  } finally {
    if (current()) checking.value = false
  }
}
</script>

<template>
  <div ref="pageRoot" class="page-container">
    <PageHeader title="个人设置" description="修改用户名、时区、默认货币和密码" />
    <p v-if="dirty" class="hint" role="status">有未保存的修改</p>
    <div class="settings-grid">
      <el-card
        ><template #header>基本资料</template
        ><el-form label-position="top" :disabled="busy"
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
            ><el-select
              :model-value="profile.currency_code"
              filterable
              allow-create
              default-first-option
              style="width: 100%"
              @update:model-value="setCurrency"
              ><el-option
                v-for="currency in currencies"
                :key="currency"
                :label="currency"
                :value="currency" /></el-select
            ><span class="field-help">可直接输入其他 3 到 8 位代码</span></el-form-item
          >
          <p class="hint">时区影响账单日期和提醒时间；默认货币仅改变显示，不进行汇率换算。</p>
          <OperationFeedback
            :message="profileError"
            :action="profileUncertain ? '重新读取并核对资料' : undefined"
            :disabled="busy"
            :loading="checking"
            @check="checkProfile"
          />
          <p v-if="profileUncertain" class="hint" role="status">
            上次资料保存结果待确认，请重新读取并核对；再次保存会要求确认。
          </p>
          <div class="form-actions">
            <el-button
              type="primary"
              :loading="saving"
              :disabled="busy && !saving"
              @click="saveProfile"
              >保存资料</el-button
            >
          </div></el-form
        ></el-card
      ><el-card
        ><template #header>修改密码</template
        ><el-form label-position="top" :disabled="busy"
          ><el-form-item label="当前密码" :error="passwordFieldErrors.current"
            ><el-input
              v-model="password.current"
              type="password"
              show-password
              autocomplete="current-password" /></el-form-item
          ><el-form-item label="新密码" :error="passwordFieldErrors.next"
            ><el-input
              v-model="password.next"
              type="password"
              show-password
              autocomplete="new-password" /></el-form-item
          ><el-form-item label="确认新密码" :error="passwordFieldErrors.confirm"
            ><el-input
              v-model="password.confirm"
              type="password"
              show-password
              autocomplete="new-password" /></el-form-item
          ><el-alert v-if="passwordError" :title="passwordError" type="warning" :closable="false" />
          <p v-if="passwordUncertain" class="hint" role="status">
            请在隐私窗口尝试用新密码登录，或联系管理员重置。确认结果后再次修改会要求明确确认。
          </p>
          <div class="form-actions">
            <el-button
              type="primary"
              :loading="passwordSaving"
              :disabled="busy && !passwordSaving"
              @click="savePassword"
              >修改密码</el-button
            >
          </div></el-form
        ></el-card
      >
    </div>
  </div>
</template>

<style scoped>
.hint {
  color: var(--sl-text-muted);
  font-size: 13px;
  line-height: 1.7;
}
.field-help {
  display: block;
  width: 100%;
  color: var(--sl-text-muted);
  font-size: var(--sl-font-size-xs);
  line-height: 1.5;
  margin-top: var(--sl-space-1);
}
.settings-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--sl-space-5, 20px);
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
