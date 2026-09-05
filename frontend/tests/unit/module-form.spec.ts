import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  updateModule: vi.fn().mockResolvedValue({ id: 1, name: 'x', parent_id: null }),
  // ModuleForm 的 onMounted 会调 fetchTree 拉父模块候选,必须 mock,否则 jsdom 真发请求
  fetchTree: vi.fn().mockResolvedValue([
    { id: 2, name: '现父模块', children: [], feature_points: [] },
    { id: 3, name: '目标模块', children: [], feature_points: [] },
  ]),
}))
vi.mock('../../src/api/tree', () => api)

import ModuleForm from '../../src/components/ModuleForm.vue'

describe('ModuleForm', () => {
  beforeEach(() => { api.updateModule.mockClear() })
  it('改名保存提交 name + 当前 parentId(恒带,后端 exclude_unset 幂等)', async () => {
    const wrapper = mount(ModuleForm, {
      props: { projectId: 1, moduleId: 5, initialName: '旧名', initialParentId: 2 },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()
    await wrapper.find('.name-input input').setValue('新名')
    await wrapper.find('button.save-btn').trigger('click')
    await flushPromises()
    expect(api.updateModule).toHaveBeenCalledWith(5, { name: '新名', parentId: 2 })
    expect(wrapper.emitted('saved')).toBeTruthy()
  })

  it('选择父模块后提交新的 parentId', async () => {
    const wrapper = mount(ModuleForm, {
      props: { projectId: 1, moduleId: 5, initialName: '模块', initialParentId: null },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()
    await wrapper.findComponent({ name: 'ElSelect' }).vm.$emit('update:modelValue', 3)
    await wrapper.find('button.save-btn').trigger('click')
    await flushPromises()
    expect(api.updateModule).toHaveBeenCalledWith(5, { name: '模块', parentId: 3 })
  })

  it('空名称阻止提交', async () => {
    const wrapper = mount(ModuleForm, {
      props: { projectId: 1, moduleId: 5, initialName: '旧名', initialParentId: null },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()
    await wrapper.find('.name-input input').setValue('  ')
    await wrapper.find('button.save-btn').trigger('click')
    await flushPromises()
    expect(api.updateModule).not.toHaveBeenCalled()
  })
})
