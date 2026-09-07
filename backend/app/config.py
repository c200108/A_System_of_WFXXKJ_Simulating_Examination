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

    # 学生打开系统用的对外地址，例如 http://203.0.113.10:8080 或 https://exam.school.edu.cn。
    # 留空则用浏览器当前地址（location.origin）。
    # 什么时候必须填：老师在服务器上用 127.0.0.1 打开后台时，浏览器地址是学生
    # 访问不到的，复制出来的链接就成了废链接——填了这项就永远给正确地址。
    public_base_url: str = ""

    @property
    def cors_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

    @property
    def public_url(self) -> str:
        """对外地址。**只认显式配置**，没配就返回空串让前端用浏览器当前地址。

        故意不从 CORS_ORIGINS 推导：那一项可能是开发默认的 localhost，
        也可能被手工改坏（少个冒号之类），拿它拼出来的链接比 location.origin 更不可靠。
        """
        url = self.public_base_url.strip().rstrip("/")
        return url if url.startswith(("http://", "https://")) else ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
