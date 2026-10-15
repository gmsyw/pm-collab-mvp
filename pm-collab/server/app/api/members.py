"""成员名册 CRUD（A 组织与权限域）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..audit import write_log
from ..models import DEFAULT_PROJECT_ID, Member
from ..schemas import MemberIn, MemberOut
from ..security import hash_password
from .deps import current_member, get_db, project_ctx

router = APIRouter(prefix="/api/members", tags=["成员名册"])


@router.get("", response_model=list[MemberOut])
def list_members(
    member_type: str | None = Query(default=None),
    pid: str = Depends(project_ctx),
    db: Session = Depends(get_db),
    _: Member = Depends(current_member),
) -> list[Member]:
    # 项目隔离：普通项目优先显示本项目私有副本；默认项目显示模板本身；
    # 历史空项目（尚无私有名册）回退显示 default 模板以保证平滑过渡。
    if pid == DEFAULT_PROJECT_ID:
        q = db.query(Member).filter(Member.project_id == DEFAULT_PROJECT_ID)
    else:
        own = db.query(Member).filter(Member.project_id == pid).all()
        q = db.query(Member).filter(
            Member.project_id == (pid if own else DEFAULT_PROJECT_ID)
        )
    if member_type:
        q = q.filter(Member.member_type == member_type)
    return q.order_by(Member.code).all()


@router.get("/code/{code}", response_model=MemberOut)
def get_member_by_code(
    code: str,
    pid: str = Depends(project_ctx),
    db: Session = Depends(get_db),
    _: Member = Depends(current_member),
) -> Member:
    """按成员编号取单条（项目隔离：优先本项目私有副本，否则默认模板）。"""
    if pid == DEFAULT_PROJECT_ID:
        obj = db.query(Member).filter(Member.project_id == DEFAULT_PROJECT_ID, Member.code == code).first()
    else:
        own = db.query(Member).filter(Member.project_id == pid, Member.code == code).first()
        obj = own or db.query(Member).filter(Member.project_id == DEFAULT_PROJECT_ID, Member.code == code).first()
    if obj is None:
        raise HTTPException(status_code=404, detail=f"成员不存在：{code}")
    return obj


@router.post("", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def create_member(
    payload: MemberIn,
    pid: str = Depends(project_ctx),
    db: Session = Depends(get_db),
    actor: Member = Depends(current_member),
) -> Member:
    exists = db.query(Member).filter(Member.code == payload.code).first()
    if exists:
        raise HTTPException(status_code=409, detail=f"成员编号已存在：{payload.code}")
    data = payload.model_dump()
    password = data.pop("password", None)
    obj = Member(**data)
    obj.project_id = pid  # 归属当前项目
    if password:
        obj.password_hash = hash_password(password)
    db.add(obj)
    db.flush()
    write_log(db, actor=actor.name, action="新增成员", change=f"成员 {obj.code} {obj.name}",
              artifact_path="01_项目库/成员名册与角色卡/")
    db.commit()
    db.refresh(obj)
    return obj


@router.put("/{member_id}", response_model=MemberOut)
def update_member(
    member_id: str,
    payload: MemberIn,
    db: Session = Depends(get_db),
    actor: Member = Depends(current_member),
) -> Member:
    obj = db.get(Member, member_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="成员不存在")
    # 编号/登录账号不可改；仅允许调整业务字段
    for key in ("name", "member_type", "status", "reports_to", "extra"):
        if hasattr(payload, key):
            value = getattr(payload, key)
            if value is not None:
                setattr(obj, key, value)
    write_log(db, actor=actor.name, action="更新成员", change=f"成员 {obj.code}",
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
