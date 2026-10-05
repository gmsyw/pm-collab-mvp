"""角色卡 CRUD（8 字段校验，A 组织与权限域）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..audit import write_log
from ..models import Member, RoleCard
from ..schemas import RoleCardIn, RoleCardOut
from .deps import current_member, get_db

router = APIRouter(prefix="/api/roles", tags=["角色卡"])


@router.get("", response_model=list[RoleCardOut])
def list_roles(
    permission_level: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: Member = Depends(current_member),
) -> list[RoleCard]:
    q = db.query(RoleCard)
    if permission_level:
        q = q.filter(RoleCard.permission_level == permission_level)
    return q.order_by(RoleCard.code).all()


@router.post("", response_model=RoleCardOut, status_code=status.HTTP_201_CREATED)
def create_role(
    payload: RoleCardIn,
    db: Session = Depends(get_db),
    actor: Member = Depends(current_member),
) -> RoleCard:
    if db.query(RoleCard).filter(RoleCard.code == payload.code).first():
        raise HTTPException(status_code=409, detail=f"角色编号已存在：{payload.code}")
    obj = RoleCard(**payload.model_dump())
    db.add(obj)
    db.flush()
    write_log(db, actor=actor.name, action="新增角色卡", change=f"角色 {obj.code}（{obj.permission_level}）",
              artifact_path="01_项目库/成员名册与角色卡/")
    db.commit()
    db.refresh(obj)
    return obj


@router.put("/{role_id}", response_model=RoleCardOut)
def update_role(
    role_id: str,
    payload: RoleCardIn,
    db: Session = Depends(get_db),
    actor: Member = Depends(current_member),
) -> RoleCard:
    obj = db.get(RoleCard, role_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="角色卡不存在")
    for key, value in payload.model_dump().items():
        setattr(obj, key, value)
    write_log(db, actor=actor.name, action="更新角色卡", change=f"角色 {obj.code}",
              artifact_path="01_项目库/成员名册与角色卡/")
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{role_id}")
def delete_role(
    role_id: str,
    db: Session = Depends(get_db),
    actor: Member = Depends(current_member),
) -> dict:
    obj = db.get(RoleCard, role_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="角色卡不存在")
    db.delete(obj)
    write_log(db, actor=actor.name, action="删除角色卡", change=f"角色 {obj.code}")
    db.commit()
    return {"deleted": role_id}
