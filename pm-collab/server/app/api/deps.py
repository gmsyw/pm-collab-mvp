"""API 公共依赖：数据库会话 + JWT 认证 + 项目上下文。"""
from __future__ import annotations

from datetime import timezone

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
    # OSS-02 改密后旧 token 吊销：token_valid_from 为 NULL 表示不限制（老库/未改密）；
    # 一旦写入时间戳，所有更早签发的 JWT 立即失效。
    # 注意两点：
    # 1) SQLite 的 DateTime(timezone=True) 读出为 naive datetime（实为 UTC），直接用 .timestamp()
    #    会被当成「本地时间」，与 JWT 中 UTC epoch 的 iat 错位约 8h，故统一按 UTC 归一；
    # 2) JWT 的 iat 是整数秒，而 token_valid_from 带亚秒精度，二者落在同一秒时若用浮点比较
    #    会因亚秒差误判「旧令牌」而把刚改密后签发的新令牌一并吊销——故比较按整数秒取整，
    #    同秒或之后签发的令牌放行，严格更早的令牌吊销。
    iat = payload.get("iat")
    if iat is not None and member.token_valid_from is not None:
        try:
            tvf = member.token_valid_from
            if tvf.tzinfo is None:
                tvf = tvf.replace(tzinfo=timezone.utc)
            if int(iat) < int(tvf.timestamp()):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail="密码已修改，请重新登录"
                )
        except (TypeError, ValueError):
            pass
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
