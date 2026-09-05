import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessage } from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../src/api/client'
import UserSearchSelect from '../../src/components/UserSearchSelect.vue'

// mock api 层:捕获入参、控制返回(el-select 遥控搜索走 usersApi.search)
const mocks = vi.hoisted(() => ({ search: vi.fn() }))
vi.mock('../../src/api/users', () => ({
  usersApi: { search: mocks.search },
}))

const RESULTS = [
  { id: 1, username: 'alice', display_name: '爱丽丝' },
  { id: 2, username: 'ali02', display_name: '阿李' },
]

function mountSelect(modelValue = '') {
  const w = mount(UserSearchSelect, {
    props: { modelValue },
    global: { plugins: [ElementPlus] },
  })
  return flushPromises().then(() => w)
}

function optionLabels(): string[] {
  return [...document.querySelectorAll('.el-select-dropdown__item')].map((el) => el.textContent?.trim() ?? '')
}

describe('UserSearchSelect 用户搜索下拉', () => {
  beforeEach(() => {
    mocks.search.mockReset()
  })

  it('remoteMethod 触发 search 并渲染「显示名 (用户名)」选项', async () => {
    mocks.search.mockResolvedValue(RESULTS)
    const w = await mountSelect()
    await (w.vm as any).remoteMethod('ali')
    expect(mocks.search).toHaveBeenCalledWith('ali')
    await flushPromises()
    expect(optionLabels()).toContain('爱丽丝 (alice)')
    expect(optionLabels()).toContain('阿李 (ali02)')
    w.unmount()
  })

  it('选中选项:emit update:modelValue 携带 username', async () => {
    mocks.search.mockResolvedValue(RESULTS)
    const w = await mountSelect()
    await (w.vm as any).remoteMethod('ali')
    await flushPromises()
    ;[...document.querySelectorAll('.el-select-dropdown__item')]
      .find((el) => el.textContent?.includes('alice'))!
      .click()
    await flushPromises()
    expect(w.emitted('update:modelValue')).toEqual([['alice']])
    w.unmount()
  })

  it('搜索失败:清掉过期选项并 ElMessage.error 透出后端 detail', async () => {
    const errSpy = vi.spyOn(ElMessage, 'error')
    mocks.search.mockResolvedValueOnce(RESULTS)
    const w = await mountSelect()
    await (w.vm as any).remoteMethod('ali')
    await flushPromises()
    expect(optionLabels()).toHaveLength(2)
    mocks.search.mockRejectedValueOnce(new ApiError(500, '搜索失败'))
    await (w.vm as any).remoteMethod('bob')
    await flushPromises()
    expect(errSpy).toHaveBeenCalledWith('搜索失败')
    expect(optionLabels()).toEqual([]) // 旧选项不残留
    w.unmount()
  })
})
