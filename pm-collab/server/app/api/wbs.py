"""WBS 分解 API：里程碑 / 工作包 / 子任务 CRUD + WBS 树（四层 + 子任务）。

层级（需求书 §4.1，任务之下再拆一层子任务）：
  项目(Project) → 里程碑(Milestone) → 工作包(WorkPackage) → 任务(TaskCard) → 子任务(SubTask)

所有接口按 project_ctx 隔离当前项目；新建项目时由 ensure_default_project / create_project 初始化骨架。
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..audit import write_log
from ..models import Member, Milestone, SubTask, TaskCard, WorkPackage
from ..schemas import (
    MilestoneIn,
    SubTaskEvidenceIn,
    SubTaskIn,
    SubTaskTransitionIn,
    WorkPackageIn,
)
from ..state_machine import TASK_TRANSITIONS, can_transit_task
from .deps import current_member, get_db, project_ctx

router = APIRouter(prefix="/api/wbs", tags=["WBS 分解"])


def _uid() -> str:
    return str(uuid.uuid4())


# ---------------- 里程碑 ----------------
@router.get("/milestones")
def list_milestones(
    pid: str = Depends(project_ctx),
    db: Session = Depends(get_db),
    _: Member = Depends(current_member),
) -> list[dict]:
    rows = (
        db.query(Milestone)
        .filter(Milestone.project_id == pid)
        .order_by(Milestone.order_index, Milestone.code)
        .all()
    )
    return [_out(m) for m in rows]


@router.post("/milestones", status_code=status.HTTP_201_CREATED)
def create_milestone(
    payload: MilestoneIn,
    pid: str = Depends(project_ctx),
    db: Session = Depends(get_db),
    actor: Member = Depends(current_member),
) -> dict:
    if db.query(Milestone).filter(Milestone.project_id == pid, Milestone.code == payload.code).first():
        raise HTTPException(status_code=409, detail=f"里程碑编号已存在：{payload.code}")
    obj = Milestone(id=_uid(), project_id=pid, **payload.model_dump())
    db.add(obj)
    db.flush()
    write_log(db, actor=actor.name, action="创建里程碑", change=f"{obj.code} {obj.name}",
              artifact_path="01_项目库/计划与里程碑/")
    db.commit()
    db.refresh(obj)
    return _out(obj)


@router.get("/milestones/{mid}")
def get_milestone(
    mid: str, db: Session = Depends(get_db), _: Member = Depends(current_member)
) -> dict:
    m = db.get(Milestone, mid)
    if m is None:
        raise HTTPException(status_code=404, detail="里程碑不存在")
    return _out(m)


@router.put("/milestones/{mid}")
def update_milestone(
    mid: str, payload: MilestoneIn,
    db: Session = Depends(get_db), actor: Member = Depends(current_member),
) -> dict:
    m = db.get(Milestone, mid)
    if m is None:
        raise HTTPException(status_code=404, detail="里程碑不存在")
    for k, v in payload.model_dump().items():
        setattr(m, k, v)
    write_log(db, actor=actor.name, action="更新里程碑", change=f"{m.code}")
    db.commit()
    return _out(m)


@router.delete("/milestones/{mid}")
def delete_milestone(
    mid: str, db: Session = Depends(get_db), actor: Member = Depends(current_member),
) -> dict:
    m = db.get(Milestone, mid)
    if m is None:
        raise HTTPException(status_code=404, detail="里程碑不存在")
    if db.query(WorkPackage).filter(WorkPackage.milestone_id == mid).first():
        raise HTTPException(status_code=409, detail="该里程碑下仍有工作包，无法删除")
    db.delete(m)
    write_log(db, actor=actor.name, action="删除里程碑", change=f"{m.code}")
    db.commit()
    return {"ok": True}


# ---------------- 工作包 ----------------
@router.get("/workpackages")
def list_workpackages(
    milestone_id: str | None = None,
    pid: str = Depends(project_ctx),
    db: Session = Depends(get_db),
    _: Member = Depends(current_member),
) -> list[dict]:
    q = db.query(WorkPackage).filter(WorkPackage.project_id == pid)
    if milestone_id:
        q = q.filter(WorkPackage.milestone_id == milestone_id)
    return [_out(w) for w in q.order_by(WorkPackage.order_index, WorkPackage.code).all()]


@router.post("/workpackages", status_code=status.HTTP_201_CREATED)
def create_workpackage(
    payload: WorkPackageIn,
    pid: str = Depends(project_ctx),
    db: Session = Depends(get_db),
    actor: Member = Depends(current_member),
) -> dict:
    ms = db.get(Milestone, payload.milestone_id)
    if ms is None or ms.project_id != pid:
        raise HTTPException(status_code=404, detail="所属里程碑不存在或不属于当前项目")
    if db.query(WorkPackage).filter(
        WorkPackage.project_id == pid, WorkPackage.code == payload.code
    ).first():
        raise HTTPException(status_code=409, detail=f"工作包编号已存在：{payload.code}")
    obj = WorkPackage(id=_uid(), project_id=pid, **payload.model_dump())
    db.add(obj)
    db.flush()
    write_log(db, actor=actor.name, action="创建工作包", change=f"{obj.code} {obj.name}",
              artifact_path="01_项目库/计划与里程碑/")
    db.commit()
    db.refresh(obj)
    return _out(obj)


@router.get("/workpackages/{wid}")
def get_workpackage(
    wid: str, db: Session = Depends(get_db), _: Member = Depends(current_member)
) -> dict:
    w = db.get(WorkPackage, wid)
    if w is None:
        raise HTTPException(status_code=404, detail="工作包不存在")
    return _out(w)


@router.put("/workpackages/{wid}")
def update_workpackage(
    wid: str, payload: WorkPackageIn,
    db: Session = Depends(get_db), actor: Member = Depends(current_member),
) -> dict:
    w = db.get(WorkPackage, wid)
    if w is None:
        raise HTTPException(status_code=404, detail="工作包不存在")
    for k, v in payload.model_dump().items():
        setattr(w, k, v)
    write_log(db, actor=actor.name, action="更新工作包", change=f"{w.code}")
    db.commit()
    return _out(w)


@router.delete("/workpackages/{wid}")
def delete_workpackage(
    wid: str, db: Session = Depends(get_db), actor: Member = Depends(current_member),
) -> dict:
    w = db.get(WorkPackage, wid)
    if w is None:
        raise HTTPException(status_code=404, detail="工作包不存在")
    if db.query(TaskCard).filter(TaskCard.work_package_id == wid).first():
        raise HTTPException(status_code=409, detail="该工作包下仍有任务，无法删除")
    db.delete(w)
    write_log(db, actor=actor.name, action="删除工作包", change=f"{w.code}")
    db.commit()
    return {"ok": True}


# ---------------- 子任务 ----------------
@router.get("/subtasks")
def list_subtasks(
    task_id: str | None = None,
    pid: str = Depends(project_ctx),
    db: Session = Depends(get_db),
    _: Member = Depends(current_member),
) -> list[dict]:
    q = db.query(SubTask).filter(SubTask.project_id == pid)
    if task_id:
        q = q.filter(SubTask.task_id == task_id)
    return [_out(s) for s in q.order_by(SubTask.order_index, SubTask.code).all()]


@router.post("/subtasks", status_code=status.HTTP_201_CREATED)
def create_subtask(
    payload: SubTaskIn,
    pid: str = Depends(project_ctx),
    db: Session = Depends(get_db),
    actor: Member = Depends(current_member),
) -> dict:
    t = db.get(TaskCard, payload.task_id)
    if t is None or t.project_id != pid:
        raise HTTPException(status_code=404, detail="所属任务不存在或不属于当前项目")
    if db.query(SubTask).filter(SubTask.project_id == pid, SubTask.code == payload.code).first():
        raise HTTPException(status_code=409, detail=f"子任务编号已存在：{payload.code}")
    obj = SubTask(id=_uid(), project_id=pid, **payload.model_dump())
    db.add(obj)
    db.flush()
    write_log(db, actor=actor.name, action="创建子任务",
              change=f"{obj.code} {obj.title}（隶属 {t.code}）",
              artifact_path="03_日志/任务台账/")
    db.commit()
    db.refresh(obj)
    return _out(obj)


@router.get("/subtasks/{sid}")
def get_subtask(
    sid: str, db: Session = Depends(get_db), _: Member = Depends(current_member)
) -> dict:
    s = db.get(SubTask, sid)
    if s is None:
        raise HTTPException(status_code=404, detail="子任务不存在")
    return _out(s)


@router.put("/subtasks/{sid}")
def update_subtask(
    sid: str, payload: SubTaskIn,
    db: Session = Depends(get_db), actor: Member = Depends(current_member),
) -> dict:
    s = db.get(SubTask, sid)
    if s is None:
        raise HTTPException(status_code=404, detail="子任务不存在")
    for k, v in payload.model_dump().items():
        setattr(s, k, v)
    write_log(db, actor=actor.name, action="更新子任务", change=f"{s.code}")
    db.commit()
    return _out(s)


@router.post("/subtasks/{sid}/transition")
def transition_subtask(
    sid: str, payload: SubTaskTransitionIn,
    db: Session = Depends(get_db), actor: Member = Depends(current_member),
) -> dict:
    s = db.get(SubTask, sid)
    if s is None:
        raise HTTPException(status_code=404, detail="子任务不存在")
    if not can_transit_task(s.status, payload.target):
        raise HTTPException(
            status_code=409,
            detail=f"非法状态迁移：{s.status} → {payload.target}（允许：{list(TASK_TRANSITIONS.get(s.status, ()))}）",
        )
    s.status = payload.target
    write_log(db, actor=actor.name, action="子任务状态迁移",
              change=f"{s.code}：{s.status} → {payload.target}",
              artifact_path="03_日志/任务台账/")
    db.commit()
    return _out(s)


@router.post("/subtasks/{sid}/evidence")
def add_subtask_evidence(
    sid: str, payload: SubTaskEvidenceIn,
    db: Session = Depends(get_db), actor: Member = Depends(current_member),
) -> dict:
    s = db.get(SubTask, sid)
    if s is None:
        raise HTTPException(status_code=404, detail="子任务不存在")
    merged = list(dict.fromkeys(list(s.evidence or []) + payload.paths))
    s.evidence = merged
    if payload.summary:
        s.summary = payload.summary
    write_log(db, actor=actor.name, action="登记子任务证据",
              change=f"{s.code} 证据 {len(payload.paths)} 条")
    db.commit()
    return {"sub_code": s.code, "evidence": s.evidence}


@router.delete("/subtasks/{sid}")
def delete_subtask(
    sid: str, db: Session = Depends(get_db), actor: Member = Depends(current_member),
) -> dict:
    s = db.get(SubTask, sid)
    if s is None:
        raise HTTPException(status_code=404, detail="子任务不存在")
    db.delete(s)
    write_log(db, actor=actor.name, action="删除子任务", change=f"{s.code}")
    db.commit()
    return {"ok": True}


# ---------------- WBS 树（一次性组装四层 + 子任务） ----------------
@router.get("/tree")
def wbs_tree(
    pid: str = Depends(project_ctx),
    db: Session = Depends(get_db),
    _: Member = Depends(current_member),
) -> dict:
    milestones = (
        db.query(Milestone)
        .filter(Milestone.project_id == pid)
        .order_by(Milestone.order_index, Milestone.code)
        .all()
    )
    wps = (
        db.query(WorkPackage)
        .filter(WorkPackage.project_id == pid)
        .order_by(WorkPackage.order_index, WorkPackage.code)
        .all()
    )
    wps_by_ms: dict[str, list[WorkPackage]] = {}
    for w in wps:
        wps_by_ms.setdefault(w.milestone_id, []).append(w)

    tasks = (
        db.query(TaskCard)
        .filter(TaskCard.project_id == pid)
        .order_by(TaskCard.code)
        .all()
    )
    subs = (
        db.query(SubTask)
        .filter(SubTask.project_id == pid)
        .order_by(SubTask.order_index, SubTask.code)
        .all()
    )
    subs_by_task: dict[str, list[dict]] = {}
    for s in subs:
        subs_by_task.setdefault(s.task_id, []).append(_out(s))

    tasks_orphan: list[dict] = []
    tasks_by_wp: dict[str, list[dict]] = {}
    for t in tasks:
        node = _task_node(t, subs_by_task.get(t.id, []))
        if t.work_package_id:
            tasks_by_wp.setdefault(t.work_package_id, []).append(node)
        else:
            tasks_orphan.append(node)

    ms_nodes = []
    for m in milestones:
        wp_nodes = []
        for w in wps_by_ms.get(m.id, []):
            wp_nodes.append({**_out(w), "tasks": tasks_by_wp.get(w.id, [])})
        ms_nodes.append({**_out(m), "work_packages": wp_nodes})

    # 未归类工作包（无里程碑）与未归类任务
    orphan_wps = [w for w in wps if w.milestone_id not in {m.id for m in milestones}]
    orphan_wp_nodes = []
    for w in orphan_wps:
        orphan_wp_nodes.append({**_out(w), "tasks": tasks_by_wp.get(w.id, [])})

    return {
        "project_id": pid,
        "milestones": ms_nodes,
        "orphan_work_packages": orphan_wp_nodes,
        "unclassified_tasks": tasks_orphan,
    }


# ---------------- 内部工具 ----------------
def _out(obj) -> dict:
    from ..schemas import asdict_out

    return asdict_out(obj)


def _task_node(t: TaskCard, subs: list[dict]) -> dict:
    d = _out(t)
    d["sub_tasks"] = subs
    d["sub_task_count"] = len(subs)
    return d
