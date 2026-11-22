"""ASGI entry point: FastAPI under `/api`, Socket.IO under `/socket.io`."""

from __future__ import annotations

import logging

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from investwatch.api import (
    calibration,
    check,
    connectors,
    entities,
    findings,
    firms,
    health,
    imports,
    objects,
    posts,
    reports,
    settings,
    sources,
    stats,
    system,
    trace,
)
from investwatch.api.sio import sio
from investwatch.config import get_settings

logging.basicConfig(level=get_settings().log_level)

api = FastAPI(title="InvestWatch", version="0.1.0")
api.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)
for module in (
    health,
    findings,
    entities,
    stats,
    settings,
    calibration,
    check,
    connectors,
    imports,
    sources,
    firms,
    objects,
    posts,
    reports,
    system,
    trace,
):
    api.include_router(module.router, prefix="/api")

app = socketio.ASGIApp(sio, other_asgi_app=api, socketio_path="socket.io")
