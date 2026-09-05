import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it, vi, beforeEach } from 'vitest'

// ---- mock api modules ----
const jobsApi = vi.hoisted(() => {
  const closeFn = vi.fn()
  return {
    listJobs: vi.fn().mockResolvedValue([
      {
        id: 10,
        project_id: 1,
        document_id: 3,
        target_module_id: 5,
        job_type: 'generate',
        status: 'pending' as const,
        model: 'gpt-4',
        input_tokens: 0,
        output_tokens: 0,
        cost_usd: 0,
        error: null,
        created_at: '2026-08-16T10:00:00',
        document_name: '需求文档.md',
        output_text: null,
        thinking_text: null,
        started_at: null,
        finished_at: null,
      },
      {
        id: 9,
        project_id: 1,
        document_id: 2,
        target_module_id: 4,
        job_type: 'generate',
        status: 'completed' as const,
        model: 'gpt-4',
        input_tokens: 1200,
        output_tokens: 800,
        cost_usd: 0.05,
        error: null,
        created_at: '2026-08-15T10:00:00',
        document_name: 'API文档.md',
        output_text: null,
        thinking_text: null,
        started_at: null,
        finished_at: null,
      },
    ]),
    createJob: vi.fn().mockResolvedValue({
      id: 11,
      project_id: 1,
      document_id: 3,
      target_module_id: 5,
      job_type: 'generate',
      status: 'pending' as const,
      model: 'gpt-4',
      input_tokens: 0,
      output_tokens: 0,
      cost_usd: 0,
      error: null,
      created_at: '2026-08-16T11:00:00',
      document_name: '需求文档.md',
      thinking_text: null,
    }),
    getJob: vi.fn(),
    subscribeJobEvents: vi.fn().mockReturnValue(vi.fn()), // returns close function
  }
})
vi.mock('../../src/api/jobs', () => jobsApi)

const docsApi = vi.hoisted(() => ({
  listDocuments: vi.fn().mockResolvedValue([
    { id: 3, filename: '需求文档.md', uploaded_at: '2026-08-15T09:00:00' },
    { id: 2, filename: 'API文档.md', uploaded_at: '2026-08-14T09:00:00' },
  ]),
}))
vi.mock('../../src/api/documents', () => docsApi)

const treeApi = vi.hoisted(() => ({
  fetchTree: vi.fn().mockResolvedValue([
    { id: 5, name: '模块A', children: [], feature_points: [] },
    { id: 4, name: '模块B', children: [{ id: 6, name: '子模块B1', children: [], feature_points: [] }], feature_points: [] },
  ]),
}))
vi.mock('../../src/api/tree', () => treeApi)

import JobsPane from '../../src/components/JobsPane.vue'

