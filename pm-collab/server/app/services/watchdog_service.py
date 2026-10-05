"""交接区 watchdog 监听（T13）：文件落盘即触发入库。

.debounce 合并同一批次事件；入库在独立线程会话中完成，避免阻塞主线程。
"""
from __future__ import annotations

import threading
from typing import Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from ..config import settings
from ..db import SessionLocal
from .five_libs import HANDOFF_ZONES, ensure_libraries

DEBOUNCE_SECONDS = 0.6


class _DebouncedHandler(FileSystemEventHandler):
    def __init__(self, on_batch: Callable[[], None]) -> None:
        self._on_batch = on_batch
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def _schedule(self) -> None:
        with self._lock:
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(DEBOUNCE_SECONDS, self._run)
            self._timer.daemon = True
            self._timer.start()

    def _run(self) -> None:
        try:
            self._on_batch()
        except Exception as exc:  # 监听线程异常不得拖垮服务
            print(f"[watchdog] 同步异常：{exc}")

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        if event.src_path.endswith(".tmp") or "~" in event.src_path:
            return
        self._schedule()


class HandoffWatcher:
    def __init__(self) -> None:
        self.observer: Observer | None = None

    def _batch_sync(self) -> None:
        from .handoff_sync import sync_from_zone

        db = SessionLocal()
        try:
            result = sync_from_zone(db, actor="watchdog")
            print(f"[watchdog] 交接区同步：{result}")
        finally:
            db.close()

    def start(self) -> bool:
        if not settings.watchdog_enabled:
            return False
        ensure_libraries()
        handler = _DebouncedHandler(self._batch_sync)
        observer = Observer()
        for zone in HANDOFF_ZONES:
            observer.schedule(handler, str(settings.handoff_dir / zone), recursive=True)
        observer.schedule(handler, str(settings.handoff_dir), recursive=False)
        observer.daemon = True
        observer.start()
        self.observer = observer
        return True

    def stop(self) -> None:
        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=3)
            self.observer = None


watcher = HandoffWatcher()
