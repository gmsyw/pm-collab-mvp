"""卡点信号队列（D 交接总线域；T16）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from ..audit import write_log
from ..models import CheckpointSignal, Member
from ..schemas import CheckpointHandleIn, CheckpointIn
from ..utils import utcnow
from .deps import current_member, get_db, project_ctx

router = APIRouter(prefix="/api/checkpoints", tags=["卡点队列"])


@router.get("")
def list_checkpoints(
    status_: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, le=500),
    pid: str = Depends(project_ctx),
    db: Session = Depends(get_db),
    _: Member = Depends(current_member),
) -> list[dict]:
    q = db.query(CheckpointSignal).filter(CheckpointSignal.project_id == pid)
    if status_:
        q = q.filter(CheckpointSignal.status == status_)
    rows = q.order_by(CheckpointSignal.occurred_at.desc()).limit(limit).all()
    return [
        {
            "id": r.id, "occurred_at": r.occurred_at.isoformat(), "trigger": r.trigger,
            "content": r.content, "human_action": r.human_action, "expect_by": r.expect_by,
            "task_code": r.task_code, "category": r.category, "status": r.status,
            "handled_note": r.handled_note,
        }
        for r in rows
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_checkpoint(
    payload: CheckpointIn,
    pid: str = Depends(project_ctx),
    db: Session = Depends(get_db),
    actor: Member = Depends(current_member),
) -> dict:
    from ..audit import raise_checkpoint

    signal = raise_checkpoint(
        db, trigger=payload.trigger or actor.name, content=payload.content,
        human_action=payload.human_action, expect_by=payload.expect_by,
        task_code=payload.task_code, category=payload.category, project_id=pid,
    )
    db.commit()
    return {"id": signal.id, "content": signal.content, "status": signal.status}


@router.post("/{signal_id}/handle")
def handle_checkpoint(
    signal_id: str,
    payload: CheckpointHandleIn,
    db: Session = Depends(get_db),
    actor: Member = Depends(current_member),
) -> dict:
    obj = db.get(CheckpointSignal, signal_id)
    if obj is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="卡点不存在")
    obj.status = "已处理"
    obj.handled_note = payload.note
    write_log(db, actor=actor.name, action="处理卡点", change=f"[{obj.category}] {obj.content}",
              next_step="继续按单执行")
    db.commit()
    return {"id": obj.id, "status": obj.status, "handled_at": utcnow().isoformat()}
