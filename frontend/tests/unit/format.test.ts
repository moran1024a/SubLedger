import { describe, expect, it } from 'vitest'
import {
  formatCycle,
  formatDate,
  formatDaysRemaining,
  formatMoney,
  normalizeAmount,
  timeToApi,
  timeToMinutes,
} from '@/utils/format'
import { isValidAmount, isValidCycleDays } from '@/utils/validation'

describe('format helpers', () => {
  it('formats money without floating point conversion', () => {
    expect(formatMoney('1288.00', 'CNY')).toBe('¥1,288.00')
    expect(formatMoney('68', 'SGD')).toBe('SGD 68.00')
  })

  it('compares decimal representations exactly without rounding large values', () => {
    expect(normalizeAmount('12.50')).toBe(normalizeAmount('12.5'))
    expect(normalizeAmount('00012.5000')).toBe('12.5')
    expect(normalizeAmount('-0.00')).toBe('0')
    expect(normalizeAmount('9007199254740993.01')).not.toBe(normalizeAmount('9007199254740993.02'))
    expect(normalizeAmount('1e2')).toBe('1e2')
  })

  it('formats cycles and remaining days', () => {
    expect(formatCycle('custom_days', 10)).toBe('每 10 天')
    expect(formatDaysRemaining(0)).toBe('今天')
    expect(formatDaysRemaining(1)).toBe('还有 1 天')
    expect(formatDaysRemaining(2)).toBe('还有 2 天')
  })

  it('keeps pure dates unchanged', () => {
    expect(formatDate('2026-07-20')).toBe('2026-07-20')
  })

  it('normalizes notification time and tolerates empty controls', () => {
    expect(timeToMinutes('09:00:00')).toBe('09:00')
    expect(timeToMinutes(null)).toBe('')
    expect(timeToApi('09:00')).toBe('09:00:00')
    expect(timeToApi(null)).toBe('')
  })
})

describe('validation helpers', () => {
  it('accepts only positive decimal amounts with two places', () => {
    expect(isValidAmount('12.50')).toBe(true)
    expect(isValidAmount('0')).toBe(false)
    expect(isValidAmount('1e2')).toBe(false)
    expect(isValidAmount('12.345')).toBe(false)
  })

  it('validates cycle days and passwords', () => {
    expect(isValidCycleDays('3')).toBe(true)
    expect(isValidCycleDays('0')).toBe(false)
  })
})

it('formats generalized calendar cycles, including two and three years', () => {
  expect(formatCycle('year', null, 2)).toBe('每 2 年')
  expect(formatCycle('year', null, 3)).toBe('每 3 年')
  expect(formatCycle('week', null, 2)).toBe('每 2 周')
  expect(formatCycle('month', null, 3)).toBe('每 3 个月')
})
