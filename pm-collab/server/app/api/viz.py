"""V0.4 过程可视化：任务详情时间线 + 模块泳道（§11）。

- 时间线：按 task_code 聚合交接单，缺失 event_type 时由 zone + payload_path 正则推断；
  节点按 event_type 配色，人类签字节点金色高亮（§11.3.1）。
- 泳道：按 module_tag 聚合，给出阶段 / 卡片数 / 最近事件 / 阻塞标记（§11.3.2）。
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..models import HandoffOrder, TaskCard
from ..schemas import asdict_out
from .deps import current_member, get_db, project_ctx

router = APIRouter(prefix="/api/viz", tags=["过程可视化"])

# event_type → 配色（对应 §11.3.1）
COLOR = {
    "派单": "blue",
    "评审意见": "purple",
    "评审通过": "purple",
    "开发交付": "cyan",
    "修订返工": "orange",
    "QA通过": "green",
    "签字": "gold",
    "合入": "green",
}

REVIEW_TYPES = ("评审意见", "修订返工", "评审通过")


def _infer_event_type(zone: str, payload_path: str) -> str:
    text = f"{zone} {payload_path or ''}".lower()
    if re.search(r"签字|基线|门禁", payload_path or ""):
        return "签字"
    if re.search(r"qa|测试|复跑|用例", text):
        return "QA通过"
    if re.search(r"返工|修订|打回|修改", text):
        return "修订返工"
    if re.search(r"评审|review", text):
        return "评审意见"
    if re.search(r"交付|完成|回执", text):
        return "开发交付"
    if zone == "派单":
        return "派单"
    return zone or "其他"


def _infer_round(payload_path: str, declared: int) -> int:
    if declared and declared > 0:
        return declared
    m = re.search(r"第\s*(\d+)\s*轮|r\s*0*(\d+)|round[_\s-]?(\d+)", payload_path or "", re.IGNORECASE)
    if m:
        return int(m.group(1) or m.group(2) or m.group(3))
    return 0


@router.get("/timeline")
def task_timeline(
    task_code: str = Query(...),
    pid: str = Depends(project_ctx),
    db: Session = Depends(get_db),
    _: Member = Depends(current_member),
) -> dict:
    task = (
        db.query(TaskCard)
        .filter(TaskCard.project_id == pid, TaskCard.code == task_code)
        .first()
    )
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    orders = (
        db.query(HandoffOrder)
        .filter(HandoffOrder.project_id == pid, HandoffOrder.task_code == task_code)
        .order_by(HandoffOrder.created_at, HandoffOrder.updated_at)
        .all()
    )
    nodes = []
    for o in orders:
        et = o.event_type or _infer_event_type(o.zone, o.payload_path)
        nodes.append(
            {
                "id": o.id,
                "code": o.code,
                "event_type": et,
                "color": COLOR.get(et, "gray"),
                "round": _infer_round(o.payload_path, o.round),
                "sender": o.sender,
                "receiver": o.receiver,
                "status": o.status,
                "payload_path": o.payload_path,
                "evidence": o.evidence or {},
                "time": (o.updated_at or o.created_at).isoformat()
                if (o.updated_at or o.created_at)
                else None,
                "human_sign": et == "签字",
            }
        )
    return {"task_code": task_code, "task": asdict_out(task), "nodes": nodes}


@router.get("/swimlane")
def module_swimlane(
    pid: str = Depends(project_ctx),
    db: Session = Depends(get_db),
    _: Member = Depends(current_member),
) -> dict:
    tasks = (
        db.query(TaskCard)
        .filter(TaskCard.project_id == pid, TaskCard.module_tag.isnot(None))
        .all()
    )
    ORDER = {"待办": 0, "进行中": 1, "待评审": 2, "返工": 3, "通过": 4, "关闭": 5, "取消": 5, "阻塞": 6}
    STAGE_NAME = {0: "待办", 1: "开发中", 2: "待评审", 3: "返工中", 4: "待合入", 5: "已归档", 6: "阻塞"}
    lanes: dict[str, dict] = {}
    for t in tasks:
        tag = t.module_tag  # type: ignore[assignment]
        lane = lanes.setdefault(
            tag,
            {"module_tag": tag, "count": 0, "blocked": 0, "stage_order": -1, "latest": None},
        )
        lane["count"] += 1
        if t.status == "阻塞":
            lane["blocked"] += 1
        lane["stage_order"] = max(lane["stage_order"], ORDER.get(t.status, 0))
        ts = t.updated_at or t.created_at
        if ts and (lane["latest"] is None or ts > lane["latest"]):
            lane["latest"] = ts
    out = []
    for tag in sorted(lanes):
        lane = lanes[tag]
        out.append(
            {
                "module_tag": tag,
                "stage": STAGE_NAME.get(lane["stage_order"], "待办"),
                "count": lane["count"],
                "blocked": lane["blocked"],
                "latest": lane["latest"].isoformat() if lane["latest"] else None,
            }
        )
    return {"lanes": out}
