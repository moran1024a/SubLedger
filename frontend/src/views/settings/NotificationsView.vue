<script setup lang="ts">
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/card/style/css'
import 'element-plus/es/components/form/style/css'
import 'element-plus/es/components/form-item/style/css'
import 'element-plus/es/components/input/style/css'
import 'element-plus/es/components/input-number/style/css'
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import 'element-plus/es/components/option/style/css'
import 'element-plus/es/components/radio-button/style/css'
import 'element-plus/es/components/radio-group/style/css'
import 'element-plus/es/components/select/style/css'
import 'element-plus/es/components/switch/style/css'
import 'element-plus/es/components/time-picker/style/css'

import {
  ElButton,
  ElCard,
  ElForm,
  ElFormItem,
  ElInput,
  ElInputNumber,
  ElOption,
  ElRadioButton,
  ElRadioGroup,
  ElSelect,
  ElSwitch,
  ElTimePicker,
} from 'element-plus'
import { useQueryRequest } from '@/composables/useQueryRequest'
import { computed, nextTick, onMounted, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getNotificationSettings,
  saveNotificationSettings,
  testEmail,
  testFeishu,
} from '@/api/notifications'
import { ApiError, type NotificationPayload, type NotificationSettings } from '@/types/api'
import { formatDateTime, timeToApi, timeToMinutes } from '@/utils/format'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import { useViewScope } from '@/composables/useViewScope'
import { asApiError, getFieldErrors, isUncertainWrite, writeErrorMessage } from '@/utils/apiErrors'
import { validateNotificationSettings } from '@/utils/validation'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import OperationFeedback from '@/components/common/OperationFeedback.vue'
import NotificationRecords from '@/components/notifications/NotificationRecords.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import LoadingBlock from '@/components/common/LoadingBlock.vue'
import ErrorState from '@/components/common/ErrorState.vue'

const route = useRoute(),
  router = useRouter(),
  auth = useAuthStore()
const tab = computed({
  get: () => (route.query.tab === 'records' ? 'records' : 'settings'),
  set: (value: string) => {
    void router.replace({ query: { ...route.query, tab: value } })
  },
})
const operationMessage = ref('')
const scope = useViewScope(() => `${auth.sessionVersion}:${auth.user?.id ?? ''}`)
const saveUncertain = ref(false)
const testUncertain = reactive({ email: false, feishu: false })
const reloading = ref(false)
type Channel = 'email' | 'feishu'
const proofs = reactive<
  Record<Channel, { token: string; expires: number; fingerprint: string; message: string }>
