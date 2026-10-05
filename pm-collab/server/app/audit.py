"""追加式日志与卡点信号的服务层封装（需求书 §5.2、§9.1）。

所有写操作统一经此模块留痕，保证"任一结论可回溯到 交互 + 证据 + 确认人"。
追加日志在库层由触发器禁止 UPDATE/DELETE（迁移 T06）。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .models import AppendLog, CheckpointSignal, DEFAULT_PROJECT_ID
from .services.events import hub
from .utils import utcnow


def write_log(
    db: Session,
    *,
    actor: str,
    action: str,
    artifact_path: str = "",
    change: str = "",
    next_step: str = "",
    open_issue: str = "",
    extra: dict[str, Any] | None = None,
) -> AppendLog:
    log = AppendLog(
        occurred_at=utcnow(),
        actor=actor,
        action=action,
        artifact_path=artifact_path,
        change=change,
        next_step=next_step,
        open_issue=open_issue,
        extra=extra or {},
    )
    db.add(log)
    db.flush()
    return log


def raise_checkpoint(
    db: Session,
    *,
    trigger: str,
    content: str,
    human_action: str,
    expect_by: str | None = None,
    task_code: str | None = None,
    category: str = "搬运请求",
    project_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> CheckpointSignal:
    """生成卡点信号（6 字段）并推送至实时队列。"""
    signal = CheckpointSignal(
        occurred_at=utcnow(),
        trigger=trigger,
        content=content,
        human_action=human_action,
        expect_by=expect_by,
        task_code=task_code,
        category=category,
        project_id=project_id or DEFAULT_PROJECT_ID,
        status="待处理",
        extra=extra or {},
    )
    db.add(signal)
    db.flush()
    hub.publish("checkpoint", {
        "id": signal.id,
        "category": signal.category,
        "content": signal.content,
        "human_action": signal.human_action,
        "task_code": signal.task_code,
        "occurred_at": signal.occurred_at.isoformat(),
    })
    return signal
