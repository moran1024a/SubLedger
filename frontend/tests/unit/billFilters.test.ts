import { describe, expect, it } from 'vitest'
import { dateShortcut, positiveId, readBillQuery, validDate } from '@/utils/billFilters'

describe('bill query helpers', () => {
  it('accepts a single safe positive decimal identifier', () => {
    expect(positiveId('23')).toBe(23)
    expect(positiveId('003')).toBe(3)
    for (const value of ['0', '-1', '1.5', '1e2', '0x10', ' 3 ', '9007199254740993', ['3'], null]) {
      expect(positiveId(value)).toBeNull()
    }
  })
  it('defaults to upcoming and validates URL parameters', () => {
    expect(readBillQuery({})).toMatchObject({ time_status: 'upcoming', sort: 'asc', page: 1 })
    expect(
      readBillQuery({
        time_status: 'passed',
        page: '-2',
        page_size: '999',
        plan_id: 'NaN',
        start_date: '2026-02-30',
      }),
    ).toMatchObject({ sort: 'desc', page: 1, page_size: 20, plan_id: undefined, start_date: '' })
    expect(
      readBillQuery({ is_valid: 'false', q: ' cloud ', page: '2', page_size: '50' }),
    ).toMatchObject({ is_valid: 'false', q: 'cloud', page: 2, page_size: 50 })
  })
  it('drops an inverted date range and keeps single-sided dates', () => {
    expect(readBillQuery({ start_date: '2026-10-02', end_date: '2026-10-01' })).toMatchObject({
      start_date: '',
      end_date: '',
    })
    expect(readBillQuery({ start_date: '2026-10-01', end_date: '2026-10-01' })).toMatchObject({
      start_date: '2026-10-01',
      end_date: '2026-10-01',
    })
    expect(readBillQuery({ start_date: '2026-10-01' })).toMatchObject({
      start_date: '2026-10-01',
      end_date: '',
    })
    expect(readBillQuery({ end_date: '2026-10-31' })).toMatchObject({
      start_date: '',
      end_date: '2026-10-31',
    })
    expect(readBillQuery({ start_date: '2026-10-02', end_date: '2026-02-30' })).toMatchObject({
      start_date: '2026-10-02',
      end_date: '',
    })
  })
  it('validates calendar dates including leap years', () => {
    expect(validDate('2024-02-29')).toBe(true)
    expect(validDate('2026-02-29')).toBe(false)
    expect(validDate('0000-01-01')).toBe(false)
  })
  it('uses the account timezone across midnight and year boundaries', () => {
    const now = new Date('2026-12-31T18:00:00Z')
    expect(dateShortcut('month', 'Asia/Shanghai', now)).toEqual({
      range: ['2027-01-01', '2027-01-31'],
      status: 'all',
    })
    expect(dateShortcut('lastMonth', 'Asia/Shanghai', now)).toEqual({
      range: ['2026-12-01', '2026-12-31'],
      status: 'passed',
    })
    expect(dateShortcut('next30', 'America/Los_Angeles', now)).toEqual({
      range: ['2026-12-31', '2027-01-29'],
      status: 'upcoming',
    })
  })
})
