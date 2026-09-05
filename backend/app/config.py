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
    ai_vision_api_key: str | None = None  # 智谱 GLM(计划 10 多端 UI 自动化视觉模型用;仅预留,暂无消费方)
    jwt_secret: str = "dev-secret-change-me-please-32bytes!"
    jwt_exp_days: int = 7
    run_slot_count: int = 5


settings = Settings()
settings.repos_dir.mkdir(parents=True, exist_ok=True)
settings.uploads_dir.mkdir(parents=True, exist_ok=True)
settings.ui_data_dir.mkdir(parents=True, exist_ok=True)
