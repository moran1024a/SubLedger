import { defineComponent } from 'vue'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import BillPlanForm from '@/components/billing/BillPlanForm.vue'
import { clearUnsavedChanges, confirmDiscardChanges } from '@/composables/useUnsavedChanges'

afterEach(() => {
  vi.restoreAllMocks()
  clearUnsavedChanges()
})
describe('unsaved user forms', () => {
  it('protects route changes and same-view plan changes, and stops prompting after success', async () => {
    const page = defineComponent({ components: { BillPlanForm }, template: '<BillPlanForm />' })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/plans/:id', component: page },
        { path: '/other', component: { template: '<p>other</p>' } },
      ],
    })
    await router.push('/plans/1')
    await router.isReady()
    const wrapper = mount(RouterView, { global: { plugins: [router] } })
    const form = wrapper.findComponent(BillPlanForm)
    const vm = form.vm as unknown as {
      form: { name: string }
      markSaved: () => void
      cancel: () => void
    }
    vm.form.name = 'changed'
    await flushPromises()
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    await router.push('/plans/2')
    expect(router.currentRoute.value.path).toBe('/plans/1')
    await router.push('/other')
    expect(router.currentRoute.value.path).toBe('/plans/1')
    vm.cancel()
    expect(form.emitted('cancel')).toBeUndefined()
    const event = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
    expect(confirmDiscardChanges()).toBe(false)
    vm.markSaved()
    confirm.mockClear()
    await router.push('/other')
    expect(router.currentRoute.value.path).toBe('/other')
    expect(confirm).not.toHaveBeenCalled()
  })
})
