import type { CycleType } from '@/types/api'

export function isValidAmount(value: string): boolean {
  return (
    /^(?=\d{1,12}(?:\.\d{1,2})?$)(?!.*e)[0-9]+(?:\.[0-9]{1,2})?$/.test(value) && Number(value) > 0
  )
}

export function isValidCycleDays(value: string): boolean {
  return /^[1-9]\d*$/.test(value) && Number(value) <= 36500
}

export function validateCycleDays(type: CycleType, value: string): string | undefined {
  if (type === 'custom_days' && !isValidCycleDays(value)) return '请输入 1 到 36500 的整数天数'
  return undefined
}

export function passwordsMatch(password: string, confirmation: string): boolean {
  return password.length > 0 && password === confirmation
}

interface NotificationFormValues {
  email_enabled: boolean
  smtp_host: string
  smtp_port?: number
  smtp_security: string
  sender_email: string
  recipient_email: string
  feishu_enabled: boolean
  feishu_webhook: string
  advance_enabled: boolean
  advance_days: number
  advance_time?: string | null
  same_day_enabled: boolean
  same_day_time?: string | null
}

export function validateNotificationSettings(
  form: NotificationFormValues,
  webhookConfigured = false,
): Record<string, string> {
  const errors: Record<string, string> = {}
  if (form.advance_enabled) {
    if (!Number.isInteger(form.advance_days) || form.advance_days < 0 || form.advance_days > 365)
      errors.advance_days = '提前天数必须是 0 到 365 的整数'
    if (!form.advance_time) errors.advance_time = '请选择提前提醒时间'
  }
  if (form.same_day_enabled && !form.same_day_time) errors.same_day_time = '请选择当日提醒时间'
  if (form.email_enabled) {
    if (!form.smtp_host.trim()) errors.smtp_host = '请输入 SMTP 主机'
    if (!form.smtp_port) errors.smtp_port = '请输入 SMTP 端口'
    if (!form.smtp_security) errors.smtp_security = '请选择加密方式'
    if (!form.sender_email.trim()) errors.sender_email = '请输入发件邮箱'
    if (!form.recipient_email.trim()) errors.recipient_email = '请输入收件人邮箱'
  }
  if (form.feishu_enabled && !webhookConfigured && !form.feishu_webhook.trim())
    errors.feishu_webhook = '请输入飞书 Webhook'
  return errors
}
