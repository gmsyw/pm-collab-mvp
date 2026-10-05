"""watchdog 监听、调度器与 WS 事件总线测试（T13/T21/T16）。"""
from __future__ import annotations

import asyncio
import json
import time

from server.app.services import events
from server.app.services.handoff_sync import ledger_path
from server.app.services.scheduler_service import (start_scheduler, stop_scheduler,
                                                   _digest_job)
from server.app.services.watchdog_service import watcher


def test_watchdog_picks_up_zone_file(db, data_dir, monkeypatch):
    """文件落盘 → 监听触发 → 入库（文件系统即消息总线）。"""
    from server.app import config

    monkeypatch.setattr(config.settings, "watchdog_enabled", True)
    order = {"project": "PM-Collab", "updated_at": "",
             "orders": [{"code": "HO-WATCH", "sender": "PM-AI", "receiver": "DEV-AI",
                         "zone": "派单", "payload_path": "", "status": "待投喂",
                         "task_code": "T01", "content_hash": ""}]}
    started = watcher.start()
    try:
        assert started
        time.sleep(0.3)
        ledger_path().write_text(json.dumps(order, ensure_ascii=False, indent=2), encoding="utf-8")
        from server.app.models import HandoffOrder

        for _ in range(40):  # 去抖 0.6s，最多等 4s
            time.sleep(0.1)
            db.expire_all()
            if db.query(HandoffOrder).filter(HandoffOrder.code == "HO-WATCH").first():
                break

        row = db.query(HandoffOrder).filter(HandoffOrder.code == "HO-WATCH").first()
        assert row is not None and row.status == "待投喂"
    finally:
        watcher.stop()
        assert watcher.observer is None


def test_scheduler_start_and_stop(db, monkeypatch):
    from server.app import config

    monkeypatch.setattr(config.settings, "scheduler_enabled", True)
    assert start_scheduler() is True
    assert start_scheduler() is False  # 幂等
    stop_scheduler()
    assert start_scheduler() is True
    stop_scheduler()


def test_digest_job_runs_without_error(db, data_dir):
    _digest_job()
    from server.app.models import MetricRecord

    assert db.query(MetricRecord).count() >= 1


def test_push_via_unreachable_webhook(db, data_dir, monkeypatch):
    from server.app.services import digest as digest_mod

    monkeypatch.setattr(digest_mod.settings, "feishu_webhook", "http://127.0.0.1:9/hook")
    assert digest_mod.push_digest("测试摘要") == "webhook-failed"


def test_event_hub_sync_and_async_paths():
    sent: list[str] = []

    class FakeWS:
        async def send_text(self, msg: str) -> None:
            sent.append(msg)

    fake = FakeWS()
    events.hub.register(fake)
    events._sync_publish = lambda msg: sent.append(msg)
    try:
        events.hub.publish("checkpoint", {"content": "同步路径"})
    finally:
        events._sync_publish = None
    assert sent and "同步路径" in sent[0]

    async def _async_path():
        events.hub.publish("checkpoint", {"content": "异步路径"})
        await asyncio.sleep(0)

    asyncio.run(_async_path())
    events.hub.unregister(fake)
    assert any("异步路径" in s for s in sent)


def test_event_hub_drops_failing_client():
    class BrokenWS:
        async def send_text(self, msg: str) -> None:
            raise RuntimeError("closed")

    events.hub.register(BrokenWS())

    async def _run():
        events.hub.publish("checkpoint", {"content": "断线客户端"})
        await asyncio.sleep(0)

    asyncio.run(_run())
    assert len(events._ws_clients) == 0


def test_ws_endpoint_registers_and_releases_client(app_client):
    with app_client.websocket_connect("/ws") as ws:
        for _ in range(20):
            if events._ws_clients:
                break
            time.sleep(0.05)
        assert len(events._ws_clients) == 1
        ws.close()
    for _ in range(20):  # 服务端断开后应自动注销
        if not events._ws_clients:
            break
        time.sleep(0.05)
    assert len(events._ws_clients) == 0
