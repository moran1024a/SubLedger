import type { CycleType } from '@/types/api'

const currencySymbols: Record<string, string> = {
  CNY: '¥',
  USD: '$',
  EUR: '€',
  GBP: '£',
  JPY: '¥',
  SGD: 'SGD ',
  HKD: 'HK$ ',
}

// Keep decimal comparison exact even when amounts exceed Number's safe range.
export function normalizeAmount(value: string): string {
  const match = /^([+-]?)(\d+)(?:\.(\d+))?$/.exec(value.trim())
  if (!match) return value
  const integer = match[2]!.replace(/^0+(?=\d)/, '')
  const fraction = (match[3] ?? '').replace(/0+$/, '')
  const sign = match[1] === '-' && (integer !== '0' || fraction) ? '-' : ''
  return `${sign}${integer}${fraction ? '.' + fraction : ''}`
}

export function formatMoney(value: string, currencyCode?: string): string {
  const [integer, fraction = '00'] = value.split('.')
  const sign = integer.startsWith('-') ? '-' : ''
  const unsigned = sign ? integer.slice(1) : integer
  const grouped = unsigned.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  const code = currencyCode || 'CNY'
  const symbol = currencySymbols[code] ?? `${code} `
  return `${sign}${symbol}${grouped}.${fraction.padEnd(2, '0').slice(0, 2)}`
}

export function formatDate(value: string): string {
  return value
}

export function formatDateTime(value: string, timezone?: string): string {
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: timezone,
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

export const cycleLimits = { day: 36500, week: 5214, month: 1200, year: 100 }
export function cycleParts(type: CycleType, days?: number | null, interval = 1) {
  if (type === 'monthly') return { type: 'month' as const, interval: 1 }
  if (type === 'quarterly') return { type: 'month' as const, interval: 3 }
  if (type === 'yearly') return { type: 'year' as const, interval: 1 }
  if (type === 'custom_days') return { type: 'day' as const, interval: days ?? 1 }
  return { type, interval }
}
export function formatCycle(type: CycleType, days?: number | null, interval = 1): string {
  if (type === 'once') return '单次'
  if (type === 'monthly') return '每月'
  if (type === 'quarterly') return '每季度'
  if (type === 'yearly') return '每年'
  if (type === 'custom_days') return `每 ${days ?? '?'} 天`
  return `每 ${interval} ${{ day: '天', week: '周', month: '个月', year: '年' }[type]}`
}

export function formatDaysRemaining(days: number): string {
  if (days === 0) return '今天'
  return days === 1 ? '还有 1 天' : `还有 ${days} 天`
}

export function formatFileSize(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

export function timeToMinutes(value?: string | null): string {
  return value?.slice(0, 5) ?? ''
}

export function timeToApi(value?: string | null): string {
  if (!value) return ''
  return value.length === 5 ? `${value}:00` : value
}
