import type { LocationQuery } from 'vue-router'

export function positiveId(value: unknown): number | null {
  if (typeof value !== 'string' || !/^\d+$/.test(value)) return null
  const id = Number(value)
  return Number.isSafeInteger(id) && id > 0 ? id : null
}

export function validDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || value.startsWith('0000')) return false
  const date = new Date(`${value}T00:00:00Z`)
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value
}

export function readBillQuery(query: LocationQuery) {
  const text = (key: string) => (typeof query[key] === 'string' ? (query[key] as string) : '')
  const positive = (key: string, fallback: number) => {
    return positiveId(text(key)) ?? fallback
  }
  const status = ['upcoming', 'passed', 'all'].includes(text('time_status'))
    ? text('time_status')
    : 'upcoming'
  let start = validDate(text('start_date')) ? text('start_date') : ''
  let end = validDate(text('end_date')) ? text('end_date') : ''
  // An inverted range cannot be shown in the two linked pickers, so both sides are dropped.
  if (start && end && start > end) start = end = ''
  return {
    time_status: status as 'upcoming' | 'passed' | 'all',
    sort: (['asc', 'desc'].includes(text('sort'))
      ? text('sort')
      : status === 'upcoming'
        ? 'asc'
        : 'desc') as 'asc' | 'desc',
    start_date: start,
    end_date: end,
    q: text('q').trim().slice(0, 128),
    is_valid: ['true', 'false'].includes(text('is_valid')) ? text('is_valid') : '',
    plan_id: positive('plan_id', 0) || undefined,
    page: positive('page', 1),
    page_size: [20, 50, 100].includes(positive('page_size', 20)) ? positive('page_size', 20) : 20,
  }
}

export function dateShortcut(
  kind: 'month' | 'next30' | 'lastMonth',
  timezone: string,
  now = new Date(),
) {
  const options: Intl.DateTimeFormatOptions = {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }
  let parts: Intl.DateTimeFormatPart[]
  try {
    parts = new Intl.DateTimeFormat('en-US', { ...options, timeZone: timezone }).formatToParts(now)
  } catch (error) {
    // An unsupported time zone falls back to the browser zone instead of breaking the page.
    if (!(error instanceof RangeError)) throw error
    parts = new Intl.DateTimeFormat('en-US', options).formatToParts(now)
  }
  const part = (type: string) => Number(parts.find((p) => p.type === type)!.value)
  const year = part('year'),
    month = part('month') - 1,
    day = part('day')
  const iso = (date: Date) => date.toISOString().slice(0, 10)
  if (kind === 'next30')
    return {
      range: [
        iso(new Date(Date.UTC(year, month, day))),
        iso(new Date(Date.UTC(year, month, day + 29))),
      ],
      status: 'upcoming' as const,
    }
  const offset = kind === 'lastMonth' ? -1 : 0
  return {
    range: [
      iso(new Date(Date.UTC(year, month + offset, 1))),
      iso(new Date(Date.UTC(year, month + offset + 1, 0))),
    ],
    status: kind === 'lastMonth' ? ('passed' as const) : ('all' as const),
  }
}