>({
  email: { token: '', expires: 0, fingerprint: '', message: '' },
  feishu: { token: '', expires: 0, fingerprint: '', message: '' },
})
const channelBaseline = reactive({ email: '', feishu: '' })
const expiryTimers: Partial<Record<Channel, number>> = {}
onBeforeUnmount(() => {
  Object.values(expiryTimers).forEach(window.clearTimeout)
})
const loading = ref(true)
const saving = ref(false)
const testing = ref<'email' | 'feishu' | null>(null)
const loaded = ref<NotificationSettings | null>(null)
const error = ref<ApiError | null>(null)
const fieldErrors = ref<Record<string, string>>({})
const pageRoot = ref<HTMLElement | null>(null)
async function focusError() {
  await nextTick()
  pageRoot.value?.querySelector<HTMLElement>('.is-error input, .is-error [tabindex="0"]')?.focus()
}
const busy = computed(() => saving.value || testing.value !== null || reloading.value)
const { dirty, confirmDiscard } = useUnsavedChanges()
const form = reactive({
  email_enabled: false,
  smtp_host: '',
  smtp_port: 465 as number | undefined,
  smtp_security: 'ssl' as 'none' | 'starttls' | 'ssl',
  smtp_username: '',
  smtp_password: '',
  sender_email: '',
  sender_name: '',
  recipient_email: '',
  feishu_enabled: false,
  feishu_webhook: '',
  feishu_secret: '',
  advance_enabled: false,
  advance_days: 3,
  advance_time: '09:00' as string | null,
  same_day_enabled: false,
  same_day_time: '08:30' as string | null,
})
const baseline = ref('')
const canTestEmail = computed(() =>
  Boolean(form.smtp_host && form.smtp_port && form.sender_email && form.recipient_email),
)
const canTestFeishu = computed(() =>
  Boolean(form.feishu_webhook.trim() || loaded.value?.feishu_webhook_configured),
)
function snapshot() {
  return JSON.stringify(form)
}
function fingerprint(kind: Channel) {
  return JSON.stringify(
    kind === 'email'
      ? [
          form.smtp_host,
          form.smtp_port,
          form.smtp_security,
          form.smtp_username,
          form.smtp_password,
          form.sender_email,
          form.sender_name,
          form.recipient_email,
        ]
      : [form.feishu_webhook, form.feishu_secret],
  )
}
function needsTest(kind: Channel) {
  return (
    fingerprint(kind) !== channelBaseline[kind] ||
    (form[`${kind}_enabled`] && !loaded.value?.[`${kind}_enabled`])
  )
}
function passed(kind: Channel) {
  return (
    Boolean(proofs[kind].token) &&
    proofs[kind].expires > Date.now() &&
    proofs[kind].fingerprint === fingerprint(kind)
  )
}
const blockedByTest = computed(() =>
  (['email', 'feishu'] as const).filter((kind) => needsTest(kind) && !passed(kind)),
)
function resetProof(kind: Channel) {
  window.clearTimeout(expiryTimers[kind])
  Object.assign(proofs[kind], { token: '', expires: 0, fingerprint: '', message: '' })
}
function expireProofs() {
  for (const kind of ['email', 'feishu'] as const) {
    if (proofs[kind].token && proofs[kind].expires <= Date.now()) {
      const expires = proofs[kind].expires
      resetProof(kind)
      proofs[kind].message =
        `测试结果于 ${formatDateTime(new Date(expires).toISOString(), auth.user?.timezone)} 到期，请重新测试`
    }
  }
}
for (const kind of ['email', 'feishu'] as const)
  watch(
    () => fingerprint(kind),
    () => resetProof(kind),
    { flush: 'sync' },
  )
