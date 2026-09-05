# tests/test_ui_vision.py
import pytest

from app.config import settings
from app.ui_automation import vision


def test_vision_env_keys(monkeypatch):
    monkeypatch.setattr(settings, "ai_vision_api_key", "k-test")
    monkeypatch.setattr(settings, "ai_vision_base_url", "https://open.bigmodel.cn/api/paas/v4")
    monkeypatch.setattr(settings, "ai_vision_model", "glm-5.3-flash")
    monkeypatch.setattr(settings, "ai_vision_model_family", "glm-v")
    assert vision.vision_env() == {
        "MIDSCENE_MODEL_BASE_URL": "https://open.bigmodel.cn/api/paas/v4",
        "MIDSCENE_MODEL_API_KEY": "k-test",
        "MIDSCENE_MODEL_NAME": "glm-5.3-flash",
        "MIDSCENE_MODEL_FAMILY": "glm-v",
    }


def test_vision_env_requires_key(monkeypatch):
    monkeypatch.setattr(settings, "ai_vision_api_key", None)
    with pytest.raises(RuntimeError, match="ai_vision_api_key"):
        vision.vision_env()
