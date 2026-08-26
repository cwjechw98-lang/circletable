from __future__ import annotations

import asyncio
import re
import shutil
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from defaults import pick_observer_provider
from http_api.deps import get_runtime
from http_api.helpers import (
    broadcast_planned_events,
    coerce_event_description,
    coerce_event_round,
    coerce_room_settings,
    knowledge_status_payload,
    list_room_documents,
    resolve_event_session_id,
    room_loaded_payload,
    room_upload_dir,
    start_room_knowledge_rebuild,
)
from knowledge.file_parser import SUPPORTED_EXTENSIONS
from knowledge.lightrag_adapter import get_knowledge_graph


router = APIRouter()


@router.get("/api/rooms")
async def list_rooms(request: Request):
    runtime = get_runtime(request)
    return {
        "rooms": runtime.repository.list_rooms(),
        "currentRoomId": runtime.repository.get_current_room_id(),
    }


@router.post("/api/rooms")
async def create_room(request: Request, payload: dict):
    runtime = get_runtime(request)
    providers = await runtime.providers_payload()
    observer_provider, observer_model = pick_observer_provider(providers)
    room_id = runtime.repository.create_room(
        name=(payload.get("name") or "Новая комната").strip(),
        observer_mode=payload.get("observerMode") or "suggest",
        observer_provider=payload.get("observerProvider") or observer_provider,
        observer_model=payload.get("observerModel") or observer_model,
        density_mode=payload.get("densityMode") or "normal",
    )
    runtime.repository.set_current_room(room_id)
    snapshot = runtime.repository.get_room_snapshot(room_id)
    await runtime.manager.broadcast(room_loaded_payload(runtime, snapshot, current_room_id=room_id))
    return snapshot


