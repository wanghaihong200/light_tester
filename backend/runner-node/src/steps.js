// runner-node/src/steps.js
// 全动作映射:AI 步走 agent(Midscene),选择器步走 page(仅 web)。
// 渲染语义与后端 app/ui_automation/dsl.py 的 render_text 保持一致。

const VAR = /\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}/g;

export function renderText(v, vars) {
  if (typeof v !== 'string') return v;
  return v.replace(VAR, (m, n) => (Object.hasOwn(vars, n) ? String(vars[n]) : m));
}

export function renderParams(params, vars) {
  const out = {};
  for (const [k, v] of Object.entries(params || {})) out[k] = renderText(v, vars);
  return out;
}

function pageLocator(page, c) {
  if (c.strategy === 'test_id') return page.getByTestId(c.value);
  if (c.strategy === 'role') return page.getByRole(c.role, { name: c.name });
  if (c.strategy === 'placeholder') return page.getByPlaceholder(c.value);
  if (c.strategy === 'label') return page.getByLabel(c.value);
  if (c.strategy === 'text') return page.getByText(c.value);
  return page.locator(c.value);
}

async function locate(page, loc) {
  // primary→fallbacks 顺序取第一个命中;全未命中回退 primary(让超时报错),与 Python 路径一致
  const cands = [loc, ...(loc.fallbacks || [])].filter((c) => c && c.strategy);
  let primary = null;
  for (const c of cands) {
    const l = pageLocator(page, c);
    if (!primary) primary = l;
    if ((await l.count()) > 0) return l.first();
  }
  return (primary || pageLocator(page, loc)).first();
}

const norm = (s) => String(s).split(/\s+/).filter(Boolean).join(' ');

export async function runStep({ page, agent, step, vars }) {
  const p = renderParams(step.params || {}, vars);
  const a = step.action;
  if (a === 'set_var') { vars[p.name] = p.value; return { status: 'passed' }; }
  if (a === 'wait') { await new Promise((r) => setTimeout(r, Math.min(p.ms, 30000))); return { status: 'passed' }; }
  if (a.startsWith('ai_')) {
    if (!agent) throw new Error(`AI 动作 ${a} 需要 agent(仅 Node 路径)`);
    switch (a) {
      case 'ai_tap': await agent.aiTap(p.target); break;
      case 'ai_input':
        if (p.target) await agent.aiInput(p.target, { value: p.text });
        else await agent.aiAct(`在当前焦点输入 "${p.text}"`);
        break;
      case 'ai_scroll': await agent.aiScroll(undefined, { direction: p.direction, scrollType: 'once' }); break;
      case 'ai_wait': await agent.aiWaitFor(p.assertion, p.timeout_ms ? { timeoutMs: p.timeout_ms } : undefined); break;
      case 'ai_assert': await agent.aiAssert(p.assertion); break;
      case 'ai_extract': vars[p.name] = await agent.aiString(`提取: ${p.target}`); break;
      default: throw new Error(`未知 AI 动作 ${a}`);
    }
    return { status: 'passed' };
  }
  if (!page) throw new Error(`选择器动作 ${a} 仅支持 web 端`);
  if (a === 'goto') { await page.goto(p.url, { waitUntil: 'domcontentloaded' }); return { status: 'passed' }; }
  if (a === 'scroll') { await page.mouse.wheel(p.dx, p.dy); return { status: 'passed' }; }
  const SELECTOR_ACTIONS = ['click', 'fill', 'press', 'select_option', 'assert_visible', 'assert_exists', 'assert_text'];
  if (!SELECTOR_ACTIONS.includes(a)) throw new Error(`未知动作 ${a}`);
  if (!step.locator) throw new Error(`动作 ${a} 缺 locator`);
  const el = await locate(page, step.locator);
  switch (a) {
    case 'click': await el.click(); break;
    case 'fill': await el.fill(p.text); break;
    case 'press': await el.press(p.key); break;
    case 'select_option': await el.selectOption(p.value); break;
    case 'assert_visible':
      if (!(await el.isVisible())) return { status: 'failed', error: `元素不可见: ${JSON.stringify(step.locator)}` };
      break;
    case 'assert_exists':
      if ((await el.count()) === 0) return { status: 'failed', error: `元素不存在: ${JSON.stringify(step.locator)}` };
      break;
    case 'assert_text': {
      const actual = await el.innerText();
      const mode = p.mode || 'contains';
      const ok = mode === 'equals' ? norm(actual) === norm(p.text) : norm(actual).includes(norm(p.text));
      if (!ok) return { status: 'failed', error: `文本不匹配(${mode}): 期望[${p.text}] 实际[${String(actual).trim().slice(0, 120)}]` };
      break;
    }
    default: throw new Error(`未知动作 ${a}`);
  }
  return { status: 'passed' };
}
