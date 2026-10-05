"""轻量事件总线：WebSocket 实时推送（卡点队列 / 看板刷新）。"""
from __future__ import annotations

import asyncio
import json
from typing import Any

_ws_clients: set[Any] = set()
_sync_publish = None  # 由 FastAPI 启动注入（用于同步线程环境）


class EventHub:
    def register(self, ws: Any) -> None:
        _ws_clients.add(ws)

    def unregister(self, ws: Any) -> None:
        _ws_clients.discard(ws)

    def publish(self, event: str, payload: dict[str, Any]) -> None:
        """线程安全发布：无论在同步线程还是协程中被调用。"""
        message = json.dumps({"event": event, "data": payload}, ensure_ascii=False)

        async def _broadcast() -> None:
            for ws in list(_ws_clients):
                try:
                    await ws.send_text(message)
                except Exception:
                    _ws_clients.discard(ws)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            loop.create_task(_broadcast())
        elif _sync_publish is not None:
            _sync_publish(message)


hub = EventHub()
