import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessage, ElMessageBox } from 'element-plus'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { UiRun, UiScript } from '../../src/types'

// mock api:捕获 SSE 回调以便注入事件;orig 展开保持模块其他导出真实可用(import 不炸)
const mocks = vi.hoisted(() => {
  let cb: (e: Record<string, unknown>) => void = () => {}
  // createUiRun 返回值对齐 types.UiRun 真实契约(组件至少消费 id);
  // status 用后端模型默认 pending(models.py UiRun.status default),勿标 running
  const run: import('../../src/types').UiRun = {
    id: 5, project_id: 1, status: 'pending', script_id: 1, script_name: '冒烟脚本',
    mode: 'headless', variables: {}, step_results: [], steps_total: 0,
    steps_passed: 0, steps_failed: 0, error: null, started_at: null, finished_at: null,
  }
  return {
    create: vi.fn(async () => run),
    subscribe: vi.fn((_id: number, c: (e: Record<string, unknown>) => void) => { cb = c; return mocks.close }),
    close: vi.fn(),
    // 默认无登录态:无变量脚本直接跑(确认面板基线);登录态专项用例内显式覆盖
    listAuth: vi.fn(async () => []),
    forceFinish: vi.fn(async () => ({ ...run, status: 'failed', error: '执行异常: 用户强制结束' })),
    fire: (e: Record<string, unknown>) => cb(e),
  }
})
vi.mock('../../src/api/uiAutomation', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  createUiRun: mocks.create,
  subscribeRunEvents: mocks.subscribe,
  listUiAuthStates: mocks.listAuth,
  forceFinishRun: mocks.forceFinish,
}))

import RunDialog from '../../src/components/webauto/RunDialog.vue'

// 截图改走鉴权 blob(fetch→objectURL):替身 fetch 返回图片流,替身 objectURL 可断言(键序即调用序)
const origObjectUrls = { create: URL.createObjectURL, revoke: URL.revokeObjectURL }
function stubShotFetch() {
  let seq = 0
  const create = vi.fn(() => `blob:shot-${++seq}`)
  const revoke = vi.fn()
  Object.defineProperty(URL, 'createObjectURL', { value: create, configurable: true, writable: true })
  Object.defineProperty(URL, 'revokeObjectURL', { value: revoke, configurable: true, writable: true })
  const fn = vi.fn(async () => new Response(new Blob(['jpg'], { type: 'image/jpeg' }), { status: 200 }))
  vi.stubGlobal('fetch', fn)
  return { fn, create, revoke }
}

function mkScript(opts: {
  id?: number; name?: string
  variables?: UiScript['script']['variables']; steps?: UiScript['script']['steps']
} = {}): UiScript {
  return {
    id: opts.id ?? 1,
    project_id: 1,
    name: opts.name ?? '冒烟脚本',
    description: null,
    script: {
      version: 1,
      meta: { start_url: 'http://x' },
      variables: opts.variables ?? [],
      steps: opts.steps ?? [],
    },
    created_at: '2026-09-02T10:00:00',
    updated_at: '2026-09-02T10:00:00',
  }
}

function mkRun(over: Partial<UiRun> = {}): UiRun {
  return {
    id: 5,
    project_id: 1,
    status: 'failed',
    script_id: 1,
    script_name: '冒烟脚本',
    mode: 'headless',
    variables: {},
    steps_total: 2,
    steps_passed: 1,
    steps_failed: 1,
    error: null,
    started_at: '2026-09-02T10:01:00',
    finished_at: '2026-09-02T10:01:05',
    step_results: [
      { index: 0, step_id: 's1', action: 'goto', status: 'passed', error: null, screenshot: 'step_0_passed.jpg', elapsed_ms: 100 },
      { index: 1, step_id: 's2', action: 'assert_text', status: 'failed', error: '文本不匹配', screenshot: 'step_1_failed.jpg', elapsed_ms: 200 },
    ],
    ...over,
  }
}

function mountDialog(props: Record<string, unknown>) {
  return mount(RunDialog, { props, global: { plugins: [ElementPlus] } })
}

