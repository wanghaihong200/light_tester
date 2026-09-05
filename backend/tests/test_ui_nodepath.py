# tests/test_ui_nodepath.py
from app.ui_automation import nodepath


def test_driver_target_fallback():
    assert nodepath.driver_target({"meta": {"target": "android"}}) == "android"
    assert nodepath.driver_target({"meta": {"target": "ios"}}) == "web"   # 非法回退
    assert nodepath.driver_target({}) == "web"
    assert nodepath.driver_target({"meta": {}}) == "web"


def test_needs_node():
    sel = {"meta": {"target": "web"}, "steps": [{"id": "1", "action": "click", "locator": {}}]}
    assert nodepath.needs_node(sel) is False
    ai_web = {"meta": {"target": "web"}, "steps": [{"id": "1", "action": "ai_tap", "params": {}}]}
    assert nodepath.needs_node(ai_web) is True
    assert nodepath.needs_node({"meta": {"target": "harmony"}, "steps": []}) is True


def test_target_locks_per_target_capacity_one():
    import threading
    for t in nodepath.TARGETS:
        lock = nodepath.TARGET_LOCKS[t]
        assert isinstance(lock, threading.BoundedSemaphore)
        assert lock._initial_value == 1
