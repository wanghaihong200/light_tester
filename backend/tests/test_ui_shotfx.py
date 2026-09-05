# tests/test_ui_shotfx.py
"""执行截图点击标示的像素级验证:白底图叠画后,点击点附近必须出现红色光标/圆环。"""
from io import BytesIO

from PIL import Image

from app.ui_automation.shotfx import overlay_click_mark

RED = (255, 77, 79)


def _white_jpeg(w=320, h=200) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (w, h), (255, 255, 255)).save(buf, "JPEG", quality=92)
    return buf.getvalue()


def test_overlay_paints_cursor_and_ring_near_click_point():
    out = Image.open(BytesIO(overlay_click_mark(_white_jpeg(), 160, 100)))
    px = out.load()
    # 圆环上缘 (160, 100-14) 与光标主体(点击点右下)附近都应是红色系
    ring_hit = any(px[160, y][0] > 200 and px[160, y][1] < 140 for y in range(82, 90))
    cursor_hit = any(
        px[x, y][0] > 200 and px[x, y][1] < 140
        for x in range(158, 185) for y in range(100, 125))
    assert ring_hit and cursor_hit


def test_overlay_near_edge_does_not_crash():
    # 点击点贴边:坐标越界由 PIL 裁剪兜底,不抛异常
    out = Image.open(BytesIO(overlay_click_mark(_white_jpeg(), 2, 2)))
    assert out.size == (320, 200)