describe('RunDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    Object.defineProperty(URL, 'createObjectURL', {
      value: origObjectUrls.create,
      configurable: true,
      writable: true,
    })
    Object.defineProperty(URL, 'revokeObjectURL', {
      value: origObjectUrls.revoke,
      configurable: true,
      writable: true,
    })
  })

  it('执行流:index=-1 显示启动浏览器占位,step_end 原位更新并渲染错误与截图', async () => {
    const shots = stubShotFetch() // 截图经鉴权 blob 加载:fetch /api/ui-runs/5/screens/* → objectURL
    const s = mkScript({ steps: [{ id: 's2', action: 'assert_text', params: { text: '欢迎' } }] })
    const w = mountDialog({ projectId: 1, queue: [{ script: s, mode: 'headless' }] })
    await flushPromises()
    expect(mocks.create).toHaveBeenCalledWith(1, {
      script_id: 1, mode: 'headless', variables: {}, auth_state_id: undefined,
    })

    mocks.fire({ type: 'step_start', index: -1 }) // 环境预启步:仅占位行
    mocks.fire({ type: 'step_start', index: 0 })
    mocks.fire({ type: 'frame', data: 'QUJD', step_index: 0 })
    mocks.fire({ type: 'step_end', index: 0, status: 'failed', error: '元素不存在: #x', screenshot: 'step_0_failed.jpg' })
    await flushPromises()
    expect(w.text()).toContain('启动浏览器')
    expect(w.text()).toContain('元素不存在: #x')
    expect(shots.fn.mock.calls[0][0]).toBe('/api/ui-runs/5/screens/step_0_failed.jpg') // 带鉴权取流
    expect(w.html()).toContain('blob:shot-1') // 缩略图渲染的是 objectURL
    expect(w.findAll('.log-row').length).toBe(2) // 占位行 + 真实步骤行,同 index 不重复建行
    expect(w.find('.frame-badge').text()).toBe('第 1 步') // 帧角标标注当前画面所属步骤
  })

  it('done 显示汇总(通过 x/总 y · 耗时 z 秒)并停止订阅,迟到事件不再打扰', async () => {
    const w = mountDialog({ projectId: 1, queue: [{ script: mkScript(), mode: 'headless' }] })
    await flushPromises()
    mocks.fire({ type: 'step_start', index: 0 })
    mocks.fire({ type: 'step_end', index: 0, status: 'passed', screenshot: 'step_0_passed.jpg' })
    mocks.fire({ type: 'done', status: 'completed', summary: { total: 2, passed: 1, failed: 1, duration_ms: 1500 } })
    mocks.fire({ type: 'error', message: '连接中断' })
    await flushPromises()
    expect(w.text()).toContain('通过 1/2 · 耗时 1.5 秒')
    expect(w.find('.summary').classes()).not.toContain('bad') // 成功终态摘要保持主题色
    expect(mocks.close).toHaveBeenCalled() // 终态即断流,避免 EventSource 重连 404 误报
    expect(w.text()).not.toContain('连接中断')
  })

  it('执行入口 400:createUiRun reject → 透传错误提示并跳过该脚本继续队列下一个', async () => {
    const errSpy = vi.spyOn(ElMessage, 'error')
    mocks.create.mockRejectedValueOnce(new Error('脚本不合法: 步骤缺少 action'))
    const w = mountDialog({
      projectId: 1,
      queue: [
        { script: mkScript({ id: 1, name: '脚本甲' }), mode: 'headless' },
        { script: mkScript({ id: 2, name: '脚本乙' }), mode: 'headless' },
      ],
    })
    await flushPromises()
    expect(String(errSpy.mock.calls[0][0])).toContain('脚本不合法')
    expect(mocks.create).toHaveBeenCalledTimes(2)
    expect(mocks.create).toHaveBeenNthCalledWith(2, 1, {
      script_id: 2, mode: 'headless', variables: {}, auth_state_id: undefined,
    })
    expect(w.text()).toContain('第 2/2 个:脚本乙') // 队列头部推进到下一个
  })

  it('历史模式:左侧 run 列表点选切换,渲染 step_results 与截图(blob objectURL),失败步骤整行红标', async () => {
    const shots = stubShotFetch()
    const r1 = mkRun()
    const r2 = mkRun({
      id: 6,
      status: 'completed',
      steps_total: 1,
      steps_passed: 1,
      steps_failed: 0,
      step_results: [
        { index: 0, step_id: 'x1', action: 'fill', status: 'passed', error: null, screenshot: 'step_0_passed.jpg', elapsed_ms: 50 },
      ],
    })
    const w = mountDialog({ projectId: 1, queue: [], history: { script: mkScript(), runs: [r1, r2] } })
    await flushPromises() // el-dialog 内容在 open 后才渲染;截图 fetch→objectURL 也已落定
    expect(w.text()).toContain('执行历史 · 冒烟脚本')
    expect(w.text()).toContain('文本不匹配') // 默认选中第一条,直接可看步骤详情
    expect(shots.fn.mock.calls.map((c) => c[0])).toEqual([
      '/api/ui-runs/5/screens/step_0_passed.jpg',
      '/api/ui-runs/5/screens/step_1_failed.jpg',
    ])
    expect(w.findAll('.row-failed').length).toBe(1) // 失败步骤红标
    // 功能2:每张缩略图的预览列表 = 该 run 全部截图(2 张,objectURL),查看器内可前后切换
    for (const img of w.findAllComponents({ name: 'ElImage' })) {
      expect(img.props('previewSrcList')).toEqual(['blob:shot-1', 'blob:shot-2'])
    }

    await w.findAll('.run-item')[1].trigger('click') // 点选第二条 → 切换渲染该 run 的结果
    await flushPromises() // run 6 截图 fetch→objectURL 异步落定后再断言
    expect(w.text()).toContain('fill')
    expect(w.html()).toContain('blob:shot-3') // run 6 的截图另取流
    expect(shots.fn).toHaveBeenCalledWith('/api/ui-runs/6/screens/step_0_passed.jpg', expect.anything())
    expect(w.findAll('.row-failed').length).toBe(0)
  })

  it('SSE error 事件:标记失败并断流,停在「运行中」的行收尾为失败', async () => {
    const w = mountDialog({ projectId: 1, queue: [{ script: mkScript(), mode: 'headless' }] })
    await flushPromises()
    mocks.fire({ type: 'step_start', index: -1 })
    mocks.fire({ type: 'step_start', index: 0 })
    mocks.fire({ type: 'error', message: '浏览器启动失败: 缺少可执行文件' })
    await flushPromises()
    expect(w.text()).toContain('浏览器启动失败: 缺少可执行文件')
    expect(mocks.close).toHaveBeenCalled() // 终态即断流
    expect(w.findAll('.log-row.failed').length).toBe(1) // 在途真实步骤行收尾为失败
    expect(w.findAll('.log-row.passed').length).toBe(1) // 环境预启行已在真实步骤开始时收尾
  })

  it('登录态下拉仅在项目存在登录态时显示;无登录态时确认后以无登录态执行', async () => {
    mocks.listAuth.mockResolvedValueOnce([])
    const s = mkScript({ variables: [{ name: 'kw', default: '', desc: '搜索关键词' }] })
    const w = mountDialog({ projectId: 1, queue: [{ script: s, mode: 'headless' }] })
    await flushPromises()
    expect(w.text()).not.toContain('登录态') // 项目暂无登录态:不出下拉
    await w.findAll('button').find((b) => b.text().includes('开始执行本脚本'))!.trigger('click')
    await flushPromises()
    expect(mocks.create).toHaveBeenCalledWith(1, {
      script_id: 1, mode: 'headless', variables: { kw: '' }, auth_state_id: undefined,
    })
  })

  it('录制带登录态的无变量脚本:直接默认执行不弹面板,auth_state_id 自动带上(功能1)', async () => {
    mocks.listAuth.mockResolvedValueOnce([{ id: 3, project_id: 1, name: 'testerhome', created_at: '2026-09-03T10:00:00' }])
    const s = mkScript({ name: '带态脚本' })
    ;(s.script.meta as Record<string, unknown>).auth_state_id = 3
    const w = mountDialog({ projectId: 1, queue: [{ script: s, mode: 'headless' }] })
    await flushPromises()
    expect(w.text()).not.toContain('开始执行本脚本') // 无面板,直跑
    expect(mocks.create).toHaveBeenCalledWith(1, {
      script_id: 1, mode: 'headless', variables: {}, auth_state_id: 3,
    })
  })

  it('录制带登录态且有变量的脚本:面板只为变量弹,登录态预选录制值(功能1)', async () => {
    mocks.listAuth.mockResolvedValueOnce([{ id: 3, project_id: 1, name: 'testerhome', created_at: '2026-09-03T10:00:00' }])
    const s = mkScript({ variables: [{ name: 'kw', default: '手机', desc: '搜索关键词' }] })
    ;(s.script.meta as Record<string, unknown>).auth_state_id = 3
    const w = mountDialog({ projectId: 1, queue: [{ script: s, mode: 'headless' }] })
    await flushPromises()
    expect(w.text()).toContain('开始执行本脚本') // 面板在(变量要收集)
    await w.findAll('button').find((b) => b.text().includes('开始执行本脚本'))!.trigger('click')
    await flushPromises()
    // 不碰下拉直接确认:预选的录制登录态生效
    expect(mocks.create).toHaveBeenCalledWith(1, {
      script_id: 1, mode: 'headless', variables: { kw: '手机' }, auth_state_id: 3,
    })
  })

  it('录制时选的登录态已被删除:回退为询问(面板弹,默认不使用)(功能1 兜底)', async () => {
    mocks.listAuth.mockResolvedValueOnce([{ id: 3, project_id: 1, name: 'testerhome', created_at: '2026-09-03T10:00:00' }])
    const s = mkScript({ name: '失态脚本' })
    ;(s.script.meta as Record<string, unknown>).auth_state_id = 99 // 已不存在
    const w = mountDialog({ projectId: 1, queue: [{ script: s, mode: 'headless' }] })
    await flushPromises()
    expect(w.text()).toContain('开始执行本脚本')
    await w.findAll('button').find((b) => b.text().includes('开始执行本脚本'))!.trigger('click')
    await flushPromises()
    expect(mocks.create).toHaveBeenCalledWith(1, {
      script_id: 1, mode: 'headless', variables: {}, auth_state_id: undefined,
    })
  })

  it('无变量脚本 + 项目存在登录态:也出确认面板提供登录态入口,确认后带 auth_state_id 执行', async () => {
    mocks.listAuth.mockResolvedValueOnce([{ id: 3, project_id: 1, name: '管理员登录态', created_at: '2026-09-02T10:00:00' }])
    const w = mountDialog({ projectId: 1, queue: [{ script: mkScript({ name: '无变量脚本' }), mode: 'headless' }] })
    await flushPromises()
    expect(mocks.create).not.toHaveBeenCalled() // 面板先出,不直接开跑
    expect(w.text()).toContain('执行「无变量脚本」前请确认参数')
    expect(w.text()).toContain('登录态')

    await w.findComponent({ name: 'ElSelect' }).vm.$emit('update:modelValue', 3) // 选登录态
    await flushPromises()
    await w.findAll('button').find((b) => b.text().includes('开始执行本脚本'))!.trigger('click')
    await flushPromises()
    expect(mocks.create).toHaveBeenCalledWith(1, {
      script_id: 1, mode: 'headless', variables: {}, auth_state_id: 3,
    })
  })

  it('声明变量的脚本先在本对话框内收集变量与登录态,点「开始执行本脚本」才创建执行', async () => {
    mocks.listAuth.mockResolvedValueOnce([{ id: 3, project_id: 1, name: '管理员登录态', created_at: '2026-09-02T10:00:00' }])
    const s = mkScript({ variables: [{ name: 'kw', default: '手机', desc: '搜索关键词' }] })
    const w = mountDialog({ projectId: 1, queue: [{ script: s, mode: 'headless' }] })
    await flushPromises()
    expect(mocks.listAuth).toHaveBeenCalledWith(1)
    expect(mocks.create).not.toHaveBeenCalled() // 表单未确认不启动执行
    expect(w.text()).toContain('搜索关键词')
    expect(w.findAll('input').some((i) => (i.element as HTMLInputElement).value === '手机')).toBe(true) // 预填默认值
    await w.findComponent({ name: 'ElSelect' }).vm.$emit('update:modelValue', 3) // 选择登录态
    await flushPromises()

    await w.findAll('button').find((b) => b.text().includes('开始执行本脚本'))!.trigger('click')
    await flushPromises()
    expect(mocks.create).toHaveBeenCalledWith(1, {
      script_id: 1, mode: 'headless', variables: { kw: '手机' }, auth_state_id: 3,
    })
    expect(mocks.subscribe).toHaveBeenCalledWith(5, expect.any(Function))
  })

  it('批量队列跨脚本变量隔离:甲填的 kw 不得传给未声明变量的乙', async () => {
    vi.useFakeTimers()
    const jia = mkScript({ id: 1, name: '脚本甲', variables: [{ name: 'kw', default: '手机', desc: '搜索关键词' }] })
    const yi = mkScript({ id: 2, name: '脚本乙' })
    const w = mountDialog({ projectId: 1, queue: [{ script: jia, mode: 'headless' }, { script: yi, mode: 'headless' }] })
    await flushPromises()
    await w.findAll('button').find((b) => b.text().includes('开始执行本脚本'))!.trigger('click')
    await flushPromises()
    expect(mocks.create).toHaveBeenNthCalledWith(1, 1, {
      script_id: 1, mode: 'headless', variables: { kw: '手机' }, auth_state_id: undefined,
    })
    mocks.fire({ type: 'done', status: 'completed', summary: { total: 0, passed: 0, failed: 0, duration_ms: 1 } })
    await flushPromises()
    await vi.advanceTimersByTimeAsync(800) // 甲 done 后的间隔
    await flushPromises()
    expect(mocks.create).toHaveBeenNthCalledWith(2, 1, {
      script_id: 2, mode: 'headless', variables: {}, auth_state_id: undefined, // 探针断言:乙收不到甲的 kw
    })
    expect(w.text()).toContain('第 2/2 个:脚本乙')
  })

  it('snapshot 终态重放:run 建连前已失败时按快照收尾、断流并解阻塞队列,迟到 done 不覆盖结论', async () => {
    vi.useFakeTimers()
    const w = mountDialog({
      projectId: 1,
      queue: [{ script: mkScript({ id: 1, name: '脚本甲' }), mode: 'headless' },
              { script: mkScript({ id: 2, name: '脚本乙' }), mode: 'headless' }],
    })
    await flushPromises()
    // 真实契约(ui_runs.py run_events):先发握手 status,再发 snapshot{status,step_results,error,steps_*} 后即 return
    mocks.fire({ type: 'status', status: 'failed' })
    mocks.fire({
      type: 'snapshot', status: 'failed', error: '浏览器启动失败: 快照重放',
      step_results: [], steps_total: 0, steps_passed: 0, steps_failed: 0,
    })
    await flushPromises()
    expect(w.text()).toContain('浏览器启动失败: 快照重放')
    expect(w.find('.summary').classes()).toContain('bad') // 失败摘要用危险色(M-3)
    expect(mocks.close).toHaveBeenCalled() // 终态即断流
    mocks.fire({ type: 'done', status: 'completed', summary: { total: 3, passed: 3, failed: 0, duration_ms: 5 } })
    await flushPromises()
    expect(w.text()).not.toContain('通过 3/3') // 迟到 done 不覆盖 snapshot 结论(M-1)
    await vi.advanceTimersByTimeAsync(800)
    await flushPromises()
    expect(mocks.create).toHaveBeenCalledTimes(2) // 队列已解阻塞,继续跑下一个
    expect(w.text()).toContain('第 2/2 个:脚本乙')
  })

  it('批量跑完停汇总页:不自动关框,出现「全部执行完毕」与关闭按钮,手动关才 emit closed(拍板落地)', async () => {
    vi.useFakeTimers()
    const w = mountDialog({ projectId: 1, queue: [{ script: mkScript(), mode: 'headless' }] })
    await flushPromises()
    mocks.fire({ type: 'done', status: 'completed', summary: { total: 1, passed: 1, failed: 0, duration_ms: 100 } })
    await flushPromises()
    await vi.advanceTimersByTimeAsync(900) // 越过脚本间隔:过去在这里自动关框
    await flushPromises()
    expect(w.text()).toContain('全部执行完毕')
    expect(w.emitted('closed')).toBeFalsy() // 停在汇总页
    await w.findAll('button').find((b) => b.text().trim() === '关闭')!.trigger('click')
    await flushPromises()
    expect(w.emitted('closed')).toBeTruthy()
  })

  it('强制结束:确认后调 force-finish,本地按「执行异常」收尾并继续队列(需求2)', async () => {
    vi.useFakeTimers()
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue({} as never)
    const s1 = mkScript({ id: 1, name: '脚本甲' })
    const s2 = mkScript({ id: 2, name: '脚本乙' })
    const w = mountDialog({ projectId: 1, queue: [{ script: s1, mode: 'headless' }, { script: s2, mode: 'headless' }] })
    await flushPromises()
    mocks.fire({ type: 'step_start', index: 0 }) // 甲执行中
    await flushPromises()
    await w.findAll('button').find((b) => b.text().includes('强制结束'))!.trigger('click')
    await flushPromises()
    expect(mocks.forceFinish).toHaveBeenCalledWith(5)
    expect(w.text()).toContain('执行异常 · 用户强制结束')
    await vi.advanceTimersByTimeAsync(900) // 放行后队列继续下一个
    await flushPromises()
    expect(mocks.create).toHaveBeenCalledTimes(2) // 乙接着跑
  })

  it('执行中卸载组件:断流且队列不再推进,无异常抛出', async () => {
    vi.useFakeTimers()
    const w = mountDialog({
      projectId: 1,
      queue: [{ script: mkScript(), mode: 'headless' }, { script: mkScript({ id: 2, name: '脚本乙' }), mode: 'headless' }],
    })
    await flushPromises()
    mocks.fire({ type: 'step_start', index: 0 })
    expect(() => w.unmount()).not.toThrow() // 非 @close 的卸载路径同样走 abortAll
    expect(mocks.close).toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(mocks.create).toHaveBeenCalledTimes(1) // 卸载后不再创建后续执行
  })
})
