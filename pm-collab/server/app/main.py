"""PM-Collab 服务层入口。

服务层 API 是唯一数据入口：人类 Web UI 与 AI 侧交接区文件均经此中转（设计大纲 §1.2 原则 8）。
"""
from __future__ import annotations

import asyncio
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import api_router
from .api.auth import ensure_bootstrap
from .config import settings
from .db import SessionLocal
from .models import Member
from .services import events
from .services.db_bootstrap import init_db
from .services.five_libs import ensure_all_project_dirs, ensure_libraries
from .services.projects import ensure_default_project
from .services.scheduler_service import start_scheduler, stop_scheduler
from .services.watchdog_service import watcher


def _wire_sync_publish(loop: asyncio.AbstractEventLoop) -> None:
    """让同步线程（watchdog）也能向 WS 客户端推送。"""
    def _publish(message: str) -> None:
        async def _run() -> None:
            for ws in list(events._ws_clients):
                try:
                    await ws.send_text(message)
                except Exception:
                    events._ws_clients.discard(ws)

        asyncio.run_coroutine_threadsafe(_run(), loop)

    events._sync_publish = _publish


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_libraries()
    init_db()

    # OSS-02：首次启动随机生成 JWT 密钥并持久化到 .env（仅当密钥未配置时）。
    secret_generated = False
    if not settings.secret_key:
        new_secret = secrets.token_hex(64)
        _persist_env("PM_SECRET_KEY", new_secret)
        settings.secret_key = new_secret
        secret_generated = True

    db = SessionLocal()
    try:
        admin_exists = db.query(Member).filter(
            Member.username == settings.bootstrap_username
        ).first() is not None
        # 新库：生成一次性随机口令；老库升级不生成、不打扰既有口令。
        bootstrap_pwd = settings.bootstrap_password or secrets.token_urlsafe(12)
        if not admin_exists:
            print(_first_run_banner(bootstrap_pwd, secret_generated))
        ensure_bootstrap(db, bootstrap_pwd)
        ensure_default_project(db)
        # 首次启动（默认项目内尚无任何任务卡）写入 PM-Collab 示范种子数据；
        # 既有库已含数据则跳过，确保升级老用户数据零打扰。种子本身按编号幂等，不会重复新建。
        from .models import TaskCard
        from ..seed.seed_all import seed_all
        if db.query(TaskCard).first() is None:
            seed_all(db, bootstrap_pwd)
            print("[startup] 已写入 PM-Collab 示范种子数据（首次启动）")
        n = ensure_all_project_dirs(db)
        print(f"[startup] 已为 {n} 个项目建立独立资料目录（data/projects/<项目编号>/）")
    finally:
        db.close()
    _wire_sync_publish(asyncio.get_running_loop())
    watcher.start()
    print("[watchdog] 交接区同步监听已启动（watchdog）")
    start_scheduler()
    print(f"[startup] {settings.app_name} v{settings.app_version} @ {settings.host}:{settings.port}")
    print(f"[startup] 数据层：{settings.database_url}")
    print(f"[startup] 文件库：{settings.data_dir}")
    yield
    stop_scheduler()
    watcher.stop()


def _persist_env(key: str, value: str) -> None:
    """把首次生成的密钥写入仓库根 .env（已被 .gitignore 排除，切勿提交）。"""
    env_path = Path(__file__).resolve().parents[2] / ".env"
    lines = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    lines = [ln for ln in lines if not ln.startswith(f"{key}=")]
    lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _first_run_banner(pwd: str, secret_generated: bool) -> str:
    secret_line = (
        "       初始 JWT 密钥已自动生成并写入 .env（请勿提交）。"
        if secret_generated else ""
    )
    return (
        "\n==================================================\n"
        "  PM-Collab 首次启动\n"
        "  初始账号: admin\n"
        f"  初始密码: {pwd}\n"
        "  登录后请通过右上角用户菜单 → 修改密码 立即更换。\n"
        f"{secret_line}\n"
        "==================================================\n"
    )


def create_app(start_services: bool = True) -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="人机共用项目管理软件 MVP：五库托管 · 任务卡状态机 · 交接总线 · 每日摘要",
        lifespan=lifespan if start_services else None,
        # 单机部署时前端「文档库」路由为 /docs，与 FastAPI 自带 Swagger 冲突；
        # 故将 Swagger 移至 /swagger、OpenAPI 描述置于 /openapi.json，释放 /docs 给 SPA。
        docs_url="/swagger",
        redoc_url=None,
        openapi_url="/openapi.json",
    )
    # CORS：当前为本地单用户单机部署，允许任意源带凭据以便本机 Web / 脚本 / AI 调用互通。
    # ⚠️ 仅限本地单用户部署：生产、多用户或公网部署必须把 allow_origins 收紧为显式可信源列表，
    # 否则等价于「任意源带凭据」，存在跨站凭据泄露与越权风险（OSS 评审 S2）。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)

    # 前端构建产物存在时一并托管（单机部署一条命令启动）
    # 说明：前端为 history 路由，/guide、/dashboard 等子路径刷新时必须回退到 index.html，
    # 否则 StaticFiles 会返回 404。故静态资源挂 /assets，其余路径由 spa_fallback 兜底。
    dist = Path(__file__).resolve().parents[2] / "web" / "dist"
    if dist.exists() and (dist / "index.html").exists():
        assets = dist / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

        dist_root = dist.resolve()

        @app.get("/{full_path:path}")
        def spa_fallback(full_path: str) -> FileResponse:
            if full_path:
                target = (dist / full_path).resolve()
                # 防路径穿越：仅允许返回 dist 目录内的真实文件
                if target.is_file() and str(target).startswith(str(dist_root)):
                    return FileResponse(target)
            return FileResponse(dist_root / "index.html")

    return app


app = create_app()
