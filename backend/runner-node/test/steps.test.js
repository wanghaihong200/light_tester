import { describe, expect, it } from 'vitest';
import { renderParams, renderText, runStep } from '../src/steps.js';

function fakeAgent() {
  const calls = [];
  return {
    calls,
    async aiTap(t) { calls.push(['aiTap', t]); },
    async aiInput(t, o) { calls.push(['aiInput', t, o]); },
    async aiAct(p) { calls.push(['aiAct', p]); },
    async aiScroll(t, o) { calls.push(['aiScroll', t, o]); },
    async aiWaitFor(a, o) { calls.push(['aiWaitFor', a, o]); },
    async aiAssert(a) { calls.push(['aiAssert', a]); },
    async aiString(p) { calls.push(['aiString', p]); return 'NO.123'; },
  };
}

function fakePage(innerText = '  欢迎   回来 ') {
  const calls = [];
  const locator = (name) => {
    const el = {
      count: async () => 1,
      isVisible: async () => true,
      innerText: async () => innerText,
      click: async () => calls.push(['click', name]),
      fill: async (t) => calls.push(['fill', name, t]),
      press: async (k) => calls.push(['press', name, k]),
      selectOption: async (v) => calls.push(['select', name, v]),
      first() { return el; },
    };
    return el;
  };
  const page = {
    calls,
    getByTestId: (v) => locator(`tid:${v}`),
    getByRole: (r, o) => locator(`role:${r}:${o?.name}`),
    getByPlaceholder: (v) => locator(`ph:${v}`),
    getByLabel: (v) => locator(`label:${v}`),
    getByText: (v) => locator(`text:${v}`),
    locator: (v) => locator(`css:${v}`),
    mouse: { wheel: async (dx, dy) => calls.push(['wheel', dx, dy]) },
    goto: async (u) => calls.push(['goto', u]),
  };
  return page;
}

describe('renderText', () => {
  it('有则替换无则保留;非字符串原样', () => {
    const vars = { u: 'admin' };
    expect(renderText('{{u}}/x', vars)).toBe('admin/x');
    expect(renderText('{{missing}}', vars)).toBe('{{missing}}');
    expect(renderText(5, vars)).toBe(5);
    expect(renderParams({ a: '{{u}}', b: 3 }, vars)).toEqual({ a: 'admin', b: 3 });
  });
});

describe('runStep · AI 步', () => {
  it('ai_tap/ai_scroll/ai_assert/ai_wait 映射', async () => {
    const agent = fakeAgent();
    const run = (action, params) => runStep({ agent, step: { id: 's', action, params }, vars: {} });
    await run('ai_tap', { target: '登录按钮' });
    await run('ai_scroll', { direction: 'down' });
    await run('ai_assert', { assertion: '显示工作台' });
    await run('ai_wait', { assertion: '出现首页', timeout_ms: 8000 });
    expect(agent.calls).toEqual([
      ['aiTap', '登录按钮'],
      ['aiScroll', undefined, { direction: 'down', scrollType: 'once' }],
      ['aiAssert', '显示工作台'],
      ['aiWaitFor', '出现首页', { timeoutMs: 8000 }],
    ]);
  });

  it('ai_input 有 target 走 aiInput、无 target 走 aiAct;ai_extract 写变量', async () => {
    const agent = fakeAgent();
    const vars = {};
    await runStep({ agent, step: { id: '1', action: 'ai_input', params: { target: '用户名框', text: '{{u}}' } }, vars: { u: 'admin' } });
    await runStep({ agent, step: { id: '2', action: 'ai_input', params: { text: 'ok' } }, vars });
    await runStep({ agent, step: { id: '3', action: 'ai_extract', params: { target: '订单编号', name: 'no' } }, vars });
    expect(agent.calls[0]).toEqual(['aiInput', '用户名框', { value: 'admin' }]);
    expect(agent.calls[1][0]).toBe('aiAct');
    expect(vars.no).toBe('NO.123');
  });

  it('set_var 影响后续步渲染', async () => {
    const agent = fakeAgent();
    const vars = {};
    await runStep({ agent, step: { id: '1', action: 'set_var', params: { name: 'k', value: 'v1' } }, vars });
    await runStep({ agent, step: { id: '2', action: 'ai_tap', params: { target: '按钮{{k}}' } }, vars });
    expect(agent.calls[0]).toEqual(['aiTap', '按钮v1']);
  });
});

describe('runStep · 选择器步(仅 web)', () => {
  it('goto/wheel/定位族与断言', async () => {
    const page = fakePage();
    const run = (action, extra) => runStep({ page, step: { id: 's', action, ...extra }, vars: {} });
    await run('goto', { params: { url: 'https://x' } });
    await run('scroll', { params: { dx: 0, dy: 300 } });
    await run('click', { locator: { strategy: 'role', role: 'button', name: '登录' } });
    await run('fill', { locator: { strategy: 'css', value: '#u' }, params: { text: 'admin' } });
    await run('press', { locator: { strategy: 'css', value: '#u' }, params: { key: 'Enter' } });
    await run('select_option', { locator: { strategy: 'css', value: '#s' }, params: { value: 'a' } });
    expect(page.calls).toEqual([
      ['goto', 'https://x'], ['wheel', 0, 300], ['click', 'role:button:登录'],
      ['fill', 'css:#u', 'admin'], ['press', 'css:#u', 'Enter'], ['select', 'css:#s', 'a'],
    ]);
  });

  it('assert_text 空白归一化 contains/equals 与失败语义', async () => {
    const page = fakePage();
    const ok = await runStep({ page, step: { id: 's', action: 'assert_text', locator: { strategy: 'text', value: '欢迎' }, params: { text: '欢迎 回来', mode: 'contains' } }, vars: {} });
    const bad = await runStep({ page, step: { id: 's', action: 'assert_text', locator: { strategy: 'text', value: '欢迎' }, params: { text: '欢迎回来', mode: 'equals' } }, vars: {} });
    expect(ok.status).toBe('passed');
    expect(bad.status).toBe('failed');
    expect(bad.error).toContain('equals');
  });

  it('未知动作抛错', async () => {
    await expect(runStep({ page: fakePage(), agent: fakeAgent(), step: { id: 's', action: 'teleport', params: {} }, vars: {} })).rejects.toThrow(/未知/);
  });
});
