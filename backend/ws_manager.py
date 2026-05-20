"""
ws_manager.py — WebSocket connection manager.

Maintains a list of active WebSocket connections and broadcasts JSON events
to all of them. Dead connections are pruned silently on each broadcast.

Module-level singleton `manager` is imported by:
  - main.py          (to accept/disconnect connections in the /ws endpoint)
  - pin_service.py   (to broadcast gesture and lock-state events)
  - lock_service.py  (to broadcast lock-state-changed events on manual updates)
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages a pool of active WebSocket connections."""

    def __init__(self) -> None:
        self._active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        """Accept the WebSocket handshake and register the connection."""
        await ws.accept()
        self._active.append(ws)
        logger.info("WS client connected. Total connections: %d", len(self._active))

    def disconnect(self, ws: WebSocket) -> None:
        """Remove a connection from the pool."""
        self._active = [c for c in self._active if c is not ws]
        logger.info("WS client disconnected. Total connections: %d", len(self._active))

    async def broadcast(self, payload: dict[str, Any]) -> None:
        """
        Send a JSON payload to all connected clients.

        Clients that have disconnected since the last broadcast are removed
        silently from the pool.
        """
        dead: list[WebSocket] = []
        for ws in list(self._active):
            try:
                await ws.send_json(payload)
            except Exception as exc:
                logger.debug("WS send failed (%s) — marking for removal", exc)
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


# Module-level singleton — import this directly wherever broadcasting is needed
manager = ConnectionManager()
