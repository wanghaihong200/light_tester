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
  // 滚动采集(主文档):滚轮/拖滚动条/PgDn 统一表现为 scroll 事件。增量累计 + 400ms 防抖
  // 合并为一条;其他交互事件先结算挂起的滚动,保证「先滚后点」的步骤顺序不颠倒。
  let accX = 0, accY = 0, sTimer = null, lastX = window.scrollX, lastY = window.scrollY;
  const settleScroll = () => {
    if (sTimer) { clearTimeout(sTimer); sTimer = null; }
    if (Math.abs(accX) >= 5 || Math.abs(accY) >= 5)
      send({kind: 'scroll', dx: Math.round(accX), dy: Math.round(accY)});
    accX = 0; accY = 0;
  };
  document.addEventListener('scroll', (e) => {
    if (e.target !== document && e.target !== document.documentElement) return; // 一期只录主文档滚动
    const x = window.scrollX, y = window.scrollY;
    accX += x - lastX; accY += y - lastY; lastX = x; lastY = y;
    if (sTimer) clearTimeout(sTimer);
    sTimer = setTimeout(settleScroll, 400);
  }, true);
  document.addEventListener('input', (e) => {
    settleScroll();
    const el = e.target;
    if (el && el.matches && el.matches('input,textarea'))
      send({kind: 'input', target: desc(el), value: el.value});
  }, true);
  document.addEventListener('change', (e) => {
    settleScroll();
    const el = e.target;
    if (el && el.tagName === 'SELECT') send({kind: 'change', target: desc(el), value: el.value});
  }, true);
  document.addEventListener('keydown', (e) => {
    settleScroll();
    send({kind: 'keydown', target: desc(e.target), key: e.key});
  }, true);
  document.addEventListener('click', (e) => {
    if (window.__tcAssertMode) { send({kind: 'assert_click', target: desc(e.target)}); return; }
    settleScroll();
    try { window.__tcClickFx && window.__tcClickFx(e.clientX, e.clientY); } catch (err) {}
    let el = e.target;
    const inter = el.closest && el.closest('button, a, [role=button], input, label, select');
    if (inter) el = inter;
    send({kind: 'click', target: desc(el)});
  }, true);
})();
"""

# 点击特效(录制预览用):点击坐标处红色鼠标光标贴纸(Midscene 风格,红填充白描边)+ 扩散圆环,
# 随 CDP 截屏自然进预览帧。寿命 1.6s:预览帧间隔 0.6s,保证至少 2 帧拍到(0.9s 短命版真机几乎看不见)。
# 只在 with_toolbar(录制)会话注入;登录态采集会话无预览,不需要。
# keyframes/贴纸惰性注入到首次点击时(init script 跑在 document-start,DOM 尚不存在)。
CLICK_FX_JS = r"""
(() => {
  if (window.__tcClickFx) return;
  const CURSOR_SVG = "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E"
    + "%3Cpath d='M4 2 L4 19 L8.8 15 L11.6 21 L14.6 19.6 L11.8 13.7 L18 13.7 Z' "
    + "fill='%23ff4d4f' stroke='%23fff' stroke-width='1.5' stroke-linejoin='round'/%3E%3C/svg%3E\")";
  window.__tcClickFx = (x, y) => {
    if (!document.getElementById('__tcFxStyle')) {
      const style = document.createElement('style');
      style.id = '__tcFxStyle';
      style.textContent = '@keyframes __tcFxRing{0%{transform:scale(.35);opacity:.95}'
        + '70%{opacity:.7}100%{transform:scale(1.7);opacity:0}}'
        + '@keyframes __tcFxCursor{0%{transform:scale(.8);opacity:1}75%{opacity:1}100%{opacity:0}}';
      (document.head || document.documentElement).appendChild(style);
    }
    const part = (css, anim) => {
      const el = document.createElement('div');
      el.setAttribute('data-tc-fx', '');
      el.style.cssText = 'position:fixed;pointer-events:none;z-index:2147483647;' + css;
      el.style.animation = anim;
      (document.body || document.documentElement).appendChild(el);
      el.addEventListener('animationend', () => el.remove());
      setTimeout(() => el.remove(), 2600);  // 兜底:动画不触发(如页面隐藏)时也不残留
    };
    // 红色光标贴纸:箭头尖端(≈5,3,按 34px 等比)对准点击点
    part('left:' + (x - 5) + 'px;top:' + (y - 3) + 'px;width:34px;height:34px;'
      + 'background:no-repeat center/contain ' + CURSOR_SVG + ';',
      '__tcFxCursor 1.6s ease-out forwards');
    // 扩散圆环:强调点击区域
    part('left:' + (x - 14) + 'px;top:' + (y - 14) + 'px;width:28px;height:28px;'
      + 'border:3px solid #ff4d4f;border-radius:50%;box-shadow:0 0 6px rgba(255,77,79,.6);',
      '__tcFxRing .9s ease-out forwards');
  };
})();
"""

TOOLBAR_JS = r"""
(() => {
  if (window.__tcToolbar) return; window.__tcToolbar = true;
  const build = () => {
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
    document.body.appendChild(bar);
  };
  // init script 跑在 document-start,documentElement/body 尚不存在,直接挂载会抛错
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', build);
  else build();
})();
"""
