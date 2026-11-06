import { describe, expect, it } from 'vitest'
import { dayInMonth, monthCells, shiftDay, shiftMonth } from '@/utils/calendar'

describe('calendar date arithmetic', () => {
  it('uses a Monday-first six-week grid including adjacent month dates', () => {
    const cells = monthCells('2026-11')
    expect(cells).toHaveLength(42)
    expect(cells[0]).toBe('2026-10-26')
    expect(cells[41]).toBe('2026-12-06')
  })
  it('handles leap days and year boundaries without local timezone offsets', () => {
    expect(shiftDay('2028-02-28', 1)).toBe('2028-02-29')
    expect(shiftDay('2027-02-28', 1)).toBe('2027-03-01')
    expect(shiftMonth('2026-12', 1)).toBe('2027-01')
    expect(shiftMonth('2026-01', -1)).toBe('2025-12')
    expect(dayInMonth('2028-01-31', '2028-02')).toBe('2028-02-29')
    expect(dayInMonth('2027-01-31', '2027-02')).toBe('2027-02-28')
  })
  it('disables dates outside the supported MySQL year range', () => {
    expect(shiftMonth('1000-01', -1)).toBeNull()
    expect(shiftMonth('9999-12', 1)).toBeNull()
    expect(shiftDay('1000-01-01', -1)).toBeNull()
    expect(shiftDay('9999-12-31', 1)).toBeNull()
    expect(
      monthCells('9999-12')
        .filter((day) => day !== null)
        .at(-1),
    ).toBe('9999-12-31')
    expect(dayInMonth('2026-11-30', '9999-12')).toBe('9999-12-30')
  })
})