function statusText(kind: Channel) {
  if (testing.value === kind) return '正在测试当前配置…'
  if (passed(kind))
    return `测试通过，有效至 ${formatDateTime(new Date(proofs[kind].expires).toISOString(), auth.user?.timezone)}（${auth.user?.timezone || '账户时区'}）；修改配置后需重新测试`
  if (proofs[kind].message) return proofs[kind].message
  if (testUncertain[kind]) return '上次测试发送结果待确认，请先检查是否收到消息；再次测试会要求确认'
  return needsTest(kind)
    ? '当前配置尚未测试，保存前请先测试'
    : '使用已保存配置；修改配置或重新启用时需测试'
}
function fill(settings: NotificationSettings) {
  loaded.value = settings
  Object.assign(form, {
    ...settings,
    smtp_host: settings.smtp_host ?? '',
    smtp_port: settings.smtp_port ?? 465,
    smtp_security: settings.smtp_security ?? 'ssl',
    smtp_username: settings.smtp_username ?? '',
    smtp_password: '',
    sender_email: settings.sender_email ?? '',
    sender_name: settings.sender_name ?? '',
    recipient_email: settings.recipient_email ?? '',
    feishu_webhook: '',
    feishu_secret: '',
    advance_time: timeToMinutes(settings.advance_time),
    same_day_time: timeToMinutes(settings.same_day_time),
  })
  baseline.value = snapshot()
  dirty.value = false
  for (const kind of ['email', 'feishu'] as const) {
    channelBaseline[kind] = fingerprint(kind)
    resetProof(kind)
  }
}
watch(
  form,
  () => {
    if (baseline.value) dirty.value = snapshot() !== baseline.value
  },
  { deep: true, flush: 'sync' },
)
const queryRequests = useQueryRequest()
async function load() {
  const signal = queryRequests.next()
  const current = scope.capture()
  loading.value = true
  error.value = null
  try {
    const result = await getNotificationSettings(signal)
    if (signal.aborted || !current()) return
    fill(result)
  } catch (cause) {
    if (signal.aborted || !current()) return
    error.value = asApiError(cause, '无法连接服务器，请检查网络或服务状态。')
  } finally {
    if (!signal.aborted && current()) loading.value = false
  }
}
function payload(forTest?: Channel): NotificationPayload {
  const value: NotificationPayload = {
    settings_version: loaded.value?.settings_version,
    email_enabled: form.email_enabled,
    feishu_enabled: form.feishu_enabled,
    advance_enabled: form.advance_enabled,
    advance_days: form.advance_days,
    advance_time: timeToApi(form.advance_time || '09:00'),
    same_day_enabled: form.same_day_enabled,
    same_day_time: timeToApi(form.same_day_time || '08:30'),
  }
  if (forTest === 'email' || (!forTest && needsTest('email'))) {
    Object.assign(value, {
      smtp_host: form.smtp_host || null,
      smtp_port: form.smtp_port || null,
      smtp_security: form.smtp_security,
      smtp_username: form.smtp_username || null,
      sender_email: form.sender_email || null,
      sender_name: form.sender_name || null,
      recipient_email: form.recipient_email || null,
    })
    if (form.smtp_password.trim()) value.smtp_password = form.smtp_password
    if (!forTest) value.email_verification_token = proofs.email.token
  }
  if (forTest === 'feishu' || (!forTest && needsTest('feishu'))) {
    if (form.feishu_webhook.trim()) value.feishu_webhook = form.feishu_webhook
    if (form.feishu_secret.trim()) value.feishu_secret = form.feishu_secret
    if (!forTest) value.feishu_verification_token = proofs.feishu.token
  }
  return value
}

