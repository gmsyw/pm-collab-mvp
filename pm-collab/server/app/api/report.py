"""度量报表 API：即时指标、日报生成与推送（T21/T22）。"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..config import settings
from ..models import AppendLog, Member, MetricRecord
from ..services.digest import compute_metrics, generate_daily_digest
from .deps import current_member, get_db, project_ctx

router = APIRouter(prefix="/api/report", tags=["度量报表"])


@router.get("/metrics")
def metrics(
    pid: str = Depends(project_ctx),
    db: Session = Depends(get_db),
    _: Member = Depends(current_member),
) -> dict:
    return compute_metrics(db, project_id=pid)


@router.post("/digest")
def make_digest(
    push: bool = Query(default=True),
    pid: str = Depends(project_ctx),
    db: Session = Depends(get_db),
    actor: Member = Depends(current_member),
) -> dict:
    record = generate_daily_digest(db, project_id=pid, push=push)
    return {
        "period": record.period,
        "on_time_rate": record.on_time_rate,
        "rework_rate": record.rework_rate,
        "ai_adoption_rate": record.ai_adoption_rate,
        "review_close_rate": record.review_close_rate,
        "pushed_at": record.pushed_at.isoformat() if record.pushed_at else None,
        "summary_text": record.summary_text,
    }


@router.get("/latest")
def latest_digest(
    pid: str = Depends(project_ctx),
    db: Session = Depends(get_db),
    _: Member = Depends(current_member),
) -> dict:
    record = (
        db.query(MetricRecord)
        .filter(MetricRecord.project_id == pid)
        .order_by(MetricRecord.id.desc())
        .first()
    )
    if record is None:
        return {"record": None, "files": _digest_files()}
    return {
        "record": {
            "period": record.period,
            "on_time_rate": record.on_time_rate,
            "rework_rate": record.rework_rate,
            "ai_adoption_rate": record.ai_adoption_rate,
            "review_close_rate": record.review_close_rate,
            "task_total": record.task_total,
            "task_closed": record.task_closed,
            "overdue_count": record.overdue_count,
            "pushed_at": record.pushed_at.isoformat() if record.pushed_at else None,
            "summary_text": record.summary_text,
        },
        "files": _digest_files(),
    }


@router.get("/logs")
def append_logs(
    limit: int = Query(default=100, le=1000),
    db: Session = Depends(get_db),
    _: Member = Depends(current_member),
) -> dict:
    rows = db.query(AppendLog).order_by(AppendLog.occurred_at.desc()).limit(limit).all()
    return {
        "total": len(rows),
        "immutable": True,  # 追加式：不可改删（库层触发器强制）
        "items": [
            {
                "id": r.id, "occurred_at": r.occurred_at.isoformat(), "actor": r.actor,
                "action": r.action, "artifact_path": r.artifact_path, "change": r.change,
                "next_step": r.next_step, "open_issue": r.open_issue,
            }
            for r in rows
        ],
    }


@router.get("/heartbeat")
def heartbeat() -> dict:
    return {"ok": True, "now": datetime.now(tz=timezone.utc).isoformat()}


def _digest_files() -> list[str]:
    d = settings.data_dir / "03_日志" / "日报周报"
    if not d.exists():
        return []
    files = sorted(d.iterdir(), key=lambda p: p.name, reverse=True)
    return [Path(p).name for p in files][:10]
