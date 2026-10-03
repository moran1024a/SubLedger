import { defineComponent } from 'vue'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import BillPlanForm from '@/components/billing/BillPlanForm.vue'
import {
  clearUnsavedChanges,
  confirmDiscardChanges,
  useUnsavedChanges,
} from '@/composables/useUnsavedChanges'
import { ElMessageBox } from 'element-plus'

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
    }
    vm.form.name = 'changed'
    await flushPromises()
    const confirm = vi.spyOn(ElMessageBox, 'confirm').mockRejectedValue('cancel')
    await router.push('/plans/2')
    expect(router.currentRoute.value.path).toBe('/plans/1')
    await router.push('/other')
    expect(router.currentRoute.value.path).toBe('/plans/1')
    const event = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
    expect(await confirmDiscardChanges()).toBe(false)
    vm.markSaved()
    confirm.mockClear()
    await router.push('/other')
    expect(router.currentRoute.value.path).toBe('/other')
    expect(confirm).not.toHaveBeenCalled()
  })

  it('asks once for multiple drafts and keeps them protected if a later guard rejects navigation', async () => {
    const draft = defineComponent({
      setup: useUnsavedChanges,
      template: '<input type="checkbox" v-model="dirty" />',
    })
    const page = defineComponent({ components: { Draft: draft }, template: '<Draft /><Draft />' })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/edit', component: page },
        { path: '/other', component: { template: '<p>other</p>' } },
      ],
    })
    await router.push('/edit')
    const wrapper = mount(RouterView, { global: { plugins: [router] } })
    for (const input of wrapper.findAll('input')) await input.setValue(true)
    const confirm = vi
      .spyOn(ElMessageBox, 'confirm')
      .mockResolvedValue('confirm' as Awaited<ReturnType<typeof ElMessageBox.confirm>>)
    const remove = router.beforeResolve(() => false)
    await router.push('/other')
    expect(confirm).toHaveBeenCalledTimes(1)
    expect(router.currentRoute.value.path).toBe('/edit')
    const event = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
    remove()
    await router.push('/other')
    expect(confirm).toHaveBeenCalledTimes(2)
    expect(router.currentRoute.value.path).toBe('/other')
  })

  it('preserves drafts for query navigation and treats an in-page discard confirmation as advisory', async () => {
    const page = defineComponent({
      setup: useUnsavedChanges,
      template: '<input type="checkbox" v-model="dirty" />',
    })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/edit/:id', component: page }],
    })
    await router.push('/edit/1')
    const wrapper = mount(RouterView, { global: { plugins: [router] } })
    await wrapper.find('input').setValue(true)
    const confirm = vi
      .spyOn(ElMessageBox, 'confirm')
      .mockResolvedValue('confirm' as Awaited<ReturnType<typeof ElMessageBox.confirm>>)
    await router.push('/edit/1?tab=records')
    expect(confirm).not.toHaveBeenCalled()
    expect(await confirmDiscardChanges()).toBe(true)
    const event = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
    confirm.mockRejectedValue('cancel')
    await router.push('/edit/2')
    expect(router.currentRoute.value.path).toBe('/edit/1')
  })
})
