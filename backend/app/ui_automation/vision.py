# app/ui_automation/vision.py
"""Midscene 模型环境变量注入表(Python 只负责把配置注入子进程 env,模型细节由 Midscene 处理)。
变量体系为 Midscene v1.x 的 MIDSCENE_MODEL_*;family 决定坐标适配,智谱 GLM-V 系列固定 glm-v。"""
from app.config import settings


def vision_env() -> dict[str, str]:
    if not settings.ai_vision_api_key:
        raise RuntimeError("未配置 ai_vision_api_key(.env),无法执行 AI 步")
    return {
        "MIDSCENE_MODEL_BASE_URL": settings.ai_vision_base_url,
        "MIDSCENE_MODEL_API_KEY": settings.ai_vision_api_key,
        "MIDSCENE_MODEL_NAME": settings.ai_vision_model,
        "MIDSCENE_MODEL_FAMILY": settings.ai_vision_model_family,
    }
