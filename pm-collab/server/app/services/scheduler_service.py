"""APScheduler：每日摘要定时生成与推送（T21/T22）。"""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from ..config import settings
from ..db import SessionLocal
from .digest import generate_daily_digest

_scheduler: BackgroundScheduler | None = None


def _digest_job() -> None:
    db = SessionLocal()
    try:
        record = generate_daily_digest(db, push=True)
        print(f"[scheduler] 每日摘要已生成：{record.period}")
    except Exception as exc:  # 调度任务异常不得影响服务
        print(f"[scheduler] 摘要生成失败：{exc}")
    finally:
        db.close()


def start_scheduler() -> bool:
    global _scheduler
    if not settings.scheduler_enabled or _scheduler is not None:
        return False
    sched = BackgroundScheduler(timezone="Asia/Shanghai")
    sched.add_job(
        _digest_job,
        CronTrigger(hour=settings.daily_digest_hour, minute=settings.daily_digest_minute),
        id="daily_digest",
        replace_existing=True,
    )
    sched.start()
    _scheduler = sched
    print(f"[scheduler] 每日摘要定时任务已启动：每天 "
          f"{settings.daily_digest_hour:02d}:{settings.daily_digest_minute:02d}")
    return True


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
