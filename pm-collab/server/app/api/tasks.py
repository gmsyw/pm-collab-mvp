"""任务卡 CRUD + 状态机（C 任务协作域；T10）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import raise_checkpoint, write_log
from ..models import Member, Milestone, TaskCard, WorkPackage
from ..schemas import EvidenceIn, TaskCardIn, TaskTransitionIn
from ..state_machine import (
    EVIDENCE_REQUIRED_STATUS,
    SUMMARY_REQUIRED_STATUS,
    can_transit_task,
)
from ..utils import ensure_aware, utcnow
from .deps import current_member, get_db, project_ctx

router = APIRouter(prefix="/api/tasks", tags=["任务卡"])


def _apply_wbs_links(db: Session, obj: TaskCard, milestone_id: str | None, work_package_id: str | None) -> None:
    """按 FK 反查并填充冗余展示字段 milestone / work_package，并强制层级归属一致。

    归属约束（需求：每个层级必须归属自己的上级，不能混乱）：
      - 里程碑必须属于当前项目；
      - 工作包必须属于当前项目，且当同时给定里程碑时，工作包必须挂在「该里程碑」下；
      - 仅给定工作包时，自动继承其所属里程碑，保证 milestone_id 与 work_package 不矛盾。
    """
    ms = None
    if milestone_id:
        ms = db.get(Milestone, milestone_id)
        if ms is None or ms.project_id != obj.project_id:
            raise HTTPException(status_code=404, detail="所属里程碑不存在或不属于当前项目")
        obj.milestone_id = ms.id
        obj.milestone = ms.name
    if work_package_id:
        wp = db.get(WorkPackage, work_package_id)
        if wp is None or wp.project_id != obj.project_id:
            raise HTTPException(status_code=404, detail="所属工作包不存在或不属于当前项目")
        # 层级一致性：工作包必须挂在指定的里程碑下；仅给工作包时反推里程碑
        if ms is not None and wp.milestone_id != ms.id:
            raise HTTPException(
                status_code=409,
                detail=f"工作包 {wp.code} 不属于里程碑 {ms.code}（它属于 {wp.milestone_id}），层级归属冲突",
            )
        if ms is None:
            ms = db.get(Milestone, wp.milestone_id)
            if ms is None or ms.project_id != obj.project_id:
                raise HTTPException(status_code=404, detail="工作包所属里程碑不存在或不属于当前项目")
            obj.milestone_id = ms.id
            obj.milestone = ms.name
        obj.work_package_id = wp.id
        obj.work_package = wp.name


@router.get("")
def list_tasks(
    status_: str | None = Query(default=None, alias="status"),
    milestone: str | None = Query(default=None),
    milestone_id: str | None = Query(default=None, alias="milestone_id"),
    pid: str = Depends(project_ctx),
    db: Session = Depends(get_db),
    _: Member = Depends(current_member),
) -> list[dict]:
    q = db.query(TaskCard).filter(TaskCard.project_id == pid)
    if status_:
        q = q.filter(TaskCard.status == status_)
    if milestone_id:
        q = q.filter(TaskCard.milestone_id == milestone_id)
    elif milestone:
        q = q.filter(TaskCard.milestone == milestone)
    return [_task_out(t) for t in q.order_by(TaskCard.code).all()]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCardIn,
    pid: str = Depends(project_ctx),
    db: Session = Depends(get_db),
    actor: Member = Depends(current_member),
) -> dict:
    # 编号唯一性：项目内唯一（需求书 §4.1），跨项目允许复用 —— 按 project_id 校验
    if db.query(TaskCard).filter(TaskCard.project_id == pid, TaskCard.code == payload.code).first():
        raise HTTPException(status_code=409, detail=f"任务编号已存在：{payload.code}（项目内唯一）")
    data = payload.model_dump()
    m_id = data.pop("milestone_id", None)
    wp_id = data.pop("work_package_id", None)
    obj = TaskCard(**data, status="待办", project_id=pid)
    _apply_wbs_links(db, obj, m_id, wp_id)
    try:
        db.add(obj)
        db.flush()
        write_log(db, actor=actor.name, action="创建任务卡", change=f"{obj.code} {obj.title}",
                  next_step="派单或进入执行", artifact_path="03_日志/任务台账/")
        db.commit()
    except IntegrityError:
        # 并发同编号竞态（DEF-03）：应用层查重与 DB 复合唯一约束之间存在窗口，
        # 落库时唯一约束冲突抛 IntegrityError，需转换为 409 而非 500
        db.rollback()
        raise HTTPException(status_code=409, detail=f"任务编号已存在：{payload.code}（项目内唯一）")
    db.refresh(obj)
    return _task_out(obj)


@router.get("/{task_id}")
def get_task(
    task_id: str,
    db: Session = Depends(get_db),
    _: Member = Depends(current_member),
) -> dict:
    obj = db.get(TaskCard, task_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return _task_out(obj)


@router.get("/code/{code}")
def get_task_by_code(
    code: str,
    pid: str = Depends(project_ctx),
    db: Session = Depends(get_db),
    _: Member = Depends(current_member),
) -> dict:
    """按任务编号（项目内唯一）取单条，供前端关联跳转（就地抽屉）直接使用。"""
    obj = db.query(TaskCard).filter(TaskCard.project_id == pid, TaskCard.code == code).first()
    if obj is None:
        raise HTTPException(status_code=404, detail=f"任务不存在：{code}")
    return _task_out(obj)


@router.put("/{task_id}")
def update_task(
    task_id: str,
    payload: TaskCardIn,
    db: Session = Depends(get_db),
    actor: Member = Depends(current_member),
) -> dict:
    obj = db.get(TaskCard, task_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    data = payload.model_dump()
    data.pop("code", None)  # 编号不可改，保可追溯
    m_id = data.pop("milestone_id", None)
    wp_id = data.pop("work_package_id", None)
    for key, value in data.items():
        setattr(obj, key, value)
    _apply_wbs_links(db, obj, m_id, wp_id)
    write_log(db, actor=actor.name, action="更新任务卡", change=f"{obj.code}",
              artifact_path="03_日志/任务台账/")
    db.commit()
    return _task_out(obj)


@router.post("/{task_id}/evidence")
def add_evidence(
    task_id: str,
    payload: EvidenceIn,
    db: Session = Depends(get_db),
    actor: Member = Depends(current_member),
) -> dict:
    """登记证据路径（需求书 §5.3：无证据不得置为通过）。"""
    obj = db.get(TaskCard, task_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    merged = list(dict.fromkeys(list(obj.evidence or []) + payload.paths))
    obj.evidence = merged
    if payload.summary:
        obj.summary = payload.summary
    write_log(db, actor=actor.name, action="登记证据", change=f"{obj.code} 证据 {len(payload.paths)} 条",
              artifact_path=";".join(payload.paths))
    db.commit()
    return {"task_code": obj.code, "evidence": obj.evidence}


@router.post("/{task_id}/transition")
def transition_task(
    task_id: str,
    payload: TaskTransitionIn,
    db: Session = Depends(get_db),
    actor: Member = Depends(current_member),
) -> dict:
    """状态迁移：非法迁移一律拒绝（MVP DoD 第 2 条）。"""
    obj = db.get(TaskCard, task_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    current, target = obj.status, payload.target
    if not can_transit_task(current, target):
        raise HTTPException(
            status_code=409,
            detail=f"非法状态迁移：{current} → {target}（允许：{_allowed(current)}）",
        )
    if target in EVIDENCE_REQUIRED_STATUS and not (obj.evidence or []):
        raise HTTPException(status_code=422, detail=f"无证据不得置为「{target}」，请先登记证据")
    if target in SUMMARY_REQUIRED_STATUS and not obj.summary.strip():
        raise HTTPException(status_code=422, detail="关闭任务必须填写完成摘要（需求书 §4.7）")
    if target == "阻塞" and not payload.note.strip():
        raise HTTPException(status_code=422, detail="阻塞须填写原因与责任方（需求书 §4.6）")

    if target == "阻塞":
        obj.blocked_reason = payload.note
        obj.blocked_since = utcnow()
    elif target == "返工":
        obj.rework_count = (obj.rework_count or 0) + 1
    elif current == "阻塞":
        obj.blocked_reason = None
        obj.blocked_since = None

    obj.status = target
    write_log(db, actor=actor.name, action="任务状态迁移",
              change=f"{obj.code}：{current} → {target}" + (f"（{payload.note}）" if payload.note else ""),
              artifact_path="03_日志/任务台账/", next_step=_next_hint(target))

    # 卡点信号：流转到「待评审」时请求人类评审签字；阻塞时告警
    if target == "待评审":
        raise_checkpoint(
            db, trigger=actor.name, task_code=obj.code, project_id=obj.project_id, category="审批请求",
            content=f"任务 {obj.code} 已就绪，等待人类评审签字",
            human_action=f"评审并签字（同意置「通过」/ 驳回置「返工」）：{obj.deliverables or obj.title}",
            expect_by="24 小时内",
        )
    elif target == "阻塞":
        raise_checkpoint(
            db, trigger=actor.name, task_code=obj.code, project_id=obj.project_id, category="决策请求",
            content=f"任务 {obj.code} 阻塞：{payload.note}",
            human_action="排除阻塞或重新分派，逾期 24 小时将持续告警",
            expect_by="24 小时内",
        )

    db.commit()
    return _task_out(obj)


def _allowed(current: str) -> list[str]:
    from ..state_machine import TASK_TRANSITIONS

    return list(TASK_TRANSITIONS.get(current, ()))


def _next_hint(target: str) -> str:
    return {
        "进行中": "执行并回写完成摘要",
        "待评审": "等待人类评审签字",
        "通过": "置为关闭并归档",
        "返工": "按评审意见修订后重提评审",
        "关闭": "归档验证",
        "阻塞": "24 小时内排除",
        "取消": "登记取消原因",
    }.get(target, "")


def _task_out(t: TaskCard) -> dict:
    from ..schemas import asdict_out

    data = asdict_out(t)
    if t.blocked_since:
        started = ensure_aware(t.blocked_since)
        data["blocked_hours"] = round((utcnow() - started).total_seconds() / 3600, 2)
    return data
