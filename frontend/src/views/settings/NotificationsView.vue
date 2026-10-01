<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
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
import { asApiError, getFieldErrors } from '@/utils/apiErrors'
import { validateNotificationSettings } from '@/utils/validation'
import PageHeader from '@/components/common/PageHeader.vue'
import LoadingBlock from '@/components/common/LoadingBlock.vue'
import ErrorState from '@/components/common/ErrorState.vue'

const loading = ref(true)
const saving = ref(false)
const testing = ref<'email' | 'feishu' | null>(null)
const loaded = ref<NotificationSettings | null>(null)
const error = ref<ApiError | null>(null)
const fieldErrors = ref<Record<string, string>>({})
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
const canTestEmail = computed(
  () =>
    Boolean(loaded.value?.smtp_host) &&
    Boolean(loaded.value?.smtp_port) &&
    Boolean(loaded.value?.smtp_security) &&
    Boolean(loaded.value?.sender_email) &&
    Boolean(loaded.value?.recipient_email),
)
const canTestFeishu = computed(() => Boolean(loaded.value?.feishu_webhook_configured))
function snapshot() {
  return JSON.stringify({
    ...form,
    smtp_password: Boolean(form.smtp_password),
    feishu_webhook: Boolean(form.feishu_webhook),
    feishu_secret: Boolean(form.feishu_secret),
  })
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
  })
}
watch(
  form,
  () => {
    if (baseline.value) dirty.value = snapshot() !== baseline.value
  },
  { deep: true },
)
async function load() {
  loading.value = true
  error.value = null
  try {
    fill(await getNotificationSettings())
  } catch (cause) {
    error.value = asApiError(cause, '无法连接服务器，请检查网络或服务状态。')
  } finally {
    loading.value = false
  }
}
function payload(): NotificationPayload {
  const value: NotificationPayload = {
    email_enabled: form.email_enabled,
    feishu_enabled: form.feishu_enabled,
    advance_enabled: form.advance_enabled,
    advance_days: form.advance_days,
    advance_time: timeToApi(form.advance_time || '09:00'),
    same_day_enabled: form.same_day_enabled,
    same_day_time: timeToApi(form.same_day_time || '08:30'),
    smtp_host: form.smtp_host || null,
    smtp_port: form.smtp_port || null,
    smtp_security: form.smtp_security,
    smtp_username: form.smtp_username || null,
    sender_email: form.sender_email || null,
    sender_name: form.sender_name || null,
    recipient_email: form.recipient_email || null,
  }
  if (form.smtp_password.trim()) value.smtp_password = form.smtp_password
  if (form.feishu_webhook.trim()) value.feishu_webhook = form.feishu_webhook
  if (form.feishu_secret.trim()) value.feishu_secret = form.feishu_secret
  return value
}
async function save() {
  if (loading.value || error.value || !loaded.value || saving.value || testing.value) return
  fieldErrors.value = validateNotificationSettings(form, loaded.value?.feishu_webhook_configured)
  if (Object.keys(fieldErrors.value).length) {
    ElMessage.error('请检查通知设置中的必填项')
    return
  }
  saving.value = true
  try {
    fill(await saveNotificationSettings(payload()))
    ElMessage.success('通知设置已保存')
  } catch (cause) {
    fieldErrors.value = getFieldErrors(cause)
    ElMessage.error(cause instanceof ApiError ? cause.message : '保存失败')
  } finally {
    saving.value = false
  }
}
async function test(kind: 'email' | 'feishu') {
  if (saving.value || testing.value) return
  testing.value = kind
  try {
    if (kind === 'email') await testEmail()
    else await testFeishu()
    ElMessage.success(kind === 'email' ? '测试邮件已发送' : '测试飞书消息已发送')
  } catch (cause) {
    ElMessage.error(cause instanceof ApiError ? cause.message : '测试发送失败')
  } finally {
    testing.value = null
  }
}
onMounted(load)
</script>

<template>
  <div class="page-container">
    <PageHeader title="通知设置" description="配置提醒规则和通知渠道"
      ><template #actions
        ><el-button
          type="primary"
          :loading="saving"
          :disabled="loading || error !== null || loaded === null || testing !== null"
          @click="save"
          >保存设置</el-button
        ></template
      ></PageHeader
    ><LoadingBlock v-if="loading" /><ErrorState
      v-else-if="error"
      :message="error.message"
      :request-id="error.requestId"
      @retry="load"
    /><el-form v-else label-position="top" class="notification-form"
      ><el-card class="content-card"
        ><template #header>提醒规则</template>
        <div class="rule-grid">
          <el-form-item label="提前提醒"><el-switch v-model="form.advance_enabled" /></el-form-item
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
            ><el-input v-model="form.smtp_username" :disabled="!form.email_enabled" /></el-form-item
          ><el-form-item label="SMTP 密码/授权码"
            ><el-input
              v-model="form.smtp_password"
              type="password"
              show-password
              :placeholder="loaded?.smtp_password_configured ? '已配置，留空保持不变' : '未配置'"
              :disabled="!form.email_enabled" /></el-form-item
          ><el-form-item label="发件邮箱" :error="fieldErrors.sender_email"
            ><el-input v-model="form.sender_email" :disabled="!form.email_enabled" /></el-form-item
          ><el-form-item label="发件人名称"
            ><el-input v-model="form.sender_name" :disabled="!form.email_enabled" /></el-form-item
          ><el-form-item label="收件人邮箱" :error="fieldErrors.recipient_email"
            ><el-input v-model="form.recipient_email" :disabled="!form.email_enabled"
          /></el-form-item>
        </div>
        <el-button
          :disabled="!canTestEmail || dirty || saving || testing !== null"
          :loading="testing === 'email'"
          @click="test('email')"
          >测试邮件</el-button
        ></el-card
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
          :disabled="!canTestFeishu || dirty || saving || testing !== null"
          :loading="testing === 'feishu'"
          @click="test('feishu')"
          >测试飞书</el-button
        ></el-card
      ></el-form
    >
  </div>
</template>

<style scoped>
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