const saveBlockedReason = computed(() => {
  if (loading.value || reloading.value) return '正在读取通知设置，请稍候'
  if (error.value || !loaded.value) return '通知设置尚未加载成功，请重新加载'
  if (saving.value) return '正在保存通知设置'
  if (testing.value) return '正在测试通知渠道，请等待结果'
  if (
    Object.keys(validateNotificationSettings(form, loaded.value.feishu_webhook_configured)).length
  )
    return '请填写完整并检查通知设置中的必填项'
  if (blockedByTest.value.length)
    return `请先测试通过当前${blockedByTest.value.map((kind) => (kind === 'email' ? '邮件' : '飞书')).join('、')}配置`
  return ''
})
async function confirmRetry(message: string) {
  try {
    await ElMessageBox.confirm(message, '确认再次提交', {
      type: 'warning',
      confirmButtonText: '继续',
      cancelButtonText: '取消',
    })
    return true
  } catch {
    return false
  }
}
async function save() {
  if (loading.value || error.value || !loaded.value || busy.value) return
  expireProofs()
  fieldErrors.value = validateNotificationSettings(form, loaded.value.feishu_webhook_configured)
  if (Object.keys(fieldErrors.value).length) {
    ElMessage.error('请检查通知设置中的必填项')
    void focusError()
    return
  }
  if (blockedByTest.value.length) {
    operationMessage.value = '请先测试通过当前修改的通知渠道'
    return
  }
  saving.value = true
  const current = scope.capture()
  const submitted = payload()
  try {
    if (
      saveUncertain.value &&
      !(await confirmRetry(
        '上次保存结果待确认。读取设置不能确认本次密码或密钥已保存，请先核对公开配置并测试已保存渠道。确定已核实并再次保存吗？',
      ))
    )
      return
    if (!current()) return
    expireProofs()
    if (blockedByTest.value.length) {
      operationMessage.value = '测试结果已过期，请重新测试当前修改的通知渠道'
      return
    }
    const result = await saveNotificationSettings(submitted)
    if (!current()) return
    fill(result)
    saveUncertain.value = false
    operationMessage.value = ''
    ElMessage.success('通知设置已保存')
  } catch (cause) {
    if (!current()) return
    fieldErrors.value = getFieldErrors(cause)
    void focusError()
    saveUncertain.value = isUncertainWrite(cause)
    operationMessage.value = writeErrorMessage(cause)
    if (saveUncertain.value)
      operationMessage.value +=
        '读取设置不能确认密码或密钥是否保存，请核对公开配置并测试已保存渠道。再次保存会要求确认。'
    if (
      cause instanceof ApiError &&
      ['NOTIFICATION_TEST_REQUIRED', 'NOTIFICATION_SETTINGS_CHANGED'].includes(cause.code)
    ) {
      resetProof('email')
      resetProof('feishu')
    }
  } finally {
    if (current()) saving.value = false
  }
}
async function test(kind: Channel) {
  if (loading.value || busy.value || !loaded.value) return
  fieldErrors.value = validateNotificationSettings(
    {
      ...form,
      email_enabled: kind === 'email',
      feishu_enabled: kind === 'feishu',
      advance_enabled: false,
      same_day_enabled: false,
    },
    loaded.value.feishu_webhook_configured,
  )
  if (Object.keys(fieldErrors.value).length) {
    void focusError()
    return
  }
  testing.value = kind
  const current = scope.capture()
  const submitted = fingerprint(kind)
  const submittedPayload = payload(kind)
  try {
    if (
      testUncertain[kind] &&
      !(await confirmRetry(
        '上次测试发送结果待确认，请先检查收件箱或飞书消息。再次测试可能重复发送，确定已核实并继续吗？',
      ))
    )
      return
    if (!current()) return
    resetProof(kind)
    const result = await (kind === 'email' ? testEmail : testFeishu)(submittedPayload)
    if (!current() || fingerprint(kind) !== submitted) return
    const expires = Date.parse(result.expires_at)
    testUncertain[kind] = false
    if (!result.verification_token || !Number.isFinite(expires) || expires <= Date.now()) {
      proofs[kind].message = '服务器返回的测试凭据无效或已过期，请重新测试'
      return
    }
    Object.assign(proofs[kind], {
      token: result.verification_token,
      expires,
      fingerprint: submitted,
      message: '',
    })
    expiryTimers[kind] = window.setTimeout(
      () => {
        if (!current()) return
        resetProof(kind)
        proofs[kind].message =
          `测试结果于 ${formatDateTime(result.expires_at, auth.user?.timezone)} 到期，请重新测试`
      },
      Math.min(2_147_483_647, expires - Date.now()),
    )
    ElMessage.success(
      kind === 'email' ? '邮件服务器已接受测试邮件，请检查收件箱' : '飞书已接受测试消息',
    )
  } catch (cause) {
    if (!current() || fingerprint(kind) !== submitted) return
    testUncertain[kind] = isUncertainWrite(cause)
    const apiError = asApiError(cause)
    proofs[kind].message =
      apiError.status === 429
        ? apiError.code === 'NOTIFICATION_TEST_BUSY'
          ? '测试通道繁忙，请稍后手动再试'
          : '测试请求过于频繁，请等待冷却后手动再试'
        : writeErrorMessage(cause)
    if (testUncertain[kind])
      proofs[kind].message += '请先检查是否收到测试消息，再决定是否继续测试。'
  } finally {
    if (current()) testing.value = null
  }
}
async function reload() {
  if (busy.value) return
  reloading.value = true
  const current = scope.capture()
  try {
    if (dirty.value && !(await confirmDiscard('重新加载成功后会放弃尚未保存的修改，确定继续吗？')))
      return
    if (!current()) return
    await load()
    if (!current() || error.value) return
    if (saveUncertain.value)
      operationMessage.value =
        '已读取服务器当前公开配置；无法确认本次密码或密钥是否保存。请测试已保存渠道并核对，之后再次保存会要求确认。'
    else operationMessage.value = ''
  } finally {
    if (current()) reloading.value = false
  }
}
watch(
  () => `${auth.sessionVersion}:${auth.user?.id ?? ''}`,
  () => {
    queryRequests.cancel()
    for (const kind of ['email', 'feishu'] as const) resetProof(kind)
    saveUncertain.value = false
    testUncertain.email = false
    testUncertain.feishu = false
    saving.value = false
    testing.value = null
    reloading.value = false
    loaded.value = null
    loading.value = true
    baseline.value = ''
    dirty.value = false
    operationMessage.value = ''
    if (auth.user) void load()
  },
)
onMounted(load)
</script>

