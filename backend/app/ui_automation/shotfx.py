# app/ui_automation/shotfx.py
"""执行步骤截图的点击标示:在 JPEG 上叠画红色鼠标光标 + 扩散圆环。
纯像素后处理,与页面 DOM 无关——点击导致导航/弹层时标示依然落在截图上。
形状与 injected.CLICK_FX_JS(录制预览)同一套视觉:红填充白描边光标 + 红圈。"""
from io import BytesIO

# 与 CLICK_FX_JS 的 SVG path 同源:viewBox 24×24 的箭头(尖端 4,2 → 尾巴右下)
_CURSOR_PTS = [(4, 2), (4, 19), (8.8, 15), (11.6, 21), (14.6, 19.6), (11.8, 13.7), (18, 13.7)]
_RED = (255, 77, 79)
_WHITE = (255, 255, 255)


def overlay_click_mark(jpeg: bytes, x: float, y: float) -> bytes:
    """在截图 (x, y) 视口坐标处叠画点击标示,返回新 JPEG。坐标越界由 PIL 裁剪兜底。"""
    from PIL import Image, ImageDraw

    img = Image.open(BytesIO(jpeg)).convert("RGB")
    d = ImageDraw.Draw(img)
    xi, yi = int(x), int(y)
    d.ellipse([xi - 14, yi - 14, xi + 14, yi + 14], outline=_RED, width=3)  # 扩散圆环(终态尺寸)
    scale, ox, oy = 34 / 24, xi - 5, yi - 3  # 光标贴纸 34px,尖端对准点击点
    poly = [(ox + px * scale, oy + py * scale) for px, py in _CURSOR_PTS]
    d.polygon(poly, outline=_WHITE, width=3)  # 白描边层
    d.polygon(poly, fill=_RED)  # 红填充盖住描边内缘,留白边
    buf = BytesIO()
    img.save(buf, "JPEG", quality=92)
    return buf.getvalue()
