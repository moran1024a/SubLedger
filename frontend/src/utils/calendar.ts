// Calendar arithmetic uses UTC dates; "today" comes from the account timezone.
export const MIN_CALENDAR_MONTH = '1000-01'
export const MAX_CALENDAR_MONTH = '9999-12'

export function shiftDay(day: string, offset: number): string | null {
  const value = new Date(`${day}T00:00:00Z`)
  value.setUTCDate(value.getUTCDate() + offset)
  if (value.getUTCFullYear() < 1000 || value.getUTCFullYear() > 9999) return null
  return value.toISOString().slice(0, 10)
}

export function shiftMonth(month: string, offset: number): string | null {
  const value = new Date(`${month}-01T00:00:00Z`)
  value.setUTCMonth(value.getUTCMonth() + offset)
  if (value.getUTCFullYear() < 1000 || value.getUTCFullYear() > 9999) return null
  return value.toISOString().slice(0, 7)
}

export function monthCells(month: string) {
  const first = `${month}-01`
  const weekday = (new Date(`${first}T00:00:00Z`).getUTCDay() + 6) % 7
  return Array.from({ length: 42 }, (_, index) => shiftDay(first, index - weekday))
}

export function dayInMonth(day: string, month: string): string {
  const end = new Date(`${month}-01T00:00:00Z`)
  end.setUTCMonth(end.getUTCMonth() + 1)
  end.setUTCDate(0)
  return `${month}-${String(Math.min(Number(day.slice(8)), end.getUTCDate())).padStart(2, '0')}`
}
