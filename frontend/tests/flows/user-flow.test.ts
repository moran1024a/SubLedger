import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import { createPlan, deletePlan, updatePlan } from '@/api/plans'
import { listBills, updateBillValidity } from '@/api/bills'
import {
  getNotificationSettings,
  saveNotificationSettings,
  testEmail,
} from '@/api/notifications'
import { getMyLogs } from '@/api/logs'
import { changePassword, updateProfile } from '@/api/users'
import { setForbiddenHandler, setUnauthorizedHandler } from '@/api/client'

const currentUser = {
  id: 1,
  username: 'member',
  role: 'user' as const,
  is_active: true,
  timezone: 'Asia/Shanghai',
  currency_code: 'CNY',
  created_at: '',
  updated_at: '',
}
const plan = {
  id: 2,
  future_bills_rebuilt: false,
  name: '云服务',
  amount: '12.50',
  first_due_date: '2026-07-20',
  cycle_type: 'monthly' as const,
  cycle_days: null,
  is_enabled: true,
  note: null,
  created_at: '',
  updated_at: '',
}
const settings = {
  email_enabled: true,
  smtp_host: 'smtp.example.com',
  smtp_port: 465,
  smtp_security: 'ssl' as const,
  smtp_username: null,
  smtp_password_configured: true,
  sender_email: 'sender@example.com',
  sender_name: null,
  recipient_email: 'receiver@example.com',
  feishu_enabled: false,
  feishu_webhook_configured: false,
  feishu_secret_configured: false,
  advance_enabled: true,
  advance_days: 3,
  advance_time: '09:00:00',
  same_day_enabled: false,
  same_day_time: '08:30:00',
}

function json(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
}

beforeEach(() => {
  setActivePinia(createPinia())
  setUnauthorizedHandler(() => {})
  setForbiddenHandler(() => {})
})

describe('ordinary user flow', () => {
  it('covers login, billing, notification, logs, profile, and password calls', async () => {
    const calls: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method ?? 'GET'
      calls.push(`${method} ${url}`)
      if (url.endsWith('/auth/login')) return json(currentUser)
      if (url.endsWith('/auth/me')) return json(currentUser)
      if (url.endsWith('/plans') && method === 'POST') {
        const payload = JSON.parse(String(init?.body)) as { cycle_type: string }
        return json(
          payload.cycle_type === 'once'
            ? { ...plan, id: 3, name: '域名', cycle_type: 'once' }
            : plan,
          201,
        )
      }
      if (url.endsWith('/plans/2') && method === 'PATCH')
        return json({ ...plan, cycle_type: 'quarterly', future_bills_rebuilt: true })
      if (url.endsWith('/plans/2') && method === 'DELETE')
        return new Response(null, { status: 204 })
      if (url.includes('/bills?'))
        return json({
          items: [{
            id: 5,
            plan_id: 2,
            plan_name: '云服务',
            due_date: '2026-07-20',
            amount: '12.50',
            is_valid: true,
            time_status: 'upcoming',
            cycle_type: 'quarterly',
            cycle_days: null,
          }],
          page: 1,
          page_size: 20,
          total: 1,
        })
      if (url.endsWith('/bills/5/validity')) return json({})
      if (url.endsWith('/me/notification-settings') && method === 'GET') return json(settings)
      if (url.endsWith('/me/notification-settings') && method === 'PUT') return json(settings)
      if (url.endsWith('/me/notification-settings/test-email')) return new Response(null, { status: 204 })
      if (url.endsWith('/me/logs')) return json([])
      if (url.endsWith('/me/profile')) return json({ ...currentUser, username: 'renamed' })
      if (url.endsWith('/me/password')) return new Response(null, { status: 204 })
      throw new Error(`Unexpected request: ${method} ${url}`)
    }))

    const auth = useAuthStore()
    await auth.login('member', 'password')
    const created = await createPlan({
      name: '云服务',
      amount: '12.50',
      first_due_date: '2026-07-20',
      cycle_type: 'monthly',
      cycle_days: null,
      note: null,
    })
    await createPlan({
      name: '域名',
      amount: '80.00',
      first_due_date: '2026-08-01',
      cycle_type: 'once',
      cycle_days: null,
      note: null,
    })
    const updated = await updatePlan(created.id, { cycle_type: 'quarterly' })
    const bills = await listBills({ plan_id: created.id })
    await updateBillValidity(bills.items[0]!.id, false)
    await deletePlan(created.id)
    const loadedSettings = await getNotificationSettings()
    await saveNotificationSettings({ ...loadedSettings, advance_time: '09:00:00', same_day_time: '08:30:00' })
    await testEmail()
    await getMyLogs()
    await updateProfile({ username: 'renamed' })
    await changePassword('old-password', 'new-password')

    expect(updated.future_bills_rebuilt).toBe(true)
    expect(calls.filter((call) => call === 'POST /api/v1/plans')).toHaveLength(2)
    expect(calls).toEqual(expect.arrayContaining([
      'POST /api/v1/auth/login',
      'POST /api/v1/plans',
      'PATCH /api/v1/plans/2',
      'DELETE /api/v1/plans/2',
      'PATCH /api/v1/bills/5/validity',
      'POST /api/v1/me/notification-settings/test-email',
      'PUT /api/v1/me/password',
    ]))
  })
})
