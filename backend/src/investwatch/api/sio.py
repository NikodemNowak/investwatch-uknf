"""Socket.IO server (ADR 0004). Workers publish through Redis; this process relays to clients."""

from __future__ import annotations

import logging
from typing import Any

import socketio

from investwatch.config import get_settings

log = logging.getLogger(__name__)


def create_server() -> socketio.AsyncServer:
    """Build the ASGI Socket.IO server, Redis-backed unless configured for memory."""
    settings = get_settings()
    manager = (
        socketio.AsyncRedisManager(settings.redis_url)
        if settings.realtime_backend == "redis"
        else None
    )
    server = socketio.AsyncServer(
        async_mode="asgi",
        client_manager=manager,
        cors_allowed_origins=settings.cors_origin_list,
    )

    @server.event
    async def connect(sid: str, environ: dict[str, Any]) -> None:
        log.info("socket.io client connected: %s", sid)

    @server.event
    async def disconnect(sid: str, *args: Any) -> None:
        log.info("socket.io client disconnected: %s", sid)

    return server


sio = create_server()
