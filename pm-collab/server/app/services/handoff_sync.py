"""交接单：库 ↔ 交接区 JSON 双向同步，任务卡落盘与完成摘要回收（D 域；T14/T15）。"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ..audit import write_log
from ..config import settings
from ..models import HandoffOrder, TaskCard, VersionLedger
from ..state_machine import HANDOFF_TRANSITIONS, can_transit_handoff
from ..utils import sha256_text, today_str, utcnow
from .five_libs import (
    HANDOFF_LEDGER,
    ensure_libraries,
    ensure_project_structure,
    project_code_by_id,
    project_ledger_path,
    project_zone_path,
)

ZONE_LEDGER_NAME = HANDOFF_LEDGER


def ledger_path(code: str) -> Path:
    """某项目交接单 JSON 路径（按项目隔离）。"""
    return project_ledger_path(code)

# ---------------- 任务卡落盘 / 完成摘要解析 ----------------


def render_task_card_file(task: TaskCard, db: Session, version: str = "V1") -> Path:
    """生成《通用方法》§4 约定的派单文件：编号_动作_名称_Vx.md

    落盘到该任务所属项目的独立交接区（data/projects/<项目编号>/交接区/派单/）。
    """
    code = project_code_by_id(db, task.project_id)
    ensure_project_structure(code)
    safe_title = re.sub(r"[\\/:*?\"<>|]", "_", task.title)[:40]
    path = project_zone_path(code, "派单") / f"{task.code}_派单_{safe_title}_{version}.md"
    body = f"""# 任务卡 {task.code} · {task.title}

## 目标
{task.goal or task.title}

## 输入
{task.inputs or '（无）'}

## 交付物及路径
{task.deliverables or '（待填写）'}

## 验收标准
{task.acceptance or '（待填写）'}

## 分工与排期
- 人类负责人（人-A）：{task.human_owner or 'H'}
- AI 执行者（AI-R）：{task.ai_executor or '（待指派）'}
- 起止：{task.start_date or '—'} ~ {task.due_date or '—'} · 优先级 {task.priority}

