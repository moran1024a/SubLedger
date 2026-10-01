<script setup lang="ts">
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/card/style/css'
import 'element-plus/es/components/form/style/css'
import 'element-plus/es/components/form-item/style/css'
import 'element-plus/es/components/input/style/css'
import 'element-plus/es/components/input-number/style/css'
import 'element-plus/es/components/message/style/css'
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
import { ElMessage } from 'element-plus'
import {
  getNotificationSettings,
  saveNotificationSettings,
  testEmail,
  testFeishu,
} from '@/api/notifications'
import { ApiError, type NotificationPayload, type NotificationSettings } from '@/types/api'
import { timeToApi, timeToMinutes } from '@/utils/format'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import { asApiError, getFieldErrors, writeErrorMessage } from '@/utils/apiErrors'
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
const { dirty } = useUnsavedChanges()
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
for (const kind of ['email', 'feishu'] as const)
  watch(
    () => fingerprint(kind),
    () => resetProof(kind),
    { flush: 'sync' },
  )
function statusText(kind: Channel) {
  if (testing.value === kind) return '正在测试当前配置…'
  if (passed(kind)) return '测试通过，10 分钟内可保存；修改配置后需重新测试'
  if (proofs[kind].message) return proofs[kind].message
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
  nextTick(() => {
    baseline.value = snapshot()
    dirty.value = false
    for (const kind of ['email', 'feishu'] as const) {
      channelBaseline[kind] = fingerprint(kind)
      resetProof(kind)
    }
  })
}
watch(
  form,
  () => {
    if (baseline.value) dirty.value = snapshot() !== baseline.value
  },
  { deep: true },
)
const queryRequests = useQueryRequest()
async function load() {
  const signal = queryRequests.next()
  loading.value = true
  error.value = null
  try {
    const result = await getNotificationSettings(signal)
    if (signal.aborted) return
    fill(result)
  } catch (cause) {
    if (signal.aborted) return
    error.value = asApiError(cause, '无法连接服务器，请检查网络或服务状态。')
  } finally {
    if (!signal.aborted) loading.value = false
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

async function save() {
  if (loading.value || error.value || !loaded.value || saving.value || testing.value) return
  fieldErrors.value = validateNotificationSettings(form, loaded.value?.feishu_webhook_configured)
  if (Object.keys(fieldErrors.value).length) {
    ElMessage.error('请检查通知设置中的必填项')
    void focusError()
    return
  }
  if (blockedByTest.value.length) {
    operationMessage.value = '请先测试通过当前修改的通知渠道'
    return
  }
  operationMessage.value = ''
  saving.value = true
  try {
    fill(await saveNotificationSettings(payload()))
    ElMessage.success('通知设置已保存')
  } catch (cause) {
    fieldErrors.value = getFieldErrors(cause)
    void focusError()
    operationMessage.value = writeErrorMessage(cause)
    if (
      cause instanceof ApiError &&
      ['NOTIFICATION_TEST_REQUIRED', 'NOTIFICATION_SETTINGS_CHANGED'].includes(cause.code)
    ) {
      resetProof('email')
      resetProof('feishu')
    }
  } finally {
    saving.value = false
  }
}
async function test(kind: Channel) {
  if (saving.value || testing.value || !loaded.value) return
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
  resetProof(kind)
  const submitted = fingerprint(kind)
  testing.value = kind
  try {
    const result = await (kind === 'email' ? testEmail : testFeishu)(payload(kind))
    if (fingerprint(kind) !== submitted) return
    Object.assign(proofs[kind], {
      token: result.verification_token,
      expires: Date.parse(result.expires_at),
      fingerprint: submitted,
      message: '',
    })
    expiryTimers[kind] = window.setTimeout(
      () => {
        resetProof(kind)
        proofs[kind].message = '测试结果已过期，请重新测试'
      },
      Math.max(0, proofs[kind].expires - Date.now()),
    )
    ElMessage.success(
      kind === 'email' ? '邮件服务器已接受测试邮件，请检查收件箱' : '飞书已接受测试消息',
    )
  } catch (cause) {
    if (fingerprint(kind) === submitted) proofs[kind].message = writeErrorMessage(cause)
  } finally {
    testing.value = null
  }
}
async function reload() {
  if (dirty.value && !window.confirm('重新加载会放弃尚未保存的修改，确定继续吗？')) return
  await load()
}
onMounted(load)
</script>

<template>
  <div ref="pageRoot" class="page-container">
    <PageHeader title="通知设置" description="配置提醒规则和通知渠道"
      ><template #actions
        ><el-button
          v-if="tab === 'settings'"
          type="primary"
          :loading="saving"
          :disabled="
            loading ||
            error !== null ||
            loaded === null ||
            testing !== null ||
            blockedByTest.length > 0
          "
          @click="save"
          >保存设置</el-button
        ></template
      ></PageHeader
    >
    <OperationFeedback :message="operationMessage" action="重新加载并核实" @check="reload" />
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
        @retry="load"
      /><el-form
        v-else
        label-position="top"
        class="notification-form"
        :disabled="saving || testing !== null"
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
            :disabled="!canTestEmail || saving || testing !== null"
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
            :disabled="!canTestFeishu || saving || testing !== null"
            :loading="testing === 'feishu'"
            @click="test('feishu')"
            >测试当前飞书配置</el-button
          >
          <p class="hint" role="status">{{ statusText('feishu') }}</p>
          <p v-if="!canTestFeishu" class="hint">填写 Webhook 后可测试。</p></el-card
        ></el-form
      >
    </div>
  </div>
</template>

<style scoped>
.hint {
  color: #6b7280;
  font-size: 13px;
  line-height: 1.7;
}
.notification-form {
  max-width: 720px;
}
.rule-grid,
.form-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
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
