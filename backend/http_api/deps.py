from __future__ import annotations

from fastapi import Request, WebSocket

from app_runtime import AppRuntime


def get_runtime_from_app(app) -> AppRuntime:
    runtime = getattr(app.state, "runtime", None)
    if runtime is None:
        raise RuntimeError("App runtime is not initialized")
    return runtime


def get_runtime(request: Request) -> AppRuntime:
    return get_runtime_from_app(request.app)


def get_ws_runtime(ws: WebSocket) -> AppRuntime:
    return get_runtime_from_app(ws.app)