## 回执要求
请回执复述交付物与验收标准；参数缺失只问不猜。完成后写回 `完成/` 目录。
"""
    path.write_text(body, encoding="utf-8")
    return path


def parse_completion_file(path: Path) -> dict[str, Any]:
    """解析完成摘要：`任务编号: T04` 形式的简单键值 + 正文摘要。"""
    text = path.read_text(encoding="utf-8", errors="ignore")
    meta: dict[str, str] = {}
    lines: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^[-*]?\s*(任务编号|执行者|证据路径|交付路径|版本)\s*[:：]\s*(.+)$", line)
        if m:
            meta[m.group(1)] = m.group(2).strip()
            continue
        lines.append(line)
    summary = "\n".join(l.strip() for l in lines if l.strip()).strip()
    evidence = [p.strip() for p in meta.get("证据路径", "").split(";") if p.strip()]
    return {
        "task_code": meta.get("任务编号", ""),
        "executor": meta.get("执行者", ""),
        "evidence": evidence,
        "deliverable": meta.get("交付路径", ""),
        "version": meta.get("版本", ""),
        "summary": summary[:4000],
        "path": str(path),
    }


# ---------------- 交接单 ↔ 数据库同步 ----------------


def _dump_orders(db: Session, project_id: str) -> dict[str, Any]:
    rows = (
        db.query(HandoffOrder)
        .filter(HandoffOrder.project_id == project_id)
        .order_by(HandoffOrder.code)
        .all()
    )
    orders = []
    for r in rows:
        orders.append({
            "code": r.code,
            "sender": r.sender,
            "receiver": r.receiver,
            "zone": r.zone,
            "payload_path": r.payload_path,
            "status": r.status,
            "task_code": r.task_code,
            "updated_at": r.updated_at.isoformat() if r.updated_at else "",
            "content_hash": r.content_hash or "",
        })
    return {
        "project": project_code_by_id(db, project_id),
        "updated_at": utcnow().isoformat(),
        "orders": orders,
    }


def sync_to_zone(db: Session, project_id: str) -> dict[str, Any]:
    """库 → 交接区 JSON（服务层为唯一权威，写入即落文件）。按项目隔离。"""
    code = project_code_by_id(db, project_id)
    ensure_project_structure(code)
    LEDGER = ledger_path(code)
    payload = _dump_orders(db, project_id)
    LEDGER.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {"direction": "db→file", "count": len(payload["orders"]), "path": str(LEDGER)}


def sync_from_zone(db: Session, project_id: str, actor: str = "watchdog") -> dict[str, Any]:
    """交接区 JSON → 库：新建同步入库，状态按状态机合法方向更新。按项目隔离。

    非法（倒退/跳变）状态一律忽略并记入冲突列表，保证双写一致。
    """
    code = project_code_by_id(db, project_id)
    LEDGER = ledger_path(code)
    if not LEDGER.exists():
        return {"direction": "file→db", "created": 0, "updated": 0, "conflicts": []}

    try:
        payload = json.loads(LEDGER.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"direction": "file→db", "error": f"交接单解析失败：{exc}", "conflicts": []}

    created = updated = 0
    conflicts: list[str] = []
    for item in payload.get("orders", []):
        code_i = item.get("code")
        if not code_i:
            continue
        row = db.query(HandoffOrder).filter(HandoffOrder.code == code_i).first()
        if row is not None and row.project_id != project_id:
            continue  # 属于其它项目，跳过
        if row is None:
            row = HandoffOrder(
                code=code_i,
                sender=item.get("sender", ""),
                receiver=item.get("receiver", ""),
                zone=item.get("zone", "派单"),
                payload_path=item.get("payload_path", ""),
                status=item.get("status", "待投喂"),
                task_code=item.get("task_code"),
                content_hash=item.get("content_hash", ""),
                project_id=project_id,
            )
            db.add(row)
            created += 1
            continue
        target = item.get("status")
        if target and target != row.status:
            if can_transit_handoff(row.status, target):
                _apply_handoff_status(db, row, target)
                updated += 1
            else:
                conflicts.append(
                    f"{code_i}：{row.status} → {target} 非法（允许 {list(HANDOFF_TRANSITIONS.get(row.status, ()))}）"
                )
        row.payload_path = item.get("payload_path", row.payload_path)
        row.receiver = item.get("receiver", row.receiver)
        row.sender = item.get("sender", row.sender)

    if created or updated or conflicts:
        write_log(db, actor=actor, action="交接区文件→库同步",
                  change=f"新增 {created}、更新 {updated}、冲突 {len(conflicts)}",
                  artifact_path=str(LEDGER),
                  open_issue="；".join(conflicts))
    db.commit()
    return {"direction": "file→db", "created": created, "updated": updated, "conflicts": conflicts}


def _apply_handoff_status(db: Session, row: HandoffOrder, target: str) -> None:
    now = utcnow()
    if target == "已投喂":
        row.fed_at = now
    elif target == "已回收":
        row.recycled_at = now
    elif target == "已闭环":
        row.closed_at = now
    row.status = target


def register_task_ledger(
    db: Session, task: TaskCard, deliverable: str, actor: str = "PM-AI"
) -> VersionLedger:
    """回收 → 台账：为任务交付物登记一条版本台账（版本不覆盖）。"""
    existing = db.query(VersionLedger).filter(
        VersionLedger.item_name == f"{task.code} {task.title}"
    ).count()
    version = f"V1.{existing}" if existing else "V1.0"
    from ..utils import sha256_file

    entry = VersionLedger(
        version=version,
        item_name=f"{task.code} {task.title}",
        item_type="交付物",
        released_at=today_str(),
        executor=actor,
        change_summary=task.summary[:500] if task.summary else f"{task.code} 交付物登记",
        review_status="待评审",
        path=deliverable,
        file_hash=sha256_file(deliverable) if deliverable and Path(deliverable).exists() else sha256_text(task.summary or ""),
    )
    db.add(entry)
    db.flush()
    return entry
