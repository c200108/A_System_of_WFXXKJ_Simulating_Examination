from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from .siteconfig import site as _site


class Settings(BaseSettings):
    """全部配置从环境变量读取，不写死在代码里，换环境只改 .env。"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # sqlite:///./data/app.db  或  mysql+pymysql://user:pwd@db:3306/exam?charset=utf8mb4
    database_url: str = "sqlite:///./data/app.db"

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720

    upload_dir: str = "./data/uploads"
    # 默认值取自 config.yaml 的 upload.max_mb，环境变量 MAX_UPLOAD_MB 可再覆盖
    max_upload_mb: int = _site.upload.max_mb

    admin_username: str = "admin"
    admin_password: str = "admin123"
    admin_name: str = "系统管理员"

    # 逗号分隔；开发时前端 vite 跑在 5173
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
