"""每日摘要：汇总 → 归档 → 推送（H 度量报表域；T21/T22）。

内容：里程碑进度 / 偏差 / 逾期清单（需求书 §5.4、§11.2）。
"""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from ..audit import write_log
from ..config import settings
from ..models import CheckpointSignal, DEFAULT_PROJECT_ID, MetricRecord, Project, TaskCard
from ..utils import today_str
from .five_libs import ensure_libraries

TERMINAL = ("关闭", "取消")
DONE = ("通过", "关闭")


def _pct(num: int, den: int) -> float:
    return round(num * 100.0 / den, 1) if den else 0.0


def compute_metrics(db: Session, project_id: str = DEFAULT_PROJECT_ID, period: str | None = None) -> dict:
    tasks: list[TaskCard] = db.query(TaskCard).filter(TaskCard.project_id == project_id).all()
    today = datetime.now(tz=timezone.utc).date()

    task_total = len(tasks)
    closed = [t for t in tasks if t.status in DONE]
    ai_tasks = [t for t in tasks if t.ai_executor]
    ai_done = [t for t in ai_tasks if t.status in DONE]
    review_entered = [t for t in tasks if t.status in ("待评审", "通过", "关闭", "返工") or (t.rework_count or 0) > 0]
    review_closed = [t for t in tasks if t.status in DONE]

    def _due(t: TaskCard):
        try:
            return datetime.strptime(t.due_date or "", "%Y-%m-%d").date()
        except ValueError:
            return None

    closed_with_due = [t for t in closed if _due(t)]
    on_time = [
        t for t in closed_with_due
        if (t.updated_at or datetime.now(tz=timezone.utc)).date() <= _due(t)  # type: ignore[operator]
    ]
    blocked = [t for t in tasks if t.status == "阻塞"]
    overdue = [
        t for t in tasks
        if t.status not in TERMINAL and (d := _due(t)) is not None and d < today
    ]

    return {
        "period": period or today_str(),
        "task_total": task_total,
        "task_closed": len(closed),
        "overdue_count": len(overdue),
        "blocked_count": len(blocked),
        "on_time_rate": 100.0 if not closed_with_due else _pct(len(on_time), len(closed_with_due)),
        "rework_rate": _pct(len([t for t in tasks if (t.rework_count or 0) > 0]), task_total),
        "ai_adoption_rate": _pct(len(ai_done), len(ai_tasks)),
        "review_close_rate": _pct(len(review_closed), len(review_entered)),
        "open_checkpoints": db.query(CheckpointSignal).filter(
            CheckpointSignal.status == "待处理",
            CheckpointSignal.project_id == project_id,
        ).count(),
        "overdue_list": [
            {"code": t.code, "title": t.title, "due_date": t.due_date, "status": t.status,
             "owner": t.human_owner or "H", "ai": t.ai_executor}
            for t in sorted(overdue, key=lambda x: x.due_date or "")
        ],
        "blocked_list": [
            {"code": t.code, "title": t.title, "reason": t.blocked_reason, "status": t.status}
            for t in blocked
        ],
    }


def render_digest(md: dict) -> str:
    lines = [
        f"# 每日摘要 {md['period']}",
        "",
        "## 里程碑进度",
        f"- 任务总数 {md['task_total']}，已完成 {md['task_closed']}，待处理卡点 {md['open_checkpoints']}",
        f"- 进度：{ _pct(md['task_closed'], md['task_total']) }%",
        "",
        "## 四指标（需求书 §11.1）",
        f"- 按期率：{md['on_time_rate']}%",
        f"- 返工率：{md['rework_rate']}%",
        f"- AI 产出采纳率：{md['ai_adoption_rate']}%",
        f"- 评审问题关闭率：{md['review_close_rate']}%",
        "",
        "## 偏差与逾期",
    ]
    if md["overdue_list"]:
        lines += [f"- 逾期 {len(md['overdue_list'])} 项："]
        lines += [f"  - {i['code']} {i['title']}（截止 {i['due_date']}，{i['status']}，负责人 {i['owner']}）"
                  for i in md["overdue_list"]]
    else:
        lines.append("- 无逾期任务")
    if md["blocked_list"]:
        lines += [f"- 阻塞 {len(md['blocked_list'])} 项："]
        lines += [f"  - {i['code']} {i['title']}：{i['reason'] or '（未填原因）'}" for i in md["blocked_list"]]
    lines += ["", "> 本摘要由 PM-Collab 自动生成，数据来源服务层唯一入库入口。", ""]
    return "\n".join(lines)


def generate_daily_digest(db: Session, project_id: str = DEFAULT_PROJECT_ID, push: bool = True) -> MetricRecord:
    """生成并记录每日摘要（含文件归档与推送），按项目隔离。"""
    ensure_libraries()
    md = compute_metrics(db, project_id=project_id)
    text = render_digest(md)

    proj = db.get(Project, project_id)
    proj_code = proj.code if proj else "PM-Collab"

    record = MetricRecord(
        period=md["period"],
        project_id=project_id,
        on_time_rate=md["on_time_rate"],
        rework_rate=md["rework_rate"],
        ai_adoption_rate=md["ai_adoption_rate"],
        review_close_rate=md["review_close_rate"],
        task_total=md["task_total"],
        task_closed=md["task_closed"],
        overdue_count=md["overdue_count"],
        blocked_count=md["blocked_count"],
        summary_text=text,
    )
    db.add(record)
    db.flush()

    path = settings.data_dir / "03_日志" / "日报周报" / f"{proj_code}-日报-{md['period']}-V1.0.0.md"
    Path(path).write_text(text, encoding="utf-8")

    write_log(db, actor="PM-AI", action="生成每日摘要", change=f"周期 {md['period']}",
              artifact_path=str(path), next_step="推送至 H")
    db.commit()

    if push:
        channel = push_digest(text)
        record.pushed_at = datetime.now(tz=timezone.utc)
        db.commit()
        print(f"[digest] {md['period']} 摘要已推送（{channel}）：{path}")
    return record


def push_digest(text: str) -> str:
    """推送：默认本地日志留痕；配置 webhook 时同步外发（可选渠道，非强依赖）。"""
    print("=" * 60)
    print(text)
    print("=" * 60)
    if settings.feishu_webhook:
        try:
            req = urllib.request.Request(
                settings.feishu_webhook,
                data=json.dumps({"msg_type": "text", "content": {"text": text[:4000]}}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=8) as resp:  # noqa: S310
                return f"webhook:{resp.status}"
        except Exception as exc:  # 推送失败不影响摘要生成与留痕
            print(f"[digest] webhook 推送失败：{exc}")
            return "webhook-failed"
    return "local-log"