@router.get("/api/rooms/{room_id}")
async def get_room(request: Request, room_id: str):
    runtime = get_runtime(request)
    snapshot = runtime.repository.get_room_snapshot(room_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Комната не найдена")
    return snapshot


@router.patch("/api/rooms/{room_id}")
async def patch_room(request: Request, room_id: str, payload: dict):
    runtime = get_runtime(request)
    snapshot = runtime.repository.get_room_snapshot(room_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Комната не найдена")
    room_settings = coerce_room_settings(payload, snapshot["room"].get("settings"))
    runtime.repository.update_room_settings(
        room_id,
        name=payload.get("name"),
        observer_mode=payload.get("observerMode"),
        density_mode=payload.get("densityMode"),
        observer_provider=payload.get("observerProvider"),
        observer_model=payload.get("observerModel"),
        settings=room_settings,
    )
    updated = runtime.repository.get_room_snapshot(room_id)
    await runtime.manager.broadcast(room_loaded_payload(runtime, updated, current_room_id=room_id))
    return updated


@router.delete("/api/rooms/{room_id}")
async def delete_room(request: Request, room_id: str):
    runtime = get_runtime(request)
    snapshot = runtime.repository.get_room_snapshot(room_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Комната не найдена")
    runtime.repository.delete_room(room_id)
    current_room_id = runtime.repository.get_current_room_id()
    current_snapshot = runtime.repository.get_room_snapshot(current_room_id) if current_room_id else None
    await runtime.manager.broadcast(room_loaded_payload(runtime, current_snapshot, current_room_id=current_room_id))
    return {"ok": True}


@router.get("/api/rooms/{room_id}/events")
async def list_room_events(request: Request, room_id: str):
    runtime = get_runtime(request)
    if not runtime.repository.room_exists(room_id):
        raise HTTPException(status_code=404, detail="Комната не найдена")
    current_session = runtime.repository.get_current_session(room_id)
    session_id = current_session["id"] if current_session else None
    return {"events": runtime.repository.list_planned_events(room_id, session_id)}


@router.post("/api/rooms/{room_id}/events")
async def create_room_event(request: Request, room_id: str, payload: dict):
    runtime = get_runtime(request)
    if not runtime.repository.room_exists(room_id):
        raise HTTPException(status_code=404, detail="Комната не найдена")
    target_round = coerce_event_round(payload)
    description = coerce_event_description(payload)
    session_id = resolve_event_session_id(runtime, room_id, payload)
    event = runtime.repository.create_planned_event(room_id, target_round, description, session_id)
    await broadcast_planned_events(runtime, room_id, session_id)
    return {"event": event, "events": runtime.repository.list_planned_events(room_id, session_id)}


@router.patch("/api/rooms/{room_id}/events/{event_id}")
async def patch_room_event(request: Request, room_id: str, event_id: str, payload: dict):
    runtime = get_runtime(request)
    if not runtime.repository.room_exists(room_id):
        raise HTTPException(status_code=404, detail="Комната не найдена")
    if "targetRound" in payload or "target_round" in payload:
        payload = {**payload, "targetRound": coerce_event_round(payload)}
    if "description" in payload:
        payload = {**payload, "description": coerce_event_description(payload)}
    if "sessionId" in payload or "session_id" in payload:
        payload = {**payload, "sessionId": resolve_event_session_id(runtime, room_id, payload)}
    event = runtime.repository.update_planned_event(room_id, event_id, payload)
    if not event:
        raise HTTPException(status_code=404, detail="Событие не найдено")
    await broadcast_planned_events(runtime, room_id, event.get("sessionId"))
    return {"event": event, "events": runtime.repository.list_planned_events(room_id, event.get("sessionId"))}


@router.delete("/api/rooms/{room_id}/events/{event_id}")
async def delete_room_event(request: Request, room_id: str, event_id: str):
    runtime = get_runtime(request)
    if not runtime.repository.room_exists(room_id):
        raise HTTPException(status_code=404, detail="Комната не найдена")
    existing = runtime.repository.get_planned_event(room_id, event_id)
    deleted = runtime.repository.delete_planned_event(room_id, event_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Событие не найдено")
    await broadcast_planned_events(runtime, room_id, existing.get("sessionId") if existing else None)
    return {"ok": True}


@router.post("/api/rooms/{room_id}/documents")
async def upload_room_document(request: Request, room_id: str, file: UploadFile = File(...)):
    runtime = get_runtime(request)
    if not runtime.repository.room_exists(room_id):
        raise HTTPException(status_code=404, detail="Комната не найдена")
    file_ext = Path(file.filename or "").suffix.lower()
    if file_ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Неподдерживаемый формат. Допустимые: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )
    upload_dir = room_upload_dir(runtime, room_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^\w.\-]", "_", Path(file.filename or "unnamed").name)
    dest = upload_dir / safe_name
    previous_graph_id = runtime.repository.get_room_graph_id(room_id)
    dest.write_bytes(await file.read())
    files = list_room_documents(runtime, room_id)
    knowledge = await start_room_knowledge_rebuild(runtime, room_id, previous_graph_id)
    return {"ok": True, "filename": safe_name, "files": files, "knowledge": knowledge}


@router.get("/api/rooms/{room_id}/documents")
async def list_documents(request: Request, room_id: str):
    runtime = get_runtime(request)
    if not runtime.repository.room_exists(room_id):
        raise HTTPException(status_code=404, detail="Комната не найдена")
    return {"files": list_room_documents(runtime, room_id), "knowledge": await knowledge_status_payload(runtime, room_id)}


@router.delete("/api/rooms/{room_id}/documents/{filename}")
async def delete_room_document(request: Request, room_id: str, filename: str):
    runtime = get_runtime(request)
    if not runtime.repository.room_exists(room_id):
        raise HTTPException(status_code=404, detail="Комната не найдена")
    safe_name = re.sub(r"[^\w.\-]", "_", filename)
    dest = room_upload_dir(runtime, room_id) / safe_name
    if not dest.exists():
        raise HTTPException(status_code=404, detail="Файл не найден")
    previous_graph_id = runtime.repository.get_room_graph_id(room_id)
    dest.unlink()
    files = list_room_documents(runtime, room_id)
    knowledge = await start_room_knowledge_rebuild(runtime, room_id, previous_graph_id)
    return {"ok": True, "files": files, "knowledge": knowledge}


@router.get("/api/rooms/{room_id}/knowledge/status")
async def get_room_knowledge_status(request: Request, room_id: str):
    runtime = get_runtime(request)
    if not runtime.repository.room_exists(room_id):
        raise HTTPException(status_code=404, detail="Комната не найдена")
    return await knowledge_status_payload(runtime, room_id)


@router.get("/api/rooms/{room_id}/knowledge/graph")
async def get_room_knowledge_graph(request: Request, room_id: str):
    runtime = get_runtime(request)
    if not runtime.repository.room_exists(room_id):
        raise HTTPException(status_code=404, detail="Комната не найдена")
    graph_id = runtime.repository.get_room_graph_id(room_id)
    if not graph_id:
        raise HTTPException(status_code=404, detail="Граф знаний ещё не создан")
    graph = await asyncio.to_thread(get_knowledge_graph, graph_id)
    return {"graphId": graph_id, "graph": graph}


@router.delete("/api/rooms/{room_id}/knowledge")
async def delete_room_knowledge(request: Request, room_id: str):
    runtime = get_runtime(request)
    if not runtime.repository.room_exists(room_id):
        raise HTTPException(status_code=404, detail="Комната не найдена")
    previous_graph_id = runtime.repository.get_room_graph_id(room_id)
    upload_dir = room_upload_dir(runtime, room_id)
    if upload_dir.exists():
        shutil.rmtree(upload_dir)
    knowledge = await start_room_knowledge_rebuild(runtime, room_id, previous_graph_id)
    return {"ok": True, "files": [], "knowledge": knowledge}
