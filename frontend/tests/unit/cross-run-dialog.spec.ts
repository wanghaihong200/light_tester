import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
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
})
