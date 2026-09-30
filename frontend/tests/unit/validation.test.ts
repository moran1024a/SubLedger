import { describe, expect, it } from 'vitest'
import {
  isValidCycleDays,
  validateCycleDays,
  validateNotificationSettings,
} from '@/utils/validation'

describe('custom cycle validation', () => {
  it.each(['1', '36500'])('accepts the supported boundary %s', (value) => {
    expect(isValidCycleDays(value)).toBe(true)
    expect(validateCycleDays('custom_days', value)).toBeUndefined()
  })

  it.each(['0', '-1', '1.5', '36501', '999999999999999999999', '1e2', '', '01'])(
    'rejects invalid or unsupported days %s',
    (value) => {
      expect(isValidCycleDays(value)).toBe(false)
      expect(validateCycleDays('custom_days', value)).toBe('请输入 1 到 36500 的整数天数')
    },
  )

  it('does not require custom days for another cycle', () => {
    expect(validateCycleDays('monthly', '')).toBeUndefined()
  })
})

const base = {
  email_enabled: false,
  smtp_host: '',
  smtp_port: 465,
  smtp_security: 'ssl',
  sender_email: '',
  recipient_email: '',
  feishu_enabled: false,
  feishu_webhook: '',
  advance_enabled: false,
  advance_days: 3,
  advance_time: '09:00',
  same_day_enabled: false,
  same_day_time: '08:30',
}

describe('notification validation', () => {
  it('requires enabled reminder times', () => {
    expect(
      validateNotificationSettings({
        ...base,
        advance_enabled: true,
        advance_days: 366,
        advance_time: null,
        same_day_enabled: true,
        same_day_time: null,
      }),
    ).toMatchObject({
      advance_days: expect.any(String),
      advance_time: expect.any(String),
      same_day_time: expect.any(String),
    })
  })

  it('requires the backend email fields when email is enabled', () => {
    expect(validateNotificationSettings({ ...base, email_enabled: true })).toMatchObject({
      smtp_host: expect.any(String),
      sender_email: expect.any(String),
      recipient_email: expect.any(String),
    })
  })

  it('accepts an existing webhook without resubmitting the secret value', () => {
    expect(
      validateNotificationSettings({ ...base, feishu_enabled: true }, true),
    ).not.toHaveProperty('feishu_webhook')
    expect(validateNotificationSettings({ ...base, feishu_enabled: true }, false)).toHaveProperty(
      'feishu_webhook',
    )
  })
})
