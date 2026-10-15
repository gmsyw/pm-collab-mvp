"""PM-Collab 全局配置（pydantic-settings，支持 .env 覆盖）。

默认单机零依赖部署：SQLite + 本地文件库；设置 PM_DATABASE_URL 为
postgresql+psycopg://... 即切换 PostgreSQL 16（生产/网络部署形态）。
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根：pm-collab/
BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PM_", env_file=".env", extra="ignore")

    # ---- 服务 ----
    app_name: str = "PM-Collab 人机共用项目管理软件"
    app_version: str = "0.1.0"
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False

    # ---- 数据层 ----
    # 默认 SQLite（本机零依赖）；PG 形态：postgresql+psycopg://user:pwd@host:5432/pmcollab
    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'pm_collab.db'}"
    db_echo: bool = False

    # ---- 认证 ----
    # 留空表示「首次启动由系统随机生成 JWT 密钥并写入 .env」；
    # 切勿在源码中写死密钥（OSS-02）。生产环境请通过 PM_SECRET_KEY 环境变量显式配置强密钥。
    secret_key: str = ""
    jwt_alg: str = "HS256"
    jwt_expire_minutes: int = 60 * 12

    # ---- 文件库（五库 + 交接区）----
    data_dir: Path = BASE_DIR / "data"
    handoff_dir: Path = BASE_DIR / "data" / "交接区"

    # ---- 调度 / 监听 ----
    daily_digest_hour: int = 8
    daily_digest_minute: int = 30
    watchdog_enabled: bool = True
    scheduler_enabled: bool = True
    feishu_webhook: str = ""  # 可选推送渠道，留空则仅本地通知/日志留痕

    # ---- 默认管理员（MVP 单用户）----
    # 口令留空表示「首次启动由系统生成一次性随机密码并打印到控制台」，
    # 切勿在源码中写死口令（OSS-02）。
    bootstrap_username: str = "admin"
    bootstrap_password: str = ""

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


settings = Settings()
