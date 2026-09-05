from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "mysql+pymysql://root:root123@127.0.0.1:3307/test_platform?charset=utf8mb4"
    repos_dir: Path = Path("../data/repos")
    uploads_dir: Path = Path("../data/uploads")
    ui_data_dir: Path = Path("../data/ui")
    anthropic_api_key: str | None = None
    ai_model: str = "claude-opus-5"
    jwt_secret: str = "dev-secret-change-me-please-32bytes!"
    jwt_exp_days: int = 7
    run_slot_count: int = 5
    # 多端 UI 自动化(计划 10):Midscene 视觉模型(智谱 OpenAI 兼容端点)
    ai_vision_base_url: str = "https://open.bigmodel.cn/api/coding/paas/v4"
    ai_vision_api_key: str | None = None
    ai_vision_model: str = "glm-5.3-flash"   # 冒烟验证 grounding;不稳则切 glm-5v-turbo(仅改配置)
    ai_vision_model_family: str = "glm-v"    # Midscene 必填,决定坐标适配;GLM-V 系列固定 glm-v
    ui_runner_dir: Path = Path("runner-node")  # Node runner 包目录(相对 backend cwd)


settings = Settings()
settings.repos_dir.mkdir(parents=True, exist_ok=True)
settings.uploads_dir.mkdir(parents=True, exist_ok=True)
settings.ui_data_dir.mkdir(parents=True, exist_ok=True)
