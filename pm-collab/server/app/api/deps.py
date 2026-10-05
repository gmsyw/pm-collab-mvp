"""API 公共依赖：数据库会话 + JWT 认证 + 项目上下文。"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..db import SessionLocal, get_session
from ..models import Member
from ..security import decode_token
from ..services import projects as proj_svc

bearer_scheme = HTTPBearer(auto_error=False)


def get_db() -> Session:
    yield from get_session()


def current_member(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Member:
    """未授权请求一律 401（T08 验收：未授权请求被拒）。"""
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少访问令牌")
    payload = decode_token(creds.credentials)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="令牌无效或已过期")
    member = db.query(Member).filter(Member.username == payload.get("sub")).first()
    if member is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    return member


def project_ctx(
    project_id: str | None = Query(default=None, alias="project_id"),
    db: Session = Depends(get_db),
) -> str:
    """解析当前操作所属项目：显式传入则用之，否则回退默认/首个项目。"""
    return proj_svc.resolve_project_id(db, project_id)


__all__ = [
    "Depends", "Session", "SessionLocal", "get_db", "current_member",
    "bearer_scheme", "project_ctx", "Query",
]
