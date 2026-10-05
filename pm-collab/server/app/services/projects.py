"""项目服务：WBS 根实体管理 + 默认项目/流程实例占位（需求书 §4.1、设计大纲决策点④）。

单项目优先，但数据层预留多项目：所有业务实体均带 project_id；本项目启动时确保存在一个
默认项目 PM-Collab 示范项目，并为其初始化流程实例与 4 门禁，使"新建项目"成为一等能力。
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import DEFAULT_PROJECT_ID, GateRecord, ProcessInstance, Project
from ..state_machine import GATES

PROJECT_DEFAULT_CODE = "PROJ-DEFAULT"
PROJECT_DEFAULT_NAME = "PM-Collab 示范项目"


def _ensure_gates(db: Session, inst: ProcessInstance) -> None:
    for no, name in GATES.items():
        stage = {"①": "S1", "②": "S3", "③": "S5", "④": "S7"}[no]
        if db.query(GateRecord).filter(
            GateRecord.process_id == inst.id, GateRecord.gate_no == no
        ).first():
            continue
        db.add(GateRecord(process_id=inst.id, gate_no=no, gate_name=name, stage=stage))


def ensure_default_project(db: Session) -> Project:
    """幂等：确保默认项目 + 其流程实例与门禁存在。"""
    proj = db.get(Project, DEFAULT_PROJECT_ID)
    if proj is None:
        proj = Project(
            id=DEFAULT_PROJECT_ID, code=PROJECT_DEFAULT_CODE,
            name=PROJECT_DEFAULT_NAME, status="进行中",
            description="MVP 默认项目，可在界面新建更多项目。",
        )
        db.add(proj)
        db.flush()

    inst = (
        db.query(ProcessInstance)
        .filter(ProcessInstance.project_id == DEFAULT_PROJECT_ID)
        .order_by(ProcessInstance.created_at.desc())
        .first()
    )
    if inst is None:
        inst = ProcessInstance(
            id=DEFAULT_PROJECT_ID, name=PROJECT_DEFAULT_NAME,
            milestone="MVP", stage="S1", project_id=DEFAULT_PROJECT_ID,
        )
        db.add(inst)
        db.flush()
        _ensure_gates(db, inst)
    db.commit()
    return proj


def resolve_project_id(db: Session, project_id: str | None) -> str:
    """解析有效项目 id：显式且存在则用之；否则回退到首个项目；再否则默认项目。"""
    if project_id:
        p = db.get(Project, project_id)
        if p is not None:
            return p.id
    first = db.query(Project).order_by(Project.created_at).first()
    return first.id if first is not None else DEFAULT_PROJECT_ID


def create_project(
    db: Session, code: str, name: str, description: str = "", owner: str = "",
) -> Project:
    """新建项目，并为其初始化独立的流程实例与 4 门禁。"""
    if db.query(Project).filter(Project.code == code).first():
        raise ValueError(f"项目编号已存在：{code}")
    proj = Project(code=code, name=name, description=description, owner=owner, status="进行中")
    db.add(proj)
    db.flush()
    inst = ProcessInstance(name=name, milestone="MVP", stage="S1", project_id=proj.id)
    db.add(inst)
    db.flush()
    _ensure_gates(db, inst)
    db.commit()
    db.refresh(proj)
    return proj
