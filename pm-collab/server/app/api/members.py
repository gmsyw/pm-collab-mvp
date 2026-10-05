"""成员名册 CRUD（A 组织与权限域）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..audit import write_log
from ..models import Member
from ..schemas import MemberIn, MemberOut
from ..security import hash_password
from .deps import current_member, get_db

router = APIRouter(prefix="/api/members", tags=["成员名册"])


@router.get("", response_model=list[MemberOut])
def list_members(
    member_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: Member = Depends(current_member),
) -> list[Member]:
    q = db.query(Member)
    if member_type:
        q = q.filter(Member.member_type == member_type)
    return q.order_by(Member.code).all()


@router.post("", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def create_member(
    payload: MemberIn,
    db: Session = Depends(get_db),
    actor: Member = Depends(current_member),
) -> Member:
    exists = db.query(Member).filter(Member.code == payload.code).first()
    if exists:
        raise HTTPException(status_code=409, detail=f"成员编号已存在：{payload.code}")
    data = payload.model_dump()
    password = data.pop("password", None)
    obj = Member(**data)
    if password:
        obj.password_hash = hash_password(password)
    db.add(obj)
    db.flush()
    write_log(db, actor=actor.name, action="新增成员", change=f"成员 {obj.code} {obj.name}",
              artifact_path="01_项目库/成员名册与角色卡/")
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{member_id}")
def delete_member(
    member_id: str,
    db: Session = Depends(get_db),
    actor: Member = Depends(current_member),
) -> dict:
    obj = db.get(Member, member_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="成员不存在")
    db.delete(obj)
    write_log(db, actor=actor.name, action="删除成员", change=f"成员 {obj.code}")
    db.commit()
    return {"deleted": member_id}
