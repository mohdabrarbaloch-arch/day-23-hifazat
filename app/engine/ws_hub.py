"""In-memory WebSocket hub.

Keeps a set of live connections per user and publishes alert events to them.

Sync request handlers run in a threadpool with no running event loop, so the
hub captures the application's main loop at startup and schedules sends onto
it with `run_coroutine_threadsafe`. Without that, an alert raised from a sync
endpoint would silently never reach the socket.

Scaling note: in multi-worker production this should be Redis pub/sub with a
dedicated WebSocket gateway; the interface here stays the same.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict

from fastapi import WebSocket

_lock = asyncio.Lock()
_connections: dict[int, set[WebSocket]] = defaultdict(set)
_main_loop: asyncio.AbstractEventLoop | None = None


class Hub:
    """Broadcast JSON events to all live sockets of a user."""

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Record the app's main event loop (called once at startup)."""
        global _main_loop
        _main_loop = loop

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        async with _lock:
            _connections[user_id].add(websocket)

    async def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        async with _lock:
            _connections.get(user_id, set()).discard(websocket)
            if not _connections.get(user_id):
                _connections.pop(user_id, None)

    async def send_json(self, user_id: int, message: dict) -> None:
        text = json.dumps(message)
        async with _lock:
            targets = list(_connections.get(user_id, set()))
        for ws in targets:
            try:
                await ws.send_text(text)
            except Exception:
                # A dead socket must not break the loop; cleanup happens on
                # the next disconnect event.
                pass

    def publish(self, user_id: int, message: dict) -> None:
        """Schedule a send from any thread (sync handlers included)."""
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None

        if running is not None:
            # Already on an event loop (async handler) — schedule directly.
            running.create_task(self.send_json(user_id, message))
            return

        if _main_loop is not None and _main_loop.is_running():
            asyncio.run_coroutine_threadsafe(self.send_json(user_id, message), _main_loop)


hub = Hub()
