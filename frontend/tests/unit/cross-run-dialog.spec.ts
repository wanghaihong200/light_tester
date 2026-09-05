import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessage } from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { UiRun, UiScript } from '../../src/types'

// mock 口径照抄 run-dialog 运行框既有 spec:捕获 SSE 回调以便注入事件;orig 展开保持其余导出真实可用
const mocks = vi.hoisted(() => {
  let cb: (e: Record<string, unknown>) => void = () => {}
  return {
    create: vi.fn(async () => mkPendingRun()),
    getRun: vi.fn(async () => mkPendingRun()),
    subscribe: vi.fn((_id: number, c: (e: Record<string, unknown>) => void) => {
      cb = c
      return mocks.close
    }),
    close: vi.fn(),
    listAuth: vi.fn(async () => [] as unknown[]),
    fire: (e: Record<string, unknown>) => cb(e),
  }
})
vi.mock('../../src/api/uiAutomation', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  createUiRun: mocks.create,
  getUiRun: mocks.getRun,
  subscribeRunEvents: mocks.subscribe,
}))
vi.mock('../../src/api/crossAutomation', () => ({
  listCrossScripts: vi.fn(async () => []),
  listRunsByTarget: vi.fn(async () => []),
  listAuthStates: mocks.listAuth,
  collectAndroidSnapshot: vi.fn(async () => ({})),
}))

import CrossRunDialog from '../../src/components/crossauto/CrossRunDialog.vue'

function mkScript(opts: {
  id?: number
  name?: string
  target?: 'web' | 'android' | 'harmony'
  launch?: string
  variables?: UiScript['script']['variables']
} = {}): UiScript {
  const target = opts.target ?? 'web'
  const meta: UiScript['script']['meta'] = { start_url: target === 'web' ? 'https://x' : '', target }
  if (opts.launch) meta.launch_target = opts.launch
  return {
    id: opts.id ?? 1,
    project_id: 1,
    name: opts.name ?? 'AI冒烟',
    description: null,
    script: {
      version: 2,
      meta,
      variables: opts.variables ?? [],
      steps: [{ id: 's1', action: 'ai_tap', params: { target: '登录按钮' } }],
    },
    created_at: '2026-09-05T10:00:00',
    updated_at: '2026-09-05T10:00:00',
  }
}

function mkPendingRun(over: Partial<UiRun> = {}): UiRun {
  return {
    id: 5, project_id: 1, status: 'pending', script_id: 1, script_name: 'AI冒烟',
    mode: 'headless', variables: {}, step_results: [], steps_total: 0, steps_passed: 0,
    steps_failed: 0, error: null, started_at: null, finished_at: null,
    driver_target: 'web', ai_usage: null,
    ...over,
  }
}

function mountDialog(script: UiScript) {
  return mount(CrossRunDialog, {
    props: { visible: false, projectId: 1, script },
    global: { plugins: [ElementPlus] },
  })
}

async function open(w: ReturnType<typeof mountDialog>) {
  await w.setProps({ visible: true })
  await flushPromises()
}

const btn = (w: ReturnType<typeof mountDialog>, text: string) =>
  w.findAll('button').find((b) => b.text().trim() === text)!

