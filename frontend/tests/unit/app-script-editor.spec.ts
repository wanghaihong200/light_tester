import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const api = vi.hoisted(() => ({ createAppScript: vi.fn(), updateAppScript: vi.fn() }))
vi.mock('../../src/api/appAutomation', () => api)

// 只换掉 ElMessageBox.confirm(jsdom 里真确认框会挂起等点击),ElMessage 等其余导出保持真实现
const msgbox = vi.hoisted(() => ({ confirm: vi.fn() }))
vi.mock('element-plus', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  ElMessageBox: msgbox,
}))

import AppScriptEditor from '../../src/components/appauto/AppScriptEditor.vue'

const EXISTING = {
  id: 7, project_id: 1, name: '导入的用例', description: null,
  case_json: {
    caseName: '导入的用例', targetAppPackage: 'com.example.shop', priority: 2, recordMode: 'local',
    operationLog: {
      steps: [
        { operationNode: null,
          operationMethod: { actionEnum: 'SLEEP', operationParam: { text: '800' }, encrypt: false, safeEncrypt: false },
          operationIndex: 0, operationId: 'g', stepId: 'a1' },
        { operationNode: { resourceId: 'com.example.shop:id/btn_pay', text: '', description: '', xpath: '' },
          operationMethod: { actionEnum: 'CLICK', operationParam: {}, encrypt: false, safeEncrypt: false },
          operationIndex: 1, operationId: 'g', stepId: 'a2' },
        { operationNode: null, // 未支持动作:原样保留
          operationMethod: { actionEnum: 'SCROLL_TO_TOP', operationParam: { text: '' }, encrypt: false, safeEncrypt: false },
          operationIndex: 2, operationId: 'g', stepId: 'a3' },
      ],
    },
  },
  app_package: 'com.example.shop', created_at: '', updated_at: '',
}

const stubs = {
  'el-dialog': { template: '<div><slot/><slot name="footer"/></div>', props: ['modelValue', 'title'] },
  'el-input': { template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />', props: ['modelValue', 'placeholder'] },
  'el-select': { template: '<select @change="$emit(\'update:modelValue\', $event.target.value)"><slot/></select>', props: ['modelValue'] },
  'el-option': true, 'el-button': { template: '<button @click="$emit(\'click\')"><slot/></button>', props: ['type', 'link', 'icon'] },
}

const mountEd = (script: any = null) =>
  mount(AppScriptEditor, { props: { projectId: 1, script }, global: { stubs } })

describe('AppScriptEditor', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('新建:构建合法原生 JSON 并调 createAppScript', async () => {
    api.createAppScript.mockResolvedValue(EXISTING)
    const w = mountEd(null)
    ;(w.vm as any).caseName = '新用例'
    ;(w.vm as any).pkg = 'com.a'
    ;(w.vm as any).steps = [
      { action: 'CLICK', rid: 'com.a:id/go', nodeText: '', desc: '', xpath: '',
        paramText: '', assertMode: 'assert_contain', assertContent: '', allocKey: '', allocValue: '', raw: null },
      { action: 'SLEEP', rid: '', nodeText: '', desc: '', xpath: '',
        paramText: '500', assertMode: 'assert_contain', assertContent: '', allocKey: '', allocValue: '', raw: null },
    ]
    await (w.vm as any).save()
    await flushPromises()
    expect(api.createAppScript).toHaveBeenCalledTimes(1)
    const body = api.createAppScript.mock.calls[0][1]
    expect(body.case.caseName).toBe('新用例')
    expect(body.case.targetAppPackage).toBe('com.a')
    expect(body.case.operationLog.steps[0].operationMethod.actionEnum).toBe('CLICK')
    expect(body.case.operationLog.steps[0].operationNode).toEqual({
      resourceId: 'com.a:id/go', text: '', description: '', xpath: '',
      className: '', nodeBound: '' })
    expect(body.case.operationLog.steps[1].operationMethod.operationParam).toEqual({ text: '500' })
    expect(w.emitted('saved')).toBeTruthy()
  })

  it('编辑:回显既有步骤,保存保留未知顶层字段与未支持动作', async () => {
    api.updateAppScript.mockResolvedValue(EXISTING)
    const w = mountEd(EXISTING)
    await flushPromises()
    expect((w.vm as any).steps).toHaveLength(3)
    expect((w.vm as any).steps[1].action).toBe('CLICK')
    expect((w.vm as any).steps[1].rid).toBe('com.example.shop:id/btn_pay')
    ;(w.vm as any).steps[0].paramText = '999'
    await (w.vm as any).save()
    const body = api.updateAppScript.mock.calls[0][1]
    const steps = body.case.operationLog.steps
    expect(steps[0].operationMethod.operationParam.text).toBe('999')
    expect(steps[2].operationMethod.actionEnum).toBe('SCROLL_TO_TOP') // 未支持动作原样保留
    expect(body.case.priority).toBe(2) // 未知顶层字段保留
    expect(body.case.recordMode).toBe('local')
  })

  // ── 终审 I2:导入时勾了 allow_high_risk 的用例,编辑保存若不带该字段会被后端 PUT 重拦 400,
  //    编辑器又没有勾选框 = UI 死路;故保存前检测高危动作并确认后代传 allow_high_risk: true ──
  const RISKY = {
    ...EXISTING,
    case_json: {
      ...EXISTING.case_json,
      operationLog: {
        steps: [
          { operationNode: null,
            operationMethod: { actionEnum: 'CLEAR_DATA', operationParam: {}, encrypt: false, safeEncrypt: false },
            operationIndex: 0, operationId: 'g', stepId: 'r1' },
        ],
      },
    },
  }

  it('编辑含高危动作的导入用例:确认后带 allow_high_risk 保存', async () => {
    api.updateAppScript.mockResolvedValue(RISKY)
    msgbox.confirm.mockResolvedValue('confirm')
    const w = mountEd(RISKY)
    await flushPromises()
    await (w.vm as any).save()
    await flushPromises()
    expect(msgbox.confirm).toHaveBeenCalledTimes(1)
    expect(String(msgbox.confirm.mock.calls[0][0])).toContain('CLEAR_DATA') // 文案说明含哪些高危动作
    expect(api.updateAppScript).toHaveBeenCalledTimes(1)
    const body = api.updateAppScript.mock.calls[0][1]
    expect(body.allow_high_risk).toBe(true)
    expect(body.case.operationLog.steps[0].operationMethod.actionEnum).toBe('CLEAR_DATA')
    expect(w.emitted('saved')).toBeTruthy()
  })

  it('高危保存被用户取消:不调 updateAppScript、不 emit saved', async () => {
    api.updateAppScript.mockResolvedValue(RISKY)
    msgbox.confirm.mockRejectedValue('cancel')
    const w = mountEd(RISKY)
    await flushPromises()
    await (w.vm as any).save()
    await flushPromises()
    expect(msgbox.confirm).toHaveBeenCalledTimes(1)
    expect(api.updateAppScript).not.toHaveBeenCalled()
    expect(w.emitted('saved')).toBeFalsy()
  })

  it('无高危动作的保存不弹确认(维持既有行为)', async () => {
    api.updateAppScript.mockResolvedValue(EXISTING)
    const w = mountEd(EXISTING)
    await flushPromises()
    await (w.vm as any).save()
    await flushPromises()
    expect(msgbox.confirm).not.toHaveBeenCalled()
    expect(api.updateAppScript).toHaveBeenCalledTimes(1)
  })
})
