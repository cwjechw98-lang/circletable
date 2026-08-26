from __future__ import annotations

from fastapi import APIRouter, Request

from http_api.deps import get_runtime
from http_api.helpers import spawn_shutdown_helper


router = APIRouter()


@router.get("/api/providers")
async def list_providers(request: Request):
    runtime = get_runtime(request)
    return await runtime.providers_payload()


@router.post("/api/providers/refresh")
async def refresh_providers(request: Request):
    runtime = get_runtime(request)
    providers = await runtime.providers_payload()
    await runtime.manager.broadcast({"type": "providers", "providers": providers})
    return {"ok": True, "providers": providers}


@router.post("/api/system/shutdown")
async def shutdown_app(request: Request):
    runtime = get_runtime(request)
    current_room_id = runtime.repository.get_current_room_id()
    current_session = runtime.repository.get_current_session(current_room_id) if current_room_id else None

    if current_room_id and current_session and current_session["status"] not in {"completed", "stopped"}:
        runtime.repository.update_session(current_session["id"], {"status": "paused"})
        runtime.repository.add_room_event(
            current_room_id,
            current_session["id"],
            "app_shutdown_requested",
            {"source": "ui"},
        )

    runtime.repository.normalize_incomplete_sessions()

    await runtime.manager.broadcast({
        "type": "app_shutdown_requested",
        "message": "Сеанс сохраняется. Окна запуска сейчас закроются.",
    })

    spawn_shutdown_helper()
    return {"ok": True}
