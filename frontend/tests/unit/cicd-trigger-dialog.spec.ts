// frontend/tests/unit/cicd-trigger-dialog.spec.ts
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ preflight: vi.fn(), triggerRuns: vi.fn() }))
vi.mock('../../src/api/cicd', () => api)

import TriggerDialog from '../../src/components/cicd/TriggerDialog.vue'

const CLEAN = { plan_id: 1, name: '干净计划', kind: 'api' as const, branch: 'master',
  freshness: { on_branch: true, dirty_files: 0, ahead: 0, stale: false }, valid: 2, missing: 0, error: null }
const STALE = { ...CLEAN, plan_id: 2, name: '过时计划',
  freshness: { on_branch: true, dirty_files: 3, ahead: 0, stale: true } }

const mountDialog = (planIds: number[]) =>
  mount(TriggerDialog, { props: { projectId: 3, planIds, modelValue: true },
                         global: { plugins: [ElementPlus] }, attachTo: document.body })

describe('TriggerDialog', () => {
  it('全部新鲜:无确认框,执行带 confirm_stale=false', async () => {
    api.preflight.mockResolvedValue([CLEAN])
    api.triggerRuns.mockResolvedValue({ runs: [{ id: 9 }], failures: [] })
    const w = mountDialog([1])
    await flushPromises()
    expect(w.find('.stale-alert').exists()).toBe(false)
    await w.find('.do-trigger').trigger('click')
    await flushPromises()
    expect(api.triggerRuns).toHaveBeenCalledWith(3, [1], false)
    expect(w.emitted('triggered')).toBeTruthy()
  })

  it('有 stale:须勾确认才能执行,confirm_stale=true', async () => {
    api.preflight.mockResolvedValue([CLEAN, STALE])
    api.triggerRuns.mockResolvedValue({ runs: [], failures: [] })
    const w = mountDialog([1, 2])
    await flushPromises()
    expect(w.find('.stale-alert').exists()).toBe(true)
    expect((w.find('.do-trigger').element as HTMLButtonElement).disabled).toBe(true)
    ;(w.vm as unknown as { agree: boolean }).agree = true
    await flushPromises()
    await w.find('.do-trigger').trigger('click')
    await flushPromises()
    expect(api.triggerRuns).toHaveBeenCalledWith(3, [1, 2], true)
  })
})
