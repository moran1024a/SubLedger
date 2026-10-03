import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import DateBadge from '@/components/common/DateBadge.vue'
import RecordCard from '@/components/common/RecordCard.vue'

describe('RecordCard', () => {
  it('renders every record slot in the card shell', () => {
    const wrapper = mount(RecordCard, {
      slots: {
        badge: '<span>有效</span>',
        title: 'Netflix',
        meta: '每月 · 2026-10-01',
        amount: '¥30.00',
        actions: '<button>查看</button>',
      },
    })

    expect(wrapper.get('.record-badge').text()).toBe('有效')
    expect(wrapper.get('.record-title').text()).toBe('Netflix')
    expect(wrapper.get('.record-meta').text()).toBe('每月 · 2026-10-01')
    expect(wrapper.get('.record-amount').text()).toBe('¥30.00')
    expect(wrapper.get('.record-actions button').text()).toBe('查看')
  })

  it('omits the optional rows when their slots are unused', () => {
    const wrapper = mount(RecordCard, { slots: { title: '只有标题' } })

    expect(wrapper.get('.record-title').text()).toBe('只有标题')
    expect(wrapper.find('.record-badge').exists()).toBe(false)
    expect(wrapper.find('.record-meta').exists()).toBe(false)
    expect(wrapper.find('.record-amount').exists()).toBe(false)
    expect(wrapper.find('.record-actions').exists()).toBe(false)
  })
})

describe('DateBadge', () => {
  it('shows the day above the month and keeps the machine readable date', () => {
    const wrapper = mount(DateBadge, { props: { date: '2026-03-07' } })

    expect(wrapper.get('.date-badge-day').text()).toBe('7')
    expect(wrapper.get('.date-badge-month').text()).toBe('3 月')
    expect(wrapper.attributes('datetime')).toBe('2026-03-07')
    expect(wrapper.classes()).not.toContain('date-badge--today')
  })

  it('highlights today', () => {
    const wrapper = mount(DateBadge, { props: { date: '2026-03-07', today: true } })

    expect(wrapper.classes()).toContain('date-badge--today')
  })
})
