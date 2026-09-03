# app/ui_automation/injected.py
"""注入页面的 JS:①原始事件采集 ②悬浮工具条(断言模式切换)。
采集只读不拦截(不 preventDefault),被测页面行为不变。"""

COLLECT_JS = r"""
(() => {
  if (window.__tcCollectInstalled) return; window.__tcCollectInstalled = true;
  const desc = (el) => ({
    tag: el.tagName.toLowerCase(), id: el.id || '',
    name: el.getAttribute('name') || '',
    classes: String(el.className || '').split(/\s+/).filter(Boolean).slice(0, 5),
    type: el.getAttribute('type') || '', role: el.getAttribute('role') || '',
    aria_label: el.getAttribute('aria-label') || '',
    test_id: el.getAttribute('data-testid') || el.getAttribute('data-test') || '',
    placeholder: el.getAttribute('placeholder') || '',
    text: (el.innerText || '').trim().slice(0, 60),
  });
  const send = (ev) => { try { window.__tcReport(ev); } catch (e) {} };
  document.addEventListener('input', (e) => {
    const el = e.target;
    if (el && el.matches && el.matches('input,textarea'))
      send({kind: 'input', target: desc(el), value: el.value});
  }, true);
  document.addEventListener('change', (e) => {
    const el = e.target;
    if (el && el.tagName === 'SELECT') send({kind: 'change', target: desc(el), value: el.value});
  }, true);
  document.addEventListener('keydown', (e) => {
    send({kind: 'keydown', target: desc(e.target), key: e.key});
  }, true);
  document.addEventListener('click', (e) => {
    if (window.__tcAssertMode) { send({kind: 'assert_click', target: desc(e.target)}); return; }
    let el = e.target;
    const inter = el.closest && el.closest('button, a, [role=button], input, label, select');
    if (inter) el = inter;
    send({kind: 'click', target: desc(el)});
  }, true);
})();
"""

TOOLBAR_JS = r"""
(() => {
  if (window.__tcToolbar) return; window.__tcToolbar = true;
  const bar = document.createElement('div');
  bar.style.cssText = 'position:fixed;top:8px;right:8px;z-index:2147483647;background:#1f2d3d;color:#fff;'
    + 'font:13px/1.6 sans-serif;padding:8px 12px;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.3);'
    + 'display:flex;gap:8px;align-items:center;';
  const label = document.createElement('span'); label.textContent = '录制中';
  const btn = document.createElement('button'); btn.textContent = '断言模式';
  btn.style.cssText = 'border:0;border-radius:4px;padding:2px 8px;cursor:pointer;background:#409eff;color:#fff;';
  btn.onclick = (e) => {
    e.stopPropagation();
    window.__tcAssertMode = !window.__tcAssertMode;
    btn.style.background = window.__tcAssertMode ? '#e6a23c' : '#409eff';
    label.textContent = window.__tcAssertMode ? '断言模式(点元素)' : '录制中';
  };
  bar.appendChild(label); bar.appendChild(btn);
  document.documentElement.appendChild(bar);
})();
"""
