"""项目管理 API：新建项目 / 列表 / 详情（WBS 根实体；需求书 §4.1）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..models import Member, Project, TaskCard
from ..schemas import ProjectIn, ProjectUpdateIn
from ..services import projects as proj_svc
from ..audit import write_log
from .deps import current_member, get_db

router = APIRouter(prefix="/api/projects", tags=["项目"])


@router.get("")
def list_projects(
    db: Session = Depends(get_db),
    _: Member = Depends(current_member),
) -> list[dict]:
    rows = db.query(Project).order_by(Project.created_at).all()
    out = []
    for p in rows:
        cnt = db.query(TaskCard).filter(TaskCard.project_id == p.id).count()
        out.append({
            "id": p.id, "code": p.code, "name": p.name, "description": p.description,
            "status": p.status, "owner": p.owner, "task_count": cnt,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        })
    return out


@router.post("", status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectIn,
    db: Session = Depends(get_db),
    actor: Member = Depends(current_member),
) -> dict:
    """新建项目：自动初始化其独立流程实例与 4 门禁。"""
    try:
        proj = proj_svc.create_project(
            db, payload.code, payload.name, payload.description, payload.owner
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"id": proj.id, "code": proj.code, "name": proj.name}


@router.get("/{project_id}")
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    _: Member = Depends(current_member),
) -> dict:
    p = db.get(Project, project_id)
    if p is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {
        "id": p.id, "code": p.code, "name": p.name, "description": p.description,
        "status": p.status, "owner": p.owner,
    }


@router.put("/{project_id}")
def update_project(
    project_id: str,
    payload: ProjectUpdateIn,
    db: Session = Depends(get_db),
    actor: Member = Depends(current_member),
) -> dict:
    """编辑项目：名称/描述/负责人/状态（仅更新传入字段，编号不可改，保可追溯）。"""
    p = db.get(Project, project_id)
    if p is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    data = payload.model_dump(exclude_unset=True)  # 仅更新客户端实际传入的字段
    data.pop("code", None)  # 编号不可改
    for key, value in data.items():
        setattr(p, key, value)
    db.commit()
    write_log(db, actor=actor.name, action="编辑项目", change=f"{p.code} {p.name}")
    return {
        "id": p.id, "code": p.code, "name": p.name, "description": p.description,
        "status": p.status, "owner": p.owner,
    }
