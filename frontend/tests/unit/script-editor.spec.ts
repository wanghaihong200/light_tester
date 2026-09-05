import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessage } from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { ApiError } from '../../src/api/client'

// mock api:orig 展开保持其他导出真实可用(import 不炸)
const mocks = vi.hoisted(() => ({
  update: vi.fn(async () => ({ id: 1 })),
  create: vi.fn(async () => ({ id: 2 })),
  listAuth: vi.fn(async () => [] as { id: number; project_id: number; name: string; created_at: string }[]),
}))
vi.mock('../../src/api/uiAutomation', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  updateUiScript: mocks.update,
  createUiScript: mocks.create,
  listUiAuthStates: mocks.listAuth,
}))

import ScriptEditor from '../../src/components/webauto/ScriptEditor.vue'

const ROW = {
  id: 1, project_id: 1, name: '登录', description: null,
  script: {
    version: 1, meta: { start_url: 'http://x' },
    variables: [{ name: 'username', default: 'admin', desc: '' }],
    steps: [
      { id: 's1', action: 'goto', params: { url: 'http://x' } },
      { id: 's2', action: 'click', locator: { strategy: 'css', value: '#go' } },
    ],
  },
  created_at: '', updated_at: '',
}

// defineExpose 后经 vm 访问内部状态(vitest 下稳定,见 Task 9 澄清)
type Exposed = {
  doc: { steps: { id: string; action: string }[] }
  addStep: (action: string) => void
}
async function mountEditor(props: Record<string, unknown> = { projectId: 1, scriptRow: ROW }) {
  const w = mount(ScriptEditor, {
    props: props as never,
    global: { plugins: [ElementPlus] },
  })
  await flushPromises() // el-dialog 内容挂载在下一拍
  return w
}
function exposed(w: ReturnType<typeof mountEditor>): Exposed {
  return w.vm as unknown as Exposed
}
const stepRows = (w: ReturnType<typeof mountEditor>) => w.findAll('.steps-table .el-table__row')

describe('ScriptEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('渲染已有步骤与变量', async () => {
    const w = await mountEditor()
    expect(w.text()).toContain('goto')
    expect(w.text()).toContain('click')
    // el-input 的值落在 DOM input 的 value 上,不在 textContent,故按 value 断言
    const vals = w.findAll('input').map((i) => (i.element as HTMLInputElement).value)
    expect(vals).toContain('username')
    expect(vals).toContain('admin')
    expect(vals).toContain('http://x')
  })

  it('添加步骤追加行(defineExpose 驱动,表格行数同步变化)', async () => {
    const w = await mountEditor()
    const before = exposed(w).doc.steps.length
    exposed(w).addStep('fill')
    await nextTick()
    expect(exposed(w).doc.steps.length).toBe(before + 1)
    expect(stepRows(w).length).toBe(before + 1)
  })

  it('登录态(功能1):「不使用」保存后清除 meta.auth_state_id;已删登录态回退不使用', async () => {
    mocks.listAuth.mockResolvedValueOnce([{ id: 3, project_id: 1, name: 'testerhome', created_at: '2026-09-03T10:00:00' }])
    const row = structuredClone(ROW)
    ;(row.script.meta as Record<string, unknown>).auth_state_id = 3
    const w = await mountEditor({ projectId: 1, scriptRow: row })
    expect(w.findComponent({ name: 'ElSelect' }).props('modelValue')).toBe(3) // 初始=录制值

    await w.findComponent({ name: 'ElSelect' }).vm.$emit('update:modelValue', '') // 改回「不使用」
    await w.findAll('button').find((b) => b.text().trim() === '保存')!.trigger('click')
    await flushPromises()
    expect(mocks.update.mock.calls[0][1].script.meta.auth_state_id).toBeUndefined()
  })

  it('登录态(功能1):录制时选的登录态已被删除 → 打开即回退「不使用」,保存清除该键', async () => {
    mocks.listAuth.mockResolvedValueOnce([{ id: 3, project_id: 1, name: 'testerhome', created_at: '2026-09-03T10:00:00' }])
    const row = structuredClone(ROW)
    ;(row.script.meta as Record<string, unknown>).auth_state_id = 99
    const w = await mountEditor({ projectId: 1, scriptRow: row })
    expect(w.findComponent({ name: 'ElSelect' }).props('modelValue')).toBe('') // 回退
    await w.findAll('button').find((b) => b.text().trim() === '保存')!.trigger('click')
    await flushPromises()
    expect(mocks.update.mock.calls[0][1].script.meta.auth_state_id).toBeUndefined()
  })

  it('保存:已有脚本走 updateUiScript(深拷贝本地 doc)并 emit saved;保存失败只提示不关闭', async () => {
    const errSpy = vi.spyOn(ElMessage, 'error')
    const w = await mountEditor()
    exposed(w).addStep('wait')
    await nextTick()
    await w.findAll('button').find((b) => b.text().trim() === '保存')!.trigger('click')
    await flushPromises()
    expect(mocks.update).toHaveBeenCalledTimes(1)
    const body = mocks.update.mock.calls[0][1] as { name: string; script: { steps: unknown[] } }
    expect(body.name).toBe('登录')
    expect(body.script.steps).toHaveLength(3)
    // 深拷贝:提交对象不是 props.scriptRow.script 的引用,编辑未保存不影响原行
    expect(body.script).not.toBe(ROW.script)
    expect(w.emitted('saved')).toBeTruthy()

    // 保存失败(网络/500,真实 PUT /ui-scripts 不做结构校验):错误 toast、不 emit saved
    mocks.update.mockRejectedValueOnce(new ApiError(500, 'Internal Server Error'))
    await w.findAll('button').find((b) => b.text().trim() === '保存')!.trigger('click')
    await flushPromises()
    expect(errSpy).toHaveBeenCalledWith('保存失败:Internal Server Error')
    expect(w.emitted('saved')).toHaveLength(1) // 失败不关闭
  })

  it('新脚本走 createUiScript;脚本名为空时只提示不提交', async () => {
    const warnSpy = vi.spyOn(ElMessage, 'warning')
    const w = await mountEditor({ projectId: 1, scriptRow: null })
    await w.findAll('button').find((b) => b.text().trim() === '保存')!.trigger('click')
    await flushPromises()
    expect(warnSpy).toHaveBeenCalled()
    expect(mocks.create).not.toHaveBeenCalled()
    expect(w.emitted('saved')).toBeFalsy()

    const nameInput = w.findAll('input').find((i) => (i.element as HTMLInputElement).placeholder === '请输入脚本名')!
    await nameInput.setValue('冒烟脚本')
    await w.findAll('button').find((b) => b.text().trim() === '保存')!.trigger('click')
    await flushPromises()
    expect(mocks.create).toHaveBeenCalledWith(1, {
      name: '冒烟脚本',
      description: null,
      script: { version: 1, meta: { start_url: '' }, variables: [], steps: [] },
    })
    expect(w.emitted('saved')).toBeTruthy()
  })
})
