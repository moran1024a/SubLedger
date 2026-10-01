export type UserRole = 'admin' | 'user'
export type CycleType =
  'once' | 'day' | 'week' | 'month' | 'year' | 'monthly' | 'quarterly' | 'yearly' | 'custom_days'
export type BillTimeStatus = 'upcoming' | 'passed'
export type MoneyString = string

export interface CurrentUser {
  id: number
  username: string
  role: UserRole
  is_active: boolean
  timezone: string
  currency_code: string
  created_at: string
  updated_at: string
}

export interface BillPlan {
  id: number
  future_bills_rebuilt: boolean
  name: string
  amount: MoneyString
  first_due_date: string
  cycle_type: CycleType
  cycle_interval?: number
  cycle_days: number | null
  is_enabled: boolean
  note: string | null
  created_at: string
  updated_at: string
}

export interface BillPlanPayload {
  name: string
  amount: string
  first_due_date: string
  cycle_type: CycleType
  cycle_interval?: number
  cycle_days?: number | null
  note?: string | null
}

export type BillPlanPatch = Partial<BillPlanPayload>

export interface BillOccurrence {
  plan_status?: 'enabled' | 'disabled' | 'deleted'
  id: number
  plan_id: number
  plan_name: string
  due_date: string
  amount: MoneyString
  is_valid: boolean
  time_status: BillTimeStatus
  cycle_type: CycleType
  cycle_interval?: number
  cycle_days: number | null
}

export interface BillOccurrencePage {
  items: BillOccurrence[]
  page: number
  page_size: number
  total: number
}

export interface StatisticsBucket {
  amount: MoneyString
  count: number
}

export interface StatisticsResponse {
  date: string
  today: StatisticsBucket
  current_month: StatisticsBucket
  averages: { monthly: MoneyString; daily: MoneyString }
  current_year: StatisticsBucket
  next_bill: {
    bill_id: number | null
    name: string
    amount: MoneyString
    due_date: string
    days_remaining: number
  } | null
}

export interface NotificationSettings {
  settings_version?: string
  email_enabled: boolean
  smtp_host: string | null
  smtp_port: number | null
  smtp_security: 'none' | 'starttls' | 'ssl' | null
  smtp_username: string | null
  smtp_password_configured: boolean
  sender_email: string | null
  sender_name: string | null
  recipient_email: string | null
  feishu_enabled: boolean
  feishu_webhook_configured: boolean
  feishu_secret_configured: boolean
  advance_enabled: boolean
  advance_days: number
  advance_time: string
  same_day_enabled: boolean
  same_day_time: string
}

export interface NotificationPayload {
  settings_version?: string
  email_verification_token?: string
  feishu_verification_token?: string
  email_enabled: boolean
  smtp_host?: string | null
  smtp_port?: number | null
  smtp_security?: 'none' | 'starttls' | 'ssl' | null
  smtp_username?: string | null
  smtp_password?: string
  sender_email?: string | null
  sender_name?: string | null
  recipient_email?: string | null
  feishu_enabled: boolean
  feishu_webhook?: string
  feishu_secret?: string
  advance_enabled: boolean
  advance_days: number
  advance_time: string
  same_day_enabled: boolean
  same_day_time: string
}

export interface LogFile {
  date: string
  filename: string
  size: number
  modified_at: string
}

export interface AdminSummary {
  total_users: number
  active_users: number
  inactive_users: number
}

export interface HealthResponse {
  status: 'ok' | 'degraded'
  application: 'ok'
  database: 'ok' | 'error'
  scheduler: 'ok' | 'disabled' | 'error'
}

export interface FieldError {
  field: string
  message: string
}

export interface ApiErrorBody {
  code?: string
  message?: string
  request_id?: string
  errors?: FieldError[]
}

export interface ApiErrorOptions {
  status: number
  code: string
  message: string
  requestId?: string
  fields?: FieldError[]
}

export class ApiError extends Error {
  status: number
  code: string
  requestId?: string
  fields: FieldError[]

  constructor(options: ApiErrorOptions) {
    super(options.message)
    this.name = 'ApiError'
    this.status = options.status
    this.code = options.code
    this.requestId = options.requestId
    this.fields = options.fields ?? []
  }
}

export interface UserPage {
  items: CurrentUser[]
  page: number
  page_size: number
  total: number
}

export interface RuntimeTask {
  id: string
  name: string
  status: 'waiting' | 'running' | 'ok' | 'warning' | 'error' | 'disabled'
  next_run_at: string | null
  last_started_at: string | null
  last_finished_at: string | null
  last_success_at: string | null
  duration_seconds: number | null
  consecutive_failures: number
  last_error: string | null
  counts: Record<string, number> | null
}
export interface RuntimeResponse {
  status: 'ok' | 'error' | 'disabled'
  tasks: RuntimeTask[]
}
export type NotificationStatus =
  'pending' | 'retry_wait' | 'sent' | 'failed' | 'unknown' | 'expired'
export interface NotificationRecord {
  id: number
  plan_id: number
  plan_name: string
  due_date: string
  channel: 'email' | 'feishu'
  reminder_type: 'advance' | 'same_day'
  status: NotificationStatus
  scheduled_at: string
  sent_at: string | null
  attempt_count: number
  last_attempt_at: string | null
  next_retry_at: string | null
  error_code: string | null
  error_message: string | null
}
export interface NotificationRecordPage {
  items: NotificationRecord[]
  page: number
  page_size: number
  total: number
}
