"""认证接口：登录 / 引导 / 当前用户。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..audit import write_log
from ..config import settings
from ..models import Member
from ..schemas import LoginIn, TokenOut
from ..security import create_token, hash_password, verify_password
from .deps import current_member, get_db

router = APIRouter(prefix="/api/auth", tags=["认证"])


def ensure_bootstrap(db: Session) -> Member:
    """MVP 单用户：确保存在默认管理员成员与人类角色卡持有者。"""
    member = db.query(Member).filter(Member.username == settings.bootstrap_username).first()
    if member is None:
        member = Member(
            code="H-001",
            name="Dr Ming（PO/PM/TL）",
            member_type="人类",
            status="在岗",
            username=settings.bootstrap_username,
            password_hash=hash_password(settings.bootstrap_password),
        )
        db.add(member)
        db.commit()
        db.refresh(member)
    return member


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)) -> TokenOut:
    ensure_bootstrap(db)
    member = db.query(Member).filter(Member.username == payload.username).first()
    if member is None or not member.password_hash:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    if not verify_password(payload.password, member.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    token = create_token(member.username or "", {"member_id": member.id})
    write_log(db, actor=member.name, action="用户登录", change=f"{payload.username} 登录成功")
    db.commit()
    return TokenOut(access_token=token, username=member.username or "")


@router.get("/me")
def me(member: Member = Depends(current_member)) -> dict:
    return {"id": member.id, "code": member.code, "name": member.name,
            "member_type": member.member_type, "username": member.username}
