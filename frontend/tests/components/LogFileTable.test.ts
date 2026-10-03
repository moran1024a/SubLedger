import { defineComponent, h, inject, provide } from 'vue'
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import LogFileTable from '@/components/logs/LogFileTable.vue'
import type { LogFile } from '@/types/api'

const ElTableStub = defineComponent({
  props: { data: { type: Array, default: () => [] } },
  setup(props, { slots }) {
    provide('rows', props.data)
    return () => h('div', slots.default?.())
  },
})
const ElTableColumnStub = defineComponent({
  setup(_, { slots }) {
    const rows = inject<LogFile[]>('rows', [])
    return () =>
      h(
        'div',
        rows.flatMap((row) => slots.default?.({ row }) ?? []),
      )
  },
})
const ElButtonStub = defineComponent({
  props: { disabled: Boolean, loading: Boolean },
  emits: ['click'],
  setup(props, { emit, slots }) {
    return () =>
      h('button', { disabled: props.disabled, onClick: () => emit('click') }, slots.default?.())
  },
})

const file = {
  date: '2026-07-20',
  filename: '2026-07-20.log',
  size: 8,
  modified_at: '2026-07-20T00:00:00Z',
}

describe('LogFileTable', () => {
  it('emits the selected filename and disables downloads while another download runs', async () => {
    const wrapper = mount(LogFileTable, {
      props: { files: [file], downloading: null },
      global: {
        stubs: {
          'el-table': ElTableStub,
          'el-table-column': ElTableColumnStub,
          'el-button': ElButtonStub,
        },
      },
    })

    await wrapper.get('.log-table button').trigger('click')
    expect(wrapper.emitted('download')?.[0]).toEqual(['2026-07-20.log'])

    await wrapper.setProps({ downloading: 'all' })
    expect(wrapper.get('.log-table button').attributes('disabled')).toBeDefined()
    expect(wrapper.get('.log-card button').attributes('disabled')).toBeDefined()
  })

  it('shows the full filename and file metadata on mobile cards and emits the same download', async () => {
    const longFile = { ...file, filename: `${'较长的日志文件名'.repeat(10)}.log`, size: 2048 }
    const wrapper = mount(LogFileTable, {
      props: { files: [longFile], downloading: null },
      global: {
        stubs: {
          'el-table': ElTableStub,
          'el-table-column': ElTableColumnStub,
          'el-button': ElButtonStub,
        },
      },
    })
    const card = wrapper.get('.log-card')
    expect(card.get('h2').text()).toBe(longFile.filename)
    expect(card.text()).toContain('2026-07-20')
    expect(card.text()).toContain('2.0 KB')
    expect(card.text()).toContain('最后修改')
    expect(card.get('button').attributes('aria-label')).toBe(`下载 ${longFile.filename}`)
    await card.get('button').trigger('click')
    expect(wrapper.emitted('download')).toEqual([[longFile.filename]])
    await wrapper.setProps({ downloading: longFile.filename })
    expect(card.get('button').attributes('disabled')).toBeDefined()
  })
})
