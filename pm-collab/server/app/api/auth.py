"""认证接口：登录 / 引导 / 当前用户 / 改密。"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..audit import write_log
from ..config import settings
from ..models import Member
from ..schemas import LoginIn, TokenOut
from ..security import create_token, hash_password, verify_password
from .deps import current_member, get_db

router = APIRouter(prefix="/api/auth", tags=["认证"])


def ensure_bootstrap(db: Session, password: str = "") -> Member:
    """MVP 单用户：确保存在默认管理员成员与人类角色卡持有者。

    新库使用传入口令（首启随机口令）；老库 admin 已存在则跳过，绝不覆盖既有口令。
    """
    member = db.query(Member).filter(Member.username == settings.bootstrap_username).first()
    if member is None:
        member = Member(
            code="H-001",
            name="Dr Ming（PO/PM/TL）",
            member_type="人类",
            status="在岗",
            username=settings.bootstrap_username,
            password_hash=hash_password(password),
        )
        db.add(member)
        db.commit()
        db.refresh(member)
    return member


class ChangePasswordIn(BaseModel):
    old_password: str
    # 长度约束下沉到 schema：框架统一返回 422，前端可较早感知（OSS 评审 S4）
    new_password: str = Field(min_length=8)


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)) -> TokenOut:
    ensure_bootstrap(db, settings.bootstrap_password)
    member = db.query(Member).filter(Member.username == payload.username).first()
    if member is None or not member.password_hash:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    if not verify_password(payload.password, member.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    token = create_token(member.username or "", {"member_id": member.id})
    write_log(db, actor=member.name, action="用户登录", change=f"{payload.username} 登录成功")
    db.commit()
    return TokenOut(access_token=token, username=member.username or "")


@router.post("/change-password")
def change_password(
    payload: ChangePasswordIn,
    member: Member = Depends(current_member),
    db: Session = Depends(get_db),
) -> dict:
    """用户自行修改密码（OSS-02）：验证原密码 → 更新哈希 → 写入 token_valid_from 吊销旧会话。"""
    if not member.password_hash or not verify_password(payload.old_password, member.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="原密码不正确")
    # 新密码长度由 ChangePasswordIn.schema 的 min_length=8 统一校验（框架返回 422）。
    # member 来自 current_member 的独立 DB session；用 merge 并入本端点 session 后再提交，
    # 确保 token_valid_from 与 password_hash 的改动一定落库（否则旧 token 无法被吊销）。
    m = db.merge(member)
    m.password_hash = hash_password(payload.new_password)
    m.token_valid_from = datetime.now(tz=timezone.utc)
    db.commit()
    write_log(
        db, actor=m.name, action="修改密码",
        change="用户自行修改登录密码，旧会话已失效",
    )
    return {"ok": True}


@router.get("/me")
def me(member: Member = Depends(current_member)) -> dict:
    return {"id": member.id, "code": member.code, "name": member.name,
            "member_type": member.member_type, "username": member.username}
