"""PM-Collab 服务层入口。

服务层 API 是唯一数据入口：人类 Web UI 与 AI 侧交接区文件均经此中转（设计大纲 §1.2 原则 8）。
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import api_router
from .api.auth import ensure_bootstrap
from .config import settings
from .db import SessionLocal
from .services import events
from .services.db_bootstrap import init_db
from .services.five_libs import ensure_libraries
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
    db = SessionLocal()
    try:
        ensure_bootstrap(db)
        ensure_default_project(db)
    finally:
        db.close()
    _wire_sync_publish(asyncio.get_running_loop())
    watcher.start()
    start_scheduler()
    print(f"[startup] {settings.app_name} v{settings.app_version} @ {settings.host}:{settings.port}")
    print(f"[startup] 数据层：{settings.database_url}")
    print(f"[startup] 文件库：{settings.data_dir}")
    yield
    stop_scheduler()
    watcher.stop()


def create_app(start_services: bool = True) -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="人机共用项目管理软件 MVP：五库托管 · 任务卡状态机 · 交接总线 · 每日摘要",
        lifespan=lifespan if start_services else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)

    # 前端构建产物存在时一并托管（单机部署一条命令启动）
    dist = Path(__file__).resolve().parents[2] / "web" / "dist"
    if dist.exists() and (dist / "index.html").exists():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="web")
    return app


app = create_app()
