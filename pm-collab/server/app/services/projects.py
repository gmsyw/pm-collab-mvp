"""项目服务：WBS 根实体管理 + 默认项目/流程实例占位（需求书 §4.1、设计大纲决策点④）。

单项目优先，但数据层预留多项目：所有业务实体均带 project_id；本项目启动时确保存在一个
默认项目 PM-Collab 示范项目，并为其初始化流程实例与 4 门禁，使"新建项目"成为一等能力。
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import DEFAULT_PROJECT_ID, GateRecord, Member, ProcessInstance, Project, RoleCard
from ..services.five_libs import ensure_project_structure
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
        ensure_project_structure(proj.code)  # 默认项目也建独立目录

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
    """解析有效项目 id：显式且存在则用之；否则回退到首个项目；再否则兜底创建默认项目。

    兜底创建确保「项目」这一根实体始终存在（此前仅返回常量 id 却不建行，
    导致任务/交接单指向幽灵项目，按项目隔离后同步看不到任何项目）。
    """
    if project_id:
        p = db.get(Project, project_id)
        if p is not None:
            return p.id
    first = db.query(Project).order_by(Project.created_at).first()
    if first is not None:
        return first.id
    return ensure_default_project(db).id


def _clone_default_roster(db: Session, proj: Project) -> None:
    """把 default 项目的角色卡 + 非登录成员克隆为新建项目的私有副本。

    目的：让每个新项目自带一份可独立调整、不影响其他项目的初始名册/角色卡
    （用户诉求：缺省值按自身情况调整，互不污染）。

    规则：
    - 角色卡全部克隆；
    - 成员仅克隆无登录账号者（username 为空）——admin 等登录账户是跨项目的
      统一管理员，按 username 全局唯一且不区分项目，不应按项目复制；
    - 克隆副本 code 加项目编号前缀，规避全局唯一约束；
    - default 模板本身保持只读基线，任何项目都不得修改它。
    """
    prefix = proj.code
    # 角色卡（8 字段）
    for rc in db.query(RoleCard).filter(RoleCard.project_id == DEFAULT_PROJECT_ID).all():
        new_code = f"{prefix}-{rc.code}"
        if db.query(RoleCard).filter(RoleCard.code == new_code).first():
            continue
        clone = RoleCard(
            code=new_code,
            project_id=proj.id,
            role_type=rc.role_type,
            duty=rc.duty,
            negative_list=rc.negative_list,
            permission_level=rc.permission_level,
            data_boundary=rc.data_boundary,
            reports_to=rc.reports_to,
            downgrade_plan=rc.downgrade_plan,
            extra=dict(rc.extra or {}),
        )
        db.add(clone)
    # 成员：全部克隆为「纯名册条目」（剥离登录账号/口令，避免 username 全局唯一冲突）；
    # 全局 admin 登录账户仍唯一存在，不被复制，各项目只拥有一份可调的名册副本。
    for m in db.query(Member).filter(Member.project_id == DEFAULT_PROJECT_ID).all():
        new_code = f"{prefix}-{m.code}"
        if db.query(Member).filter(Member.code == new_code).first():
            continue
        clone = Member(
            code=new_code,
            project_id=proj.id,
            name=m.name,
            member_type=m.member_type,
            status=m.status,
            reports_to=m.reports_to,
            extra=dict(m.extra or {}),
        )
        db.add(clone)


def create_project(
    db: Session, code: str, name: str, description: str = "", owner: str = "",
) -> Project:
    """新建项目，并为其初始化独立的流程实例、4 门禁与私有名册/角色卡副本。"""
    if db.query(Project).filter(Project.code == code).first():
        raise ValueError(f"项目编号已存在：{code}")
    proj = Project(code=code, name=name, description=description, owner=owner, status="进行中")
    db.add(proj)
    db.flush()
    inst = ProcessInstance(name=name, milestone="MVP", stage="S1", project_id=proj.id)
    db.add(inst)
    db.flush()
    _ensure_gates(db, inst)
    ensure_project_structure(proj.code)  # 每个新建项目拥有独立资料目录
    _clone_default_roster(db, proj)  # 克隆 default 名册/角色卡为项目私有副本
    db.commit()
    db.refresh(proj)
    return proj