describe('JobsPane', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('加载并渲染任务列表', async () => {
    const wrapper = mount(JobsPane, { props: { projectId: 1 }, global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(jobsApi.listJobs).toHaveBeenCalledWith(1)
    const text = wrapper.text()
    expect(text).toContain('10')
    expect(text).toContain('需求文档.md')
    expect(text).toContain('API文档.md')
    expect(text).toContain('待执行')
    expect(text).toContain('已完成')
  })

  it('发起对话框提交调 createJob', async () => {
    const wrapper = mount(JobsPane, { props: { projectId: 1 }, global: { plugins: [ElementPlus] } })
    await flushPromises()

    // 点击「+ 发起生成」按钮
    await wrapper.find('button').trigger('click')
    await flushPromises()

    // 对话框应出现
    expect(wrapper.find('.el-dialog').exists()).toBe(true)

    // 设置两个 el-select 的值
    const selects = wrapper.findAllComponents({ name: 'ElSelect' })
    expect(selects.length).toBeGreaterThanOrEqual(2)
    await selects[0].vm.$emit('update:modelValue', 3)   // documentId
    await selects[1].vm.$emit('update:modelValue', 5)    // targetModuleId
    await flushPromises()

    // 找到并点击提交按钮(对话框内的「发起」按钮，精确匹配避免命中工具栏的「+ 发起生成」)
    const btns = wrapper.findAll('button')
    for (const btn of btns) {
      if (btn.text().trim() === '发起') {
        await btn.trigger('click')
        break
      }
    }
    await flushPromises()

    // 默认任务类型 case_generation → createJob payload 带 jobType
    expect(jobsApi.createJob).toHaveBeenCalledWith(1, { documentId: 3, targetModuleId: 5, jobType: 'case_generation' })
    // 自动打开该任务的进度抽屉 → subscribeJobEvents 被调用
    expect(jobsApi.subscribeJobEvents).toHaveBeenCalledWith(11, expect.any(Function))
  })

  it('api_generation 无 git_repo_url 时 toast 不发请求', async () => {
    const wrapper = mount(JobsPane, {
      props: { projectId: 1, project: { id: 1, name: 'p', git_repo_url: null } as any },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()

    // 打开对话框
    await wrapper.find('button').trigger('click')
    await flushPromises()

    // 切换任务类型为接口生成:el-radio-group 触发 update:modelValue
    const radioGroup = wrapper.findComponent({ name: 'ElRadioGroup' })
    await radioGroup.vm.$emit('update:modelValue', 'api_generation')
    await flushPromises()

    // 选文档 + 选模块
    const selects = wrapper.findAllComponents({ name: 'ElSelect' })
    await selects[0].vm.$emit('update:modelValue', 3)
    await selects[1].vm.$emit('update:modelValue', 5)
    await flushPromises()

    // 点击「发起」
    const btns = wrapper.findAll('button')
    for (const btn of btns) {
      if (btn.text().trim() === '发起') {
        await btn.trigger('click')
        break
      }
    }
    await flushPromises()

    // 不应调用 createJob(因 git_repo_url 缺失)
    expect(jobsApi.createJob).not.toHaveBeenCalled()
  })

  it('api_generation 有 git_repo_url 时 payload 带 job_type=api_generation', async () => {
    const wrapper = mount(JobsPane, {
      props: { projectId: 1, project: { id: 1, name: 'p', git_repo_url: 'https://x' } as any },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()

    await wrapper.find('button').trigger('click')
    await flushPromises()

    const radioGroup = wrapper.findComponent({ name: 'ElRadioGroup' })
    await radioGroup.vm.$emit('update:modelValue', 'api_generation')
    await flushPromises()

    const selects = wrapper.findAllComponents({ name: 'ElSelect' })
    await selects[0].vm.$emit('update:modelValue', 3)
    await selects[1].vm.$emit('update:modelValue', 5)
    await flushPromises()

    const btns = wrapper.findAll('button')
    for (const btn of btns) {
      if (btn.text().trim() === '发起') {
        await btn.trigger('click')
        break
      }
    }
    await flushPromises()

    expect(jobsApi.createJob).toHaveBeenCalledWith(1, { documentId: 3, targetModuleId: 5, jobType: 'api_generation' })
  })

  it('打开发起弹窗时重拉文档与模块列表(Bug1 回归)', async () => {
    const wrapper = mount(JobsPane, { props: { projectId: 1 }, global: { plugins: [ElementPlus] } })
    await flushPromises()
    // onMounted 各拉 1 次
    expect(docsApi.listDocuments).toHaveBeenCalledTimes(1)
    expect(treeApi.fetchTree).toHaveBeenCalledTimes(1)

    // 点击「+ 发起生成」打开弹窗 → 再次拉取(新上传文档立即可见)
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(docsApi.listDocuments).toHaveBeenCalledTimes(2)
    expect(treeApi.fetchTree).toHaveBeenCalledTimes(2)
  })

  it('手输模块名 payload 带 target_module_name', async () => {
    const wrapper = mount(JobsPane, { props: { projectId: 1 }, global: { plugins: [ElementPlus] } })
    await flushPromises()

    await wrapper.find('button').trigger('click')
    await flushPromises()

    const selects = wrapper.findAllComponents({ name: 'ElSelect' })
    await selects[0].vm.$emit('update:modelValue', 3)          // documentId
    await selects[1].vm.$emit('update:modelValue', '支付模块')   // allow-create 手输入 → string
    await flushPromises()

    const btns = wrapper.findAll('button')
    for (const btn of btns) {
      if (btn.text().trim() === '发起') {
        await btn.trigger('click')
        break
      }
    }
    await flushPromises()

    expect(jobsApi.createJob).toHaveBeenCalledWith(1, {
      documentId: 3,
      targetModuleName: '支付模块',
      jobType: 'case_generation',
    })
  })

  it('模块留空可发起,payload 不带模块字段', async () => {
    const wrapper = mount(JobsPane, { props: { projectId: 1 }, global: { plugins: [ElementPlus] } })
    await flushPromises()

    await wrapper.find('button').trigger('click')
    await flushPromises()

    // 只选文档,模块保持空(发起按钮 disabled 只看文档)
    const selects = wrapper.findAllComponents({ name: 'ElSelect' })
    await selects[0].vm.$emit('update:modelValue', 3)
    await flushPromises()

    const submitBtn = wrapper.findAll('button').find(b => b.text().trim() === '发起')
    expect(submitBtn).toBeTruthy()
    expect((submitBtn!.element as HTMLButtonElement).disabled).toBe(false)
    await submitBtn!.trigger('click')
    await flushPromises()

    expect(jobsApi.createJob).toHaveBeenCalledWith(1, { documentId: 3, jobType: 'case_generation' })
  })

  it('终态任务详情连 SSE 并渲染 snapshot 回放', async () => {
    let onEventCb: ((e: any) => void) | null = null
    jobsApi.subscribeJobEvents.mockImplementation((_id: number, cb: (e: any) => void) => { onEventCb = cb; return vi.fn() })
    const wrapper = mount(JobsPane, { props: { projectId: 1 }, global: { plugins: [ElementPlus] } })
    await flushPromises()
    const detailBtns = wrapper.findAll('button').filter(b => b.text().trim() === '详情')
    await detailBtns[1].trigger('click')  // row1 = completed
    await flushPromises()
    expect(jobsApi.subscribeJobEvents).toHaveBeenCalled()  // ← 原用例断言 not:反转
    onEventCb!({
      type: 'snapshot', status: 'completed', error: null,
      output_text: '历史流式输出全文', thinking_text: null, tool_trace: null,
      input_tokens: 11, output_tokens: 22,
      files_count: 0, staged_count: 3,
    })
    await flushPromises()
    expect(wrapper.text()).toContain('历史流式输出全文')
    expect(wrapper.text()).toContain('暂无思考记录')
    expect(wrapper.find('.stage-text').text()).toContain('生成 3 条暂存用例')
  })

  it('抽屉关闭断开', async () => {
    const closeFn = vi.fn()
    jobsApi.subscribeJobEvents.mockReturnValue(closeFn)

    const wrapper = mount(JobsPane, { props: { projectId: 1 }, global: { plugins: [ElementPlus] } })
    await flushPromises()

    // 点击第一个「详情」按钮(pending 任务的详情按钮)
    const detailBtns = wrapper.findAll('button').filter(b => b.text().trim() === '详情')
    expect(detailBtns.length).toBeGreaterThanOrEqual(1)
    await detailBtns[0].trigger('click')
    await flushPromises()

    // subscribeJobEvents 已被调用
    expect(jobsApi.subscribeJobEvents).toHaveBeenCalled()

    // 关闭抽屉
    const drawer = wrapper.findComponent({ name: 'ElDrawer' })
    drawer.vm.$emit('close')
    await flushPromises()

    expect(closeFn).toHaveBeenCalled()
  })

  it('SSE stage 事件渲染到详情抽屉', async () => {
    // 让 subscribeJobEvents 立即回调 onEvent
    let onEventCb: ((e: any) => void) | null = null
    jobsApi.subscribeJobEvents.mockImplementation((_id: number, cb: (e: any) => void) => {
      onEventCb = cb
      return vi.fn()
    })

    const wrapper = mount(JobsPane, { props: { projectId: 1 }, global: { plugins: [ElementPlus] } })
    await flushPromises()

    // 点击 pending 任务详情 → 打开抽屉并订阅 SSE
    const detailBtns = wrapper.findAll('button').filter(b => b.text().trim() === '详情')
    await detailBtns[0].trigger('click')
    await flushPromises()

    expect(onEventCb).toBeTruthy()

    // 模拟后端推送 stage=compiling
    onEventCb!({ type: 'stage', stage: 'compiling' })
    await flushPromises()
    expect(wrapper.find('.stage-text').text()).toContain('编译中')

    // 模拟 thinking_delta 直播追加
    onEventCb!({ type: 'thinking_delta', text: '思考片段直播' })
    await flushPromises()
    expect(wrapper.text()).toContain('思考片段直播')

    // 模拟 stage=fixing round=1
    onEventCb!({ type: 'stage', stage: 'fixing', round: 1 })
    await flushPromises()
    expect(wrapper.find('.stage-text').text()).toContain('修复第 1 轮')

    // 模拟 done.files_count(api_generation 终态)
    onEventCb!({ type: 'done', files_count: 7 })
    await flushPromises()
    expect(wrapper.find('.stage-text').text()).toContain('生成 7 个文件')

    // 模拟 done.staged_count(case_generation 终态)——重新打开抽屉
    await detailBtns[0].trigger('click')
    await flushPromises()
    onEventCb!({ type: 'done', staged_count: 3 })
    await flushPromises()
    expect(wrapper.find('.stage-text').text()).toContain('生成 3 条暂存用例')
  })

  it('列表渲染时长列(终态任务显示 finished-started)', async () => {
    jobsApi.listJobs.mockResolvedValue([
      {
        id: 9, project_id: 1, document_id: 2, target_module_id: 4, job_type: 'generate',
        status: 'completed' as const, model: 'gpt-4', input_tokens: 1200, output_tokens: 800,
        cost_usd: 0.05, error: null, created_at: '2026-08-15T10:00:00', document_name: 'API文档.md',
        output_text: null, thinking_text: null, started_at: '2026-08-18T10:00:00', finished_at: '2026-08-18T10:02:30',
      },
    ])
    const wrapper = mount(JobsPane, { props: { projectId: 1 }, global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(wrapper.text()).toContain('时长')
    expect(wrapper.text()).toContain('2分30秒')
  })

  it('终态任务详情渲染思考摘要回放(折叠面板)', async () => {
    jobsApi.listJobs.mockResolvedValue([
      {
        id: 10, project_id: 1, document_id: 3, target_module_id: 5, job_type: 'generate',
        status: 'pending' as const, model: 'gpt-4', input_tokens: 0, output_tokens: 0,
        cost_usd: 0, error: null, created_at: '2026-08-16T10:00:00', document_name: '需求文档.md',
        output_text: null, thinking_text: null, started_at: null, finished_at: null,
      },
      {
        id: 9, project_id: 1, document_id: 2, target_module_id: 4, job_type: 'generate',
        status: 'completed' as const, model: 'gpt-4', input_tokens: 1200, output_tokens: 800,
        cost_usd: 0.05, error: null, created_at: '2026-08-15T10:00:00', document_name: 'API文档.md',
        output_text: null, thinking_text: null, started_at: null, finished_at: null,
      },
    ])
    let onEventCb: ((e: any) => void) | null = null
    jobsApi.subscribeJobEvents.mockImplementation((_id: number, cb: (e: any) => void) => { onEventCb = cb; return vi.fn() })
    const wrapper = mount(JobsPane, { props: { projectId: 1 }, global: { plugins: [ElementPlus] } })
    await flushPromises()
    const detailBtns = wrapper.findAll('button').filter(b => b.text().trim() === '详情')
    await detailBtns[1].trigger('click')  // row1 = completed
    await flushPromises()
    onEventCb!({
      type: 'snapshot', status: 'completed', error: null,
      output_text: '产物全文', thinking_text: '历史思考摘要全文', tool_trace: null,
      input_tokens: 11, output_tokens: 22, files_count: 0, staged_count: 3,
    })
    await flushPromises()
    expect(wrapper.text()).toContain('思考过程')
    expect(wrapper.text()).toContain('历史思考摘要全文')
  })

  it('列表渲染创建/修改时间列(MM-dd HH:mm,未终态显示 -)', async () => {
    jobsApi.listJobs.mockResolvedValue([
      {
        id: 10, project_id: 1, document_id: 2, target_module_id: 4, job_type: 'generate',
        status: 'completed' as const, model: 'gpt-4', input_tokens: 1200, output_tokens: 800,
        cost_usd: 0.05, error: null, created_at: '2026-08-18T10:00:00', document_name: 'API文档.md',
        output_text: null, thinking_text: null, started_at: '2026-08-18T10:00:00', finished_at: '2026-08-18T10:02:30',
      },
    ])
    const wrapper = mount(JobsPane, { props: { projectId: 1 }, global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(wrapper.text()).toContain('创建时间')
    expect(wrapper.text()).toContain('修改时间')
    expect(wrapper.text()).toContain('08-18 10:00')
    expect(wrapper.text()).toContain('08-18 10:02')
  })

  it('发起弹窗填写补充指令 → payload 带 userPrompt', async () => {
    const wrapper = mount(JobsPane, { props: { projectId: 1 }, global: { plugins: [ElementPlus] } })
    await flushPromises()
    await wrapper.find('button').trigger('click')
    await flushPromises()
    const selects = wrapper.findAllComponents({ name: 'ElSelect' })
    await selects[0].vm.$emit('update:modelValue', 3)
    // 补充指令 textarea:ElSelect 内部也有 ElInput,按 type=textarea 区分
    const textarea = wrapper.findAllComponents({ name: 'ElInput' }).find(c => c.props('type') === 'textarea')
    expect(textarea).toBeTruthy()
    await textarea!.vm.$emit('update:modelValue', '只测登录,优先异常')
    await flushPromises()
    const btns = wrapper.findAll('button')
    for (const btn of btns) {
      if (btn.text().trim() === '发起') { await btn.trigger('click'); break }
    }
    await flushPromises()
    expect(jobsApi.createJob).toHaveBeenCalledWith(1, {
      documentId: 3, jobType: 'case_generation', userPrompt: '只测登录,优先异常',
    })
  })

  it('SSE tool 事件直播过程记录,snapshot 回放并覆盖', async () => {
    let onEventCb: ((e: any) => void) | null = null
    jobsApi.subscribeJobEvents.mockImplementation((_id: number, cb: (e: any) => void) => { onEventCb = cb; return vi.fn() })
    const wrapper = mount(JobsPane, { props: { projectId: 1 }, global: { plugins: [ElementPlus] } })
    await flushPromises()
    const detailBtns = wrapper.findAll('button').filter(b => b.text().trim() === '详情')
    await detailBtns[0].trigger('click')
    await flushPromises()
    onEventCb!({ type: 'tool', text: 'Read SKILL.md\n' })
    await flushPromises()
    expect(wrapper.text()).toContain('Read SKILL.md')
    expect(wrapper.text()).toContain('过程记录')
    // 终态 snapshot 回放完整过程记录(覆盖直播累积,与 thinking 同语义)
    onEventCb!({
      type: 'snapshot', status: 'completed', error: null,
      output_text: 'o', thinking_text: null, tool_trace: 'Bash mvn -q test-compile\n',
      input_tokens: 1, output_tokens: 2, files_count: 0, staged_count: 0,
    })
    await flushPromises()
    expect(wrapper.text()).toContain('Bash mvn -q test-compile')
    expect(wrapper.text()).not.toContain('Read SKILL.md')
  })

  it('无过程记录的终态 snapshot 显示空态文案', async () => {
    let onEventCb: ((e: any) => void) | null = null
    jobsApi.subscribeJobEvents.mockImplementation((_id: number, cb: (e: any) => void) => { onEventCb = cb; return vi.fn() })
    const wrapper = mount(JobsPane, { props: { projectId: 1 }, global: { plugins: [ElementPlus] } })
    await flushPromises()
    const detailBtns = wrapper.findAll('button').filter(b => b.text().trim() === '详情')
    await detailBtns[0].trigger('click')
    await flushPromises()
    onEventCb!({
      type: 'snapshot', status: 'completed', error: null,
      output_text: 'o', thinking_text: null, tool_trace: null,
      input_tokens: 1, output_tokens: 2, files_count: 0, staged_count: 0,
    })
    await flushPromises()
    expect(wrapper.text()).toContain('暂无过程记录')
  })
})
