"""WebSocket：卡点队列实时刷新（设计大纲 §10.2）。"""
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..services.events import hub

router = APIRouter(tags=["实时通道"])


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    hub.register(ws)
    try:
        while True:
            await ws.receive_text()  # 保持连接；服务端单向推送
    except WebSocketDisconnect:
        hub.unregister(ws)
    except Exception:
        hub.unregister(ws)
