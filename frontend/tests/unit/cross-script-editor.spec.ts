import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it } from 'vitest'
import type { UiScript, UiScriptDoc, UiStep } from '../../src/types'

// 编辑器不发请求(save 由父组件落库),无需 mock API
import CrossScriptEditor from '../../src/components/crossauto/CrossScriptEditor.vue'

function mkScript(opts: {
  id?: number; name?: string; target?: 'web' | 'android' | 'harmony'
  launch?: string; steps?: UiStep[]
} = {}): UiScript {
  const target = opts.target ?? 'web'
  const meta: UiScript['script']['meta'] = { start_url: target === 'web' ? 'https://x' : '', target }
  if (opts.launch) meta.launch_target = opts.launch
  return {
    id: opts.id ?? 1,
    project_id: 1,
    name: opts.name ?? 'AI冒烟',
    description: null,
    script: { version: 2, meta, variables: [], steps: opts.steps ?? [] },
    created_at: '2026-09-05T10:00:00',
    updated_at: '2026-09-05T10:00:00',
  }
}

function mountEditor(script: UiScript | null, crossScripts: UiScript[] = []) {
  // 真实使用是「弹框先挂、visible 翻 true 时回填表单」,这里同样以 setProps 触发
  return mount(CrossScriptEditor, {
    props: { visible: false, projectId: 1, script, crossScripts },
    global: { plugins: [ElementPlus] },
  })
}

async function open(w: ReturnType<typeof mountEditor>) {
  await w.setProps({ visible: true })
  await flushPromises()
}

const btn = (w: ReturnType<typeof mountEditor>, text: string) =>
  w.findAll('button').find((b) => b.text().trim() === text)!

function lastPayload(w: ReturnType<typeof mountEditor>) {
  return w.emitted('save')![0][0] as { name: string; description: string | null; script: UiScriptDoc }
}

beforeEach(() => {
  document.body.textContent = '' // 清掉上一例遗留在 body 的弹层残留
})

describe('CrossScriptEditor', () => {
  it('① ai_tap 缺 target 时点保存不 emit save,并展示校验信息', async () => {
    const w = mountEditor(mkScript({ steps: [{ id: 's1', action: 'ai_tap', params: {} }] }))
    await open(w)
    await btn(w, '保存').trigger('click')
    await flushPromises()
    expect(w.emitted('save')).toBeFalsy()
    expect(w.text()).toContain('缺 target')
  })

  it('② 填全后 emit save:name/description/script,version=2 且 meta.target 与所选端一致', async () => {
    const w = mountEditor(mkScript({ steps: [{ id: 's1', action: 'ai_tap', params: { target: '登录按钮' } }] }))
    await open(w)
    await btn(w, '保存').trigger('click')
    await flushPromises()
    const p = lastPayload(w)
    expect(p.name).toBe('AI冒烟')
    expect(p.description).toBeNull()
    expect(p.script.version).toBe(2)
    expect(p.script.meta.target).toBe('web') // 默认选中 Web 端
    expect(p.script.meta.start_url).toBe('https://x')
    expect(p.script.steps[0]).toEqual({ id: 's1', action: 'ai_tap', params: { target: '登录按钮' } })
  })

  it('② 补充:编辑 Android 脚本时 radio 预选 android,保存 meta.target/launch_target 与所选端一致', async () => {
    const w = mountEditor(mkScript({
      target: 'android', launch: 'com.example.app',
      steps: [{ id: 's1', action: 'ai_tap', params: { target: '登录按钮' } }],
    }))
    await open(w)
    await btn(w, '保存').trigger('click')
    await flushPromises()
    const p = lastPayload(w)
    expect(p.script.meta.target).toBe('android')
    expect(p.script.meta.launch_target).toBe('com.example.app')
    expect(p.script.meta.start_url).toBeUndefined() // 非 web 端不写 start_url
  })

  it('③ run_sub 的 script_id 下拉选项来自跨端脚本列表且排除自身', async () => {
    const self = mkScript({ id: 1, name: '主脚本', steps: [{ id: 's1', action: 'run_sub', params: {} }] })
    const w = mountEditor(self, [self, mkScript({ id: 2, name: '子脚本A' }), mkScript({ id: 3, name: '子脚本B' })])
    await open(w)
    const values = w.findAllComponents({ name: 'ElOption' }).map((o) => String(o.props('value')))
    expect(values).toContain('2')
    expect(values).toContain('3')
    expect(values).not.toContain('1') // 排除自身
    expect(values).not.toContain('主脚本')
    expect(w.text()).toContain('子脚本A')
  })

  it('补充:ai_scroll direction 必须是 up/down/left/right;空值按缺参提示', async () => {
    const w = mountEditor(mkScript({ steps: [{ id: 's1', action: 'ai_scroll', params: { direction: 'side' } }] }))
    await open(w)
    expect(w.text()).toContain('direction 必须是 up/down/left/right')
    // 精确找到 direction 下拉(按当前值定位,避免命中同屏的动作下拉)
    const dirSel = w.findAllComponents({ name: 'ElSelect' }).find((s) => s.props('modelValue') === 'side')!
    await dirSel.vm.$emit('update:modelValue', '')
    await flushPromises()
    expect(w.text()).toContain('缺 direction')
    await btn(w, '保存').trigger('click')
    expect(w.emitted('save')).toBeFalsy()
  })

  it('补充:run_sub 引用脚本自身时报「不能引用脚本自身」且不 emit save', async () => {
    const w = mountEditor(mkScript({ id: 1, steps: [{ id: 's1', action: 'run_sub', params: { script_id: '1' } }] }))
    await open(w)
    expect(w.text()).toContain('不能引用脚本自身')
    await btn(w, '保存').trigger('click')
    expect(w.emitted('save')).toBeFalsy()
  })
})
