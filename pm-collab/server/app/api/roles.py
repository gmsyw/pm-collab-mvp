"""角色卡 CRUD（8 字段校验，A 组织与权限域）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..audit import write_log
from ..models import DEFAULT_PROJECT_ID, Member, RoleCard
from ..schemas import RoleCardIn, RoleCardOut
from .deps import current_member, get_db, project_ctx

router = APIRouter(prefix="/api/roles", tags=["角色卡"])


@router.get("", response_model=list[RoleCardOut])
def list_roles(
    permission_level: str | None = Query(default=None),
    pid: str = Depends(project_ctx),
    db: Session = Depends(get_db),
    _: Member = Depends(current_member),
) -> list[RoleCard]:
    # 项目隔离：普通项目优先显示本项目私有副本；默认项目显示模板本身；
    # 历史空项目回退显示 default 模板以保证平滑过渡。
    if pid == DEFAULT_PROJECT_ID:
        q = db.query(RoleCard).filter(RoleCard.project_id == DEFAULT_PROJECT_ID)
    else:
        own = db.query(RoleCard).filter(RoleCard.project_id == pid).all()
        q = db.query(RoleCard).filter(
            RoleCard.project_id == (pid if own else DEFAULT_PROJECT_ID)
        )
    if permission_level:
        q = q.filter(RoleCard.permission_level == permission_level)
    return q.order_by(RoleCard.code).all()


@router.get("/code/{code}", response_model=RoleCardOut)
def get_role_by_code(
    code: str,
    pid: str = Depends(project_ctx),
    db: Session = Depends(get_db),
    _: Member = Depends(current_member),
) -> RoleCard:
    """按角色卡编号取单条（项目隔离：优先本项目私有副本，否则默认模板）。"""
    if pid == DEFAULT_PROJECT_ID:
        obj = db.query(RoleCard).filter(RoleCard.project_id == DEFAULT_PROJECT_ID, RoleCard.code == code).first()
    else:
        own = db.query(RoleCard).filter(RoleCard.project_id == pid, RoleCard.code == code).first()
        obj = own or db.query(RoleCard).filter(RoleCard.project_id == DEFAULT_PROJECT_ID, RoleCard.code == code).first()
    if obj is None:
        raise HTTPException(status_code=404, detail=f"角色卡不存在：{code}")
    return obj


@router.post("", response_model=RoleCardOut, status_code=status.HTTP_201_CREATED)
def create_role(
    payload: RoleCardIn,
    pid: str = Depends(project_ctx),
    db: Session = Depends(get_db),
    actor: Member = Depends(current_member),
) -> RoleCard:
    if db.query(RoleCard).filter(RoleCard.code == payload.code).first():
        raise HTTPException(status_code=409, detail=f"角色编号已存在：{payload.code}")
    obj = RoleCard(**payload.model_dump())
    obj.project_id = pid  # 归属当前项目
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
    # 编号/归属不可改；仅更新业务字段
    for key, value in payload.model_dump().items():
        if key in ("code", "project_id"):
            continue
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