describe('CrossRunDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.listAuth.mockResolvedValue([
      {
        id: 3, project_id: 1, name: '管理员登录态', created_at: '2026-09-05T10:00:00',
        kind: 'web_storage', app_package: null,
      },
    ])
  })

  it('① 提交时 createUiRun 收到 {script_id, mode, variables, auth_state_id};变量按 default 预填,缺省空串', async () => {
    const s = mkScript({
      variables: [{ name: 'kw', default: '手机', desc: '搜索关键词' }, { name: 'q' }],
    })
    const w = mountDialog(s)
    await open(w)
    expect(mocks.listAuth).toHaveBeenCalledWith(1, 'web_storage')
    expect(w.text()).toContain('搜索关键词')
    // default 预填
    const kwInput = w.findAll('input').find((i) => (i.element as HTMLInputElement).value === '手机')
    expect(kwInput).toBeTruthy()
    await btn(w, '开始执行').trigger('click')
    await flushPromises()
    expect(mocks.create).toHaveBeenCalledWith(1, {
      script_id: 1, mode: 'headless', variables: { kw: '手机', q: '' }, auth_state_id: undefined,
    })
    expect(mocks.subscribe).toHaveBeenCalledWith(5, expect.any(Function))
  })

  it('① 补充:选过登录态再改回「不使用」,提交 auth_state_id 为 undefined 而非空串(后端 int|None 防 422)', async () => {
    const w = mountDialog(mkScript())
    await open(w)
    const sel = w.findComponent({ name: 'ElSelect' })
    await sel.vm.$emit('update:modelValue', 3) // 先选登录态
    await sel.vm.$emit('update:modelValue', '') // 再改回「不使用」(选项 value 是空串)
    await flushPromises()
    await btn(w, '开始执行').trigger('click')
    await flushPromises()
    expect(mocks.create).toHaveBeenCalledWith(1, {
      script_id: 1, mode: 'headless', variables: {}, auth_state_id: undefined,
    })
  })

  it('② done 事件后展示 summary(通过 x/总 y)与 ai_usage.report_path', async () => {
    mocks.getRun.mockResolvedValue(mkPendingRun({
      id: 5,
      status: 'completed',
      steps_total: 2,
      steps_passed: 1,
      steps_failed: 1,
      step_results: [
        { index: 0, step_id: 's1', action: 'ai_tap', status: 'passed', error: null, screenshot: null, elapsed_ms: 120 },
        { index: 1, step_id: 's2', action: 'ai_assert', status: 'failed', error: '断言失败', screenshot: null, elapsed_ms: 80 },
      ],
      started_at: '2026-09-05T10:01:00',
      finished_at: '2026-09-05T10:01:05',
      ai_usage: { input_tokens: 120, output_tokens: 30, report_path: 'reports/ui_run_5.html' },
    }))
    const w = mountDialog(mkScript())
    await open(w)
    await btn(w, '开始执行').trigger('click')
    await flushPromises()
    mocks.fire({ type: 'done', status: 'completed', summary: { total: 2, passed: 1, failed: 1 }, report_path: 'reports/ui_run_5.html' })
    await flushPromises()
    expect(mocks.getRun).toHaveBeenCalledWith(5)
    expect(w.text()).toContain('通过 1/2')
    expect(w.text()).toContain('reports/ui_run_5.html')
  })

  it('补充:frame 事件渲染 b64 jpeg data URL,不走截图文件端点', async () => {
    const w = mountDialog(mkScript())
    await open(w)
    await btn(w, '开始执行').trigger('click')
    await flushPromises()
    mocks.fire({ type: 'frame', data: 'QUJD' })
    await flushPromises()
    expect(w.find('img.frame').attributes('src')).toBe('data:image/jpeg;base64,QUJD')
  })

  it('补充:android 端拉应用数据快照文案与 kind,且无执行方式单选', async () => {
    mocks.listAuth.mockResolvedValue([
      {
        id: 7, project_id: 1, name: '首页快照', created_at: '2026-09-05T10:00:00',
        kind: 'android_snapshot', app_package: 'com.example.app',
      },
    ])
    const w = mountDialog(mkScript({ target: 'android', launch: 'com.example.app' }))
    await open(w)
    expect(mocks.listAuth).toHaveBeenCalledWith(1, 'android_snapshot')
    expect(w.text()).toContain('应用数据快照')
    expect(w.text()).not.toContain('无头执行') // android 无 mode 单选
    // 下拉选项经 popper 渲染,从组件树断言选项标签
    const labels = w.findAllComponents({ name: 'ElOption' }).map((o) => String(o.props('label')))
    expect(labels).toContain('首页快照')
  })

  it('③ error 事件(环境级失败):ElMessage.error 提示 + refresh 拉终态,run.error 红字透出不再停在「等待画面」', async () => {
    const errSpy = vi.spyOn(ElMessage, 'error')
    mocks.getRun.mockResolvedValue(mkPendingRun({
      status: 'failed',
      error: '环境启动失败:缺少 AI Key,无法执行 ai_tap',
      started_at: '2026-09-05T10:01:00',
      finished_at: '2026-09-05T10:01:02',
    }))
    const w = mountDialog(mkScript())
    await open(w)
    await btn(w, '开始执行').trigger('click')
    await flushPromises()
    mocks.fire({ type: 'error', message: '环境启动失败:Node 进程崩溃' })
    await flushPromises()
    expect(String(errSpy.mock.calls[0][0])).toContain('Node 进程崩溃') // SSE error 的 message 透出
    expect(mocks.getRun).toHaveBeenCalledWith(5) // refresh 拉终态
    expect(w.text()).toContain('环境启动失败:缺少 AI Key') // 终态 summary 区透出 run.error
    expect(w.find('.summary').classes()).toContain('bad')
    expect(w.find('.err').text()).toContain('缺少 AI Key') // 红字(此场景无 step_results,.err 即 run.error)
  })

  it('③ 防重入:createUiRun 未返回期间连点「开始执行」,submitting 守卫 + 按钮 :loading 兜底只建一个 run', async () => {
    let resolveCreate!: (r: UiRun) => void
    mocks.create.mockImplementationOnce(
      () => new Promise<UiRun>((r) => { resolveCreate = r }),
    )
    const w = mountDialog(mkScript())
    await open(w)
    await btn(w, '开始执行').trigger('click') // 第一次点击:createUiRun 挂起中
    const pendingBtn = btn(w, '开始执行')!
    expect(pendingBtn.attributes('disabled')).toBeDefined() // :loading 期间禁点
    await pendingBtn.trigger('click') // jsdom 对禁用按钮仍派发 click,须由守卫兜住
    expect(mocks.create).toHaveBeenCalledTimes(1)
    resolveCreate(mkPendingRun())
    await flushPromises()
    expect(mocks.subscribe).toHaveBeenCalledTimes(1) // 也只订一次,无订阅泄漏
  })

  it('③ 防重入:run 已存在时再触发 submit 早退,不再调 createUiRun', async () => {
    const w = mountDialog(mkScript())
    await open(w)
    await btn(w, '开始执行').trigger('click')
    await flushPromises()
    expect(mocks.create).toHaveBeenCalledTimes(1)
    await (w.vm as { submit: () => Promise<void> }).submit() // run 存在(按钮已切到 runner 视图)
    await flushPromises()
    expect(mocks.create).toHaveBeenCalledTimes(1) // 早退,不产生第二个 run
    expect(mocks.subscribe).toHaveBeenCalledTimes(1)
  })
})
