import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessage } from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  getCase: vi.fn().mockResolvedValue({
    id: 100,
    feature_point_id: 10,
    title: '旧标题',
    priority: 'P1',
    precondition: '已注册用户',
    remark: null,
    executed_pass: null,
    steps: [
      { id: 1, step_no: 1, action: '输入正确账号密码', expected: '登录成功跳首页' },
    ],
  }),
  updateCase: vi.fn().mockResolvedValue({}),
  patchExecution: vi.fn().mockResolvedValue({}),
}))
vi.mock('../../src/api/cases', () => api)

import CaseForm from '../../src/components/CaseForm.vue'

function mountForm() {
  return mount(CaseForm, { props: { caseId: 100 }, global: { plugins: [ElementPlus] } })
}

describe('CaseForm', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('挂载即加载详情并渲染', async () => {
    const wrapper = mountForm()
    await flushPromises()
    expect(api.getCase).toHaveBeenCalledWith(100)
    expect((wrapper.find('.title-input input').element as HTMLInputElement).value).toBe('旧标题')
    // jsdom 中 el-input textarea 的值不在 wrapper.text() 里,需直接读 element.value
    expect((wrapper.find('.step-action textarea').element as HTMLTextAreaElement).value).toBe('输入正确账号密码')
  })

  it('保存提交全量字段(含步骤全量替换)', async () => {
    const wrapper = mountForm()
    await flushPromises()
    await wrapper.find('button.add-step-btn').trigger('click')
    const actions = wrapper.findAll('.step-action textarea')
    await actions[1].setValue('退出登录')
    const expecteds = wrapper.findAll('.step-expected textarea')
    await expecteds[1].setValue('回到登录页')
    await wrapper.find('button.save-btn').trigger('click')
    await flushPromises()
    expect(api.updateCase).toHaveBeenCalledWith(
      100,
      expect.objectContaining({
        title: '旧标题',
        priority: 'P1',
        steps: [
          { action: '输入正确账号密码', expected: '登录成功跳首页' },
          { action: '退出登录', expected: '回到登录页' },
        ],
      }),
    )
  })

  it('步骤含空行时阻止提交', async () => {
    const wrapper = mountForm()
    await flushPromises()
    await wrapper.find('button.add-step-btn').trigger('click') // 新增空白行
    await wrapper.find('button.save-btn').trigger('click')
    await flushPromises()
    expect(api.updateCase).not.toHaveBeenCalled()
  })

  it('保存同时 PATCH 执行结果', async () => {
    const wrapper = mountForm()
    await flushPromises()
    await wrapper.find('button.save-btn').trigger('click')
    await flushPromises()
    expect(api.patchExecution).toHaveBeenCalledWith(100, null)
  })

  it('执行结果仅提供通过/未通过两项(未执行只能来自初始态)', async () => {
    const wrapper = mountForm()
    await flushPromises()
    const execLabels = wrapper
      .findAll('.el-radio-button')
      .map((b) => b.text())
      .filter((t) => ['通过', '未通过', '未执行'].includes(t))
    expect(execLabels).toEqual(['通过', '未通过'])
  })

  it('执行结果保存失败时提示内容已保存', async () => {
    api.patchExecution.mockRejectedValueOnce(new Error('x'))
    const errorSpy = vi.spyOn(ElMessage, 'error')
    const wrapper = mountForm()
    await flushPromises()
    await wrapper.find('button.save-btn').trigger('click')
    await flushPromises()
    expect(errorSpy).toHaveBeenCalledWith(
      expect.stringContaining('内容已保存,但执行结果保存失败'),
    )
    expect(wrapper.emitted('saved')).toBeTruthy()
    errorSpy.mockRestore()
  })
})
