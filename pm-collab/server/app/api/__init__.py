"""API 路由聚合。"""
from fastapi import APIRouter

from . import auth, checkpoints, docs, handoff, members, process, projects, report, roles, tasks, wbs, ws

api_router = APIRouter()
for m in (auth, members, roles, tasks, wbs, process, docs, handoff, checkpoints, report, projects):
    api_router.include_router(m.router)
api_router.include_router(ws.router)

__all__ = ["api_router"]
