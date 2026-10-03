import { defineComponent, h, nextTick } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import BillPlanForm from '@/components/billing/BillPlanForm.vue'
const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/', component: { template: '<div />' } }],
})

const ElFormStub = defineComponent({
  setup(_, { expose, slots }) {
    expose({ validate: () => Promise.resolve(true) })
    return () => h('form', slots.default?.())
  },
})

describe('BillPlanForm', () => {
  it('enforces the supported custom cycle bounds in the form validator', () => {
    const wrapper = shallowMount(BillPlanForm, { global: { plugins: [router] } })
    const vm = wrapper.vm as unknown as {
      form: { cycle_type: string }
      rules: {
        cycle_interval: {
          validator: (
            rule: unknown,
            value: number | null,
            callback: (error?: Error) => void,
          ) => void
        }[]
      }
    }
    vm.form.cycle_type = 'day'
    const validator = vm.rules.cycle_interval[0]!.validator
    for (const value of [1, 36500]) {
      validator({}, value, (error) => expect(error).toBeUndefined())
    }
    for (const value of [null, 0, 1.5, 36501]) {
      validator({}, value, (error) => expect(error?.message).toBe('请输入 1 到 36500 的整数'))
    }
  })

  it('shows custom days and emits a normalized payload', async () => {
    const wrapper = shallowMount(BillPlanForm, {
      global: {
        plugins: [router],
        stubs: {
          'el-form': ElFormStub,
          'el-form-item': { template: '<div><slot /></div>' },
          'el-input': true,
          'el-date-picker': true,
          'el-select': { template: '<div><slot /></div>' },
          'el-option': true,
          'el-input-number': { template: '<input data-test="cycle-days" />' },
          'el-button': true,
        },
      },
    })
    const vm = wrapper.vm as unknown as {
      form: Record<string, unknown>
      submit: () => Promise<void>
    }
    Object.assign(vm.form, {
      name: '  云服务  ',
      amount: '12.50',
      first_due_date: '2026-07-20',
      cycle_type: 'day',
      cycle_interval: 10,
      note: '  生产环境  ',
    })
    await nextTick()

    expect(wrapper.find('[data-test="cycle-days"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="cycle-days"]').attributes('min')).toBe('1')
    expect(wrapper.find('[data-test="cycle-days"]').attributes('max')).toBe('36500')
    await vm.submit()
    expect(wrapper.emitted('submit')?.[0]?.[0]).toEqual({
      name: '云服务',
      amount: '12.50',
      first_due_date: '2026-07-20',
      cycle_type: 'day',
      cycle_interval: 10,
      note: '生产环境',
      cycle_days: null,
    })
  })

  it('emits cancellation for the parent to handle without clearing the draft', async () => {
    const wrapper = shallowMount(BillPlanForm, { global: { plugins: [router] } })
    const vm = wrapper.vm as unknown as {
      form: { name: string }
      dirty: boolean
      cancel: () => void
    }
    vm.form.name = '未保存规则'
    vm.cancel()
    expect(wrapper.emitted('cancel')).toHaveLength(1)
    expect(vm.dirty).toBe(true)
  })

  it('prevents duplicate submissions while async validation is pending', async () => {
    let resolve!: (value: boolean) => void
    const validate = vi.fn(
      () =>
        new Promise<boolean>((done) => {
          resolve = done
        }),
    )
    const wrapper = shallowMount(BillPlanForm, {
      global: {
        plugins: [router],
        stubs: {
          'el-form': defineComponent({
            setup(_, { expose, slots }) {
              expose({ validate })
              return () => h('form', slots.default?.())
            },
          }),
        },
      },
    })
    const vm = wrapper.vm as unknown as { submit: () => Promise<void>; cancel: () => void }
    const saving = vm.submit()
    await vm.submit()
    vm.cancel()
    expect(validate).toHaveBeenCalledOnce()
    expect(wrapper.emitted('cancel')).toBeUndefined()
    resolve(true)
    await saving
    expect(wrapper.emitted('submit')).toHaveLength(1)
  })
})
