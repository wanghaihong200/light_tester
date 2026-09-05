import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// ---- mock api/jobs ----
const jobsApi = vi.hoisted(() => ({
  listStaging: vi.fn().mockResolvedValue({
    job_id: 1,
    groups: [
      {
        feature_point_name: '账号登录',
        cases: [
          { id: 101, job_id: 1, feature_point_name: '账号登录', title: '登录成功', priority: 'P0', precondition: null, remark: null, steps: [], created_at: '2026-08-16T10:00:00' },
          { id: 102, job_id: 1, feature_point_name: '账号登录', title: '密码错误提示', priority: 'P1', precondition: null, remark: null, steps: [], created_at: '2026-08-16T10:00:00' },
        ],
      },
      {
        feature_point_name: '权限管理',
        cases: [
          { id: 103, job_id: 1, feature_point_name: '权限管理', title: '角色分配', priority: 'P2', precondition: null, remark: null, steps: [], created_at: '2026-08-16T10:00:00' },
        ],
      },
    ],
  }),
  acceptStaging: vi.fn().mockResolvedValue({ accepted: 2, feature_point_ids: {} }),
  rejectStaged: vi.fn().mockResolvedValue(undefined),
}))
vi.mock('../../src/api/jobs', () => jobsApi)

// ---- mock MindmapEditor.vue ----
const MindmapEditorDef = vi.hoisted(() => ({
  name: 'MindmapEditor',
  props: ['data'],
  template: '<div class="mindmap-stub"></div>',
}))
vi.mock('../../src/components/MindmapEditor.vue', () => ({ default: MindmapEditorDef }))

// ---- mock ElMessageBox ----
const ElMessageBoxMock = vi.hoisted(() => ({
  confirm: vi.fn().mockResolvedValue(true),
}))
vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<typeof import('element-plus')>()
  return {
    ...actual,
    ElMessageBox: {
      ...actual.ElMessageBox,
      confirm: ElMessageBoxMock.confirm,
    },
  }
})

import StagingPane from '../../src/components/StagingPane.vue'

describe('StagingPane', () => {
  beforeEach(() => vi.clearAllMocks())

  it('渲染分组与勾选', async () => {
    const wrapper = mount(StagingPane, {
      props: { jobId: 1 },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()
    expect(jobsApi.listStaging).toHaveBeenCalledWith(1)
    const text = wrapper.text()
    expect(text).toContain('账号登录 (2)')
    expect(text).toContain('[P0] 登录成功')
    expect(text).toContain('暂存区仅有')
  })

  it('入库调 acceptStaging(选中 ids)', async () => {
    const wrapper = mount(StagingPane, {
      props: { jobId: 1 },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()

    const checkboxes = wrapper.findAllComponents({ name: 'ElCheckbox' })
    await checkboxes[1].vm.$emit('change', true)
    await flushPromises()
    await checkboxes[2].vm.$emit('change', true)
    await flushPromises()

    const acceptBtn = wrapper.findAll('button').find(b => b.text().trim() === '入库所选')!
    await acceptBtn.trigger('click')
    await flushPromises()

    expect(jobsApi.acceptStaging).toHaveBeenCalledWith(1, expect.arrayContaining([101, 102]))
    expect(jobsApi.listStaging).toHaveBeenCalledTimes(2)
    expect(wrapper.emitted('accepted')).toBeTruthy()
  })

  it('拒绝确认后逐个 rejectStaged', async () => {
    const wrapper = mount(StagingPane, {
      props: { jobId: 1 },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()

    const checkboxes = wrapper.findAllComponents({ name: 'ElCheckbox' })
    await checkboxes[1].vm.$emit('change', true)
    await flushPromises()
    await checkboxes[2].vm.$emit('change', true)
    await flushPromises()

    const rejectBtn = wrapper.findAll('button').find(b => b.text().trim() === '拒绝所选')!
    await rejectBtn.trigger('click')
    await flushPromises()

    expect(ElMessageBoxMock.confirm).toHaveBeenCalled()
    expect(jobsApi.rejectStaged).toHaveBeenCalledWith(101)
    expect(jobsApi.rejectStaged).toHaveBeenCalledWith(102)
    expect(jobsApi.listStaging).toHaveBeenCalledTimes(2)
  })

  it('勾选驱动预览', async () => {
    const wrapper = mount(StagingPane, {
      props: { jobId: 1 },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('勾选左侧用例查看预览')

    const checkboxes = wrapper.findAllComponents({ name: 'ElCheckbox' })
    await checkboxes[1].vm.$emit('change', true)
    await flushPromises()

    const editor = wrapper.findComponent({ name: 'MindmapEditor' })
    const data = editor.props('data') as any
    expect(data.children).toHaveLength(1)
    expect(data.children[0].children).toHaveLength(1)
    expect(data.children[0].children[0].data.text).toContain('登录成功')

    await checkboxes[1].vm.$emit('change', false)
    await flushPromises()
    expect(wrapper.text()).toContain('勾选左侧用例查看预览')
  })
})
