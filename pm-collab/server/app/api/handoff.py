"""交接总线 API（D 域）：交接单 CRUD / 双向同步 / 投喂与回收助手（T14/T15）。"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..audit import raise_checkpoint, write_log
from ..config import settings
from ..models import HandoffOrder, Member, TaskCard
from ..schemas import HandoffIn, HandoffTransitionIn
from ..services import handoff_sync as hs
from ..services.five_libs import ensure_libraries, list_zone_files, zone_path
from ..state_machine import can_transit_handoff
from ..utils import today_str
from .deps import current_member, get_db, project_ctx

router = APIRouter(prefix="/api/handoff", tags=["交接总线"])


def _out(r: HandoffOrder) -> dict:
    return {
        "id": r.id, "code": r.code, "sender": r.sender, "receiver": r.receiver,
        "zone": r.zone, "payload_path": r.payload_path, "status": r.status,
        "task_code": r.task_code,
        "fed_at": r.fed_at.isoformat() if r.fed_at else None,
        "recycled_at": r.recycled_at.isoformat() if r.recycled_at else None,
        "closed_at": r.closed_at.isoformat() if r.closed_at else None,
    }


@router.get("")
def list_orders(
    status_: str | None = Query(default=None, alias="status"),
    pid: str = Depends(project_ctx),
    db: Session = Depends(get_db),
    _: Member = Depends(current_member),
) -> list[dict]:
    q = db.query(HandoffOrder).filter(HandoffOrder.project_id == pid)
    if status_:
        q = q.filter(HandoffOrder.status == status_)
    return [_out(r) for r in q.order_by(HandoffOrder.code).all()]


@router.get("/zones")
def zones(_: Member = Depends(current_member)) -> dict:
    return {"handoff_dir": str(settings.handoff_dir), "files": list_zone_files()}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_order(
    payload: HandoffIn,
    pid: str = Depends(project_ctx),
    db: Session = Depends(get_db),
    actor: Member = Depends(current_member),
) -> dict:
    if db.query(HandoffOrder).filter(HandoffOrder.code == payload.code).first():
        raise HTTPException(status_code=409, detail=f"交接单编号已存在：{payload.code}")
    obj = HandoffOrder(**payload.model_dump(), project_id=pid)
    db.add(obj)
    db.flush()
    write_log(db, actor=actor.name, action="创建交接单",
              change=f"{obj.code} → {obj.receiver}（{obj.zone}）", artifact_path=obj.payload_path)
    db.commit()
    hs.sync_to_zone(db)
    return _out(obj)


@router.post("/{order_id}/transition")
def transition_order(
    order_id: str,
    payload: HandoffTransitionIn,
    db: Session = Depends(get_db),
    actor: Member = Depends(current_member),
) -> dict:
    obj = db.get(HandoffOrder, order_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="交接单不存在")
    if not can_transit_handoff(obj.status, payload.target):
        raise HTTPException(
            status_code=409,
            detail=f"非法交接状态迁移：{obj.status} → {payload.target}（须按 待投喂→已投喂→已回收→已闭环）",
        )
    hs._apply_handoff_status(db, obj, payload.target)
    write_log(db, actor=actor.name, action="交接单状态迁移",
              change=f"{obj.code}：{obj.status} → {payload.target}", artifact_path=obj.payload_path)
    db.commit()
    hs.sync_to_zone(db)
    return _out(obj)


@router.post("/sync")
def sync(direction: Literal["to", "from", "both"] = Query(default="both"),
         db: Session = Depends(get_db),
         actor: Member = Depends(current_member)) -> dict:
    """手动双向同步（对账入口，MVP 风险项：文件与库双写不一致）。"""
    result: dict = {}
    if direction in ("from", "both"):
        result.update(hs.sync_from_zone(db, actor=actor.name))
    if direction in ("to", "both"):
        result.update(hs.sync_to_zone(db))
    if "direction" not in result:
        result["direction"] = direction
    return result


@router.post("/feed/{task_id}")
def feed_task(
    task_id: str,
    receiver: str = Query(default=""),
    db: Session = Depends(get_db),
    actor: Member = Depends(current_member),
) -> dict:
    """投喂助手：任务卡 → `派单/` 文件 + 交接单置「已投喂」+ 生成搬运卡点。"""
    task = db.get(TaskCard, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    ensure_libraries()
    path = hs.render_task_card_file(task)
    code = f"HO-{task.code}"
    order = db.query(HandoffOrder).filter(HandoffOrder.code == code).first()
    if order is None:
        order = HandoffOrder(code=code, sender=actor.name, receiver=receiver or task.ai_executor,
                             zone="派单", payload_path=str(path), task_code=task.code,
                             project_id=task.project_id)
        db.add(order)
        db.flush()
    else:
        order.payload_path = str(path)
        if receiver:
            order.receiver = receiver
    if can_transit_handoff(order.status, "已投喂"):
        hs._apply_handoff_status(db, order, "已投喂")

    write_log(db, actor=actor.name, action="投喂任务卡",
              change=f"{task.code} → {order.receiver or '（待指派）'}", artifact_path=str(path),
              next_step="等待接收方回执复述")
    raise_checkpoint(
        db, trigger=actor.name, task_code=task.code, project_id=task.project_id, category="搬运请求",
        content=f"任务卡已生成于「派单/」：{Path(path).name}",
        human_action=f"把 {path} 投喂给 {order.receiver or '目标 AI 角色'} 对话，回执放入「回执/」",
        expect_by="当日",
    )
    db.commit()
    hs.sync_to_zone(db)
    return {"task_code": task.code, "file": str(path), "order": order.code, "status": order.status}


@router.post("/recycle/{order_id}")
def recycle_order(
    order_id: str,
    db: Session = Depends(get_db),
    actor: Member = Depends(current_member),
) -> dict:
    """回收助手：`完成/` 摘要回收 → 任务卡回填 + 版本台账登记 + 交接单置「已回收」。

    端到端闭环：派单 → AI 回写 → 回收 → 台账（MVP DoD 第 4 条）。
    """
    order = db.get(HandoffOrder, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="交接单不存在")
    if not can_transit_handoff(order.status, "已回收"):
        raise HTTPException(status_code=409, detail=f"当前状态不可回收：{order.status}")

    candidates = _find_completion(order)
    if not candidates:
        raise HTTPException(
            status_code=404,
            detail=f"未在「完成/」目录找到该交接单的产物（任务 {order.task_code}）",
        )
    parsed = hs.parse_completion_file(candidates[0])

    task = None
    if order.task_code:
        task = db.query(TaskCard).filter(TaskCard.code == order.task_code).first()
    if task is not None:
        task.summary = parsed["summary"] or task.summary
        task.evidence = list(dict.fromkeys(list(task.evidence or []) + parsed["evidence"] + [parsed["path"]]))
        if parsed["deliverable"]:
            task.deliverables = parsed["deliverable"]
        if task.status == "进行中":
            task.status = "待评审"

    order.payload_path = parsed["path"]
    hs._apply_handoff_status(db, order, "已回收")

    ledger = None
    if task is not None and (parsed["deliverable"] or parsed["summary"]):
        ledger = hs.register_task_ledger(db, task, parsed["deliverable"], actor=order.receiver or "PM-AI")

    write_log(db, actor=actor.name, action="回收完成摘要",
              change=f"{order.code}：{Path(parsed['path']).name}：执行者 {parsed['executor'] or '未署名'}",
              artifact_path=parsed["path"],
              next_step=f"台账登记 {ledger.version if ledger else '（跳过）'}，等待评审签字")
    db.commit()
    hs.sync_to_zone(db)
    return {
        "order": order.code, "status": order.status, "file": parsed["path"],
        "task_code": task.code if task else None,
        "task_status": task.status if task else None,
        "ledger": {"version": ledger.version, "item_name": ledger.item_name} if ledger else None,
    }


def _find_completion(order: HandoffOrder) -> list[Path]:
    """按任务编号匹配「完成/」目录产物。"""
    done_dir = zone_path("完成")
    if not done_dir.exists():
        return []
    if not order.task_code:
        return []
    pattern = re.compile(rf"^{re.escape(order.task_code)}_")
    files = [f for f in done_dir.iterdir() if f.is_file() and pattern.match(f.name)]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


@router.post("/{order_id}/close")
def close_order(
    order_id: str,
    db: Session = Depends(get_db),
    actor: Member = Depends(current_member),
) -> dict:
    order = db.get(HandoffOrder, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="交接单不存在")
    if not can_transit_handoff(order.status, "已闭环"):
        raise HTTPException(status_code=409, detail=f"当前状态不可闭环：{order.status}（须先回收）")
    hs._apply_handoff_status(db, order, "已闭环")
    write_log(db, actor=actor.name, action="交接单闭环", change=f"{order.code} 已闭环于 {today_str()}",
              artifact_path=order.payload_path)
    db.commit()
    hs.sync_to_zone(db)
    return _out(order)