<template>
  <div ref="pageRoot" class="page-container">
    <PageHeader title="通知设置" description="配置提醒规则和通知渠道"
      ><template #actions
        ><span v-if="tab === 'settings' && saveBlockedReason" class="hint" role="status">{{
          saveBlockedReason
        }}</span
        ><el-button
          v-if="tab === 'settings'"
          type="primary"
          :loading="saving"
          :disabled="Boolean(saveBlockedReason)"
          @click="save"
          >保存设置</el-button
        ></template
      ></PageHeader
    >
    <OperationFeedback
      :message="operationMessage"
      action="重新加载并核实"
      :disabled="busy"
      :loading="reloading"
      @check="reload"
    />
    <p v-if="tab === 'settings' && loaded" class="hint">
      账户时区：{{ auth.user?.timezone }}。{{
        form.advance_enabled
          ? `提前 ${form.advance_days} 天 ${form.advance_time} 提醒`
          : '提前提醒已关闭'
      }}；{{ form.same_day_enabled ? `当日 ${form.same_day_time} 提醒` : '当日提醒已关闭' }}。
    </p>
    <p v-if="tab === 'settings' && blockedByTest.length" class="hint" role="status">
      保存前需测试：{{
        blockedByTest.map((kind) => (kind === 'email' ? '邮件' : '飞书')).join('、')
      }}。测试不会覆盖已保存配置。
    </p>
    <el-radio-group v-model="tab" class="content-card"
      ><el-radio-button value="settings">通知设置</el-radio-button
      ><el-radio-button value="records">通知记录</el-radio-button></el-radio-group
    >
    <NotificationRecords v-if="tab === 'records'" />
    <div v-show="tab === 'settings'">
      <LoadingBlock v-if="loading" /><ErrorState
        v-else-if="error"
        :message="error.message"
        :request-id="error.requestId"
        @retry="reload"
      /><el-form v-else label-position="top" class="notification-form" :disabled="busy"
        ><el-card class="content-card"
          ><template #header>提醒规则</template>
          <div class="rule-grid">
            <el-form-item label="提前提醒"
              ><el-switch v-model="form.advance_enabled" /></el-form-item
            ><el-form-item label="提前天数" :error="fieldErrors.advance_days"
              ><el-input-number
                v-model="form.advance_days"
                :disabled="!form.advance_enabled"
                :min="0"
                :max="365" /></el-form-item
            ><el-form-item label="提前提醒时间" :error="fieldErrors.advance_time"
              ><el-time-picker
                v-model="form.advance_time"
                value-format="HH:mm"
                format="HH:mm"
                :disabled="!form.advance_enabled" /></el-form-item
            ><el-form-item label="当日提醒"
              ><el-switch v-model="form.same_day_enabled" /></el-form-item
            ><el-form-item label="当日提醒时间" :error="fieldErrors.same_day_time"
              ><el-time-picker
                v-model="form.same_day_time"
                value-format="HH:mm"
                format="HH:mm"
                :disabled="!form.same_day_enabled"
            /></el-form-item></div></el-card
        ><el-card class="content-card"
          ><template #header>邮件通知</template
          ><el-form-item label="启用邮件通知"
            ><el-switch v-model="form.email_enabled"
          /></el-form-item>
          <div class="form-grid">
            <el-form-item label="SMTP 主机" :error="fieldErrors.smtp_host"
              ><el-input v-model="form.smtp_host" :disabled="!form.email_enabled" /></el-form-item
            ><el-form-item label="SMTP 端口" :error="fieldErrors.smtp_port"
              ><el-input-number
                v-model="form.smtp_port"
                :disabled="!form.email_enabled"
                :min="1"
                :max="65535" /></el-form-item
            ><el-form-item label="加密方式" :error="fieldErrors.smtp_security"
              ><el-select
                v-model="form.smtp_security"
                :disabled="!form.email_enabled"
                style="width: 100%"
                ><el-option label="无加密" value="none" /><el-option
                  label="STARTTLS"
                  value="starttls" /><el-option
                  label="SSL/TLS"
                  value="ssl" /></el-select></el-form-item
            ><el-form-item label="SMTP 用户名"
              ><el-input
                v-model="form.smtp_username"
                :disabled="!form.email_enabled" /></el-form-item
            ><el-form-item label="SMTP 密码/授权码"
              ><el-input
                v-model="form.smtp_password"
                type="password"
                show-password
                :placeholder="loaded?.smtp_password_configured ? '已配置，留空保持不变' : '未配置'"
                :disabled="!form.email_enabled" /></el-form-item
            ><el-form-item label="发件邮箱" :error="fieldErrors.sender_email"
              ><el-input
                v-model="form.sender_email"
                :disabled="!form.email_enabled" /></el-form-item
            ><el-form-item label="发件人名称"
              ><el-input v-model="form.sender_name" :disabled="!form.email_enabled" /></el-form-item
            ><el-form-item label="收件人邮箱" :error="fieldErrors.recipient_email"
              ><el-input v-model="form.recipient_email" :disabled="!form.email_enabled"
            /></el-form-item>
          </div>
          <el-button
            :disabled="!canTestEmail || busy"
            :loading="testing === 'email'"
            @click="test('email')"
            >测试当前邮件配置</el-button
          >
          <p class="hint" role="status">{{ statusText('email') }}</p>
          <p v-if="!canTestEmail" class="hint">填写主机、端口、发件和收件邮箱后可测试。</p></el-card
        ><el-card class="content-card"
          ><template #header>飞书通知</template
          ><el-form-item label="启用飞书通知"
            ><el-switch v-model="form.feishu_enabled" /></el-form-item
          ><el-form-item label="Webhook" :error="fieldErrors.feishu_webhook"
            ><el-input
              v-model="form.feishu_webhook"
              type="password"
              show-password
              :placeholder="loaded?.feishu_webhook_configured ? '已配置，留空保持不变' : '未配置'"
              :disabled="!form.feishu_enabled" /></el-form-item
          ><el-form-item label="签名密钥"
            ><el-input
              v-model="form.feishu_secret"
              type="password"
              show-password
              :placeholder="loaded?.feishu_secret_configured ? '已配置，留空保持不变' : '未配置'"
              :disabled="!form.feishu_enabled" /></el-form-item
          ><el-button
            :disabled="!canTestFeishu || busy"
            :loading="testing === 'feishu'"
            @click="test('feishu')"
            >测试当前飞书配置</el-button
          >
          <p class="hint" role="status">{{ statusText('feishu') }}</p>
          <p v-if="!canTestFeishu" class="hint">填写 Webhook 后可测试。</p></el-card
        >
        <div class="form-actions notification-actions">
          <p v-if="saveBlockedReason" class="hint" role="status">{{ saveBlockedReason }}</p>
          <p v-else-if="saveUncertain" class="hint" role="status">
            上次保存结果待确认；核实后再次保存会要求确认。
          </p>
          <el-button
            type="primary"
            :loading="saving"
            :disabled="Boolean(saveBlockedReason)"
            @click="save"
            >保存设置</el-button
          >
        </div></el-form
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
.notification-actions {
  flex-wrap: wrap;
}
.notification-actions .hint {
  flex-basis: 100%;
  margin: 0;
}
.notification-form {
  max-width: 720px;
}
.rule-grid,
.form-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--sl-space-4, 16px);
}
.form-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
@media (max-width: 700px) {
  .rule-grid,
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
