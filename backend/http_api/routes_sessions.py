from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from http_api.deps import get_runtime
from http_api.helpers import launch_fact_check_task, launch_report_task, resolve_fact_check_scope, room_loaded_payload


router = APIRouter()


@router.get("/api/rooms/{room_id}/sessions")
async def list_room_sessions(request: Request, room_id: str, query: str = ""):
    runtime = get_runtime(request)
    if not runtime.repository.room_exists(room_id):
        raise HTTPException(status_code=404, detail="Комната не найдена")
    return {"sessions": runtime.repository.list_room_sessions(room_id, query=query)}


@router.get("/api/sessions/{session_id}")
async def get_session(request: Request, session_id: str):
    runtime = get_runtime(request)
    snapshot = runtime.repository.get_session_snapshot(session_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    return snapshot


@router.get("/api/sessions/{session_id}/report")
async def get_session_report(request: Request, session_id: str):
    runtime = get_runtime(request)
    if not runtime.repository.get_session(session_id):
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    return {"report": runtime.repository.get_latest_report(session_id)}


@router.post("/api/sessions/{session_id}/report")
async def generate_session_report(request: Request, session_id: str, payload: dict | None = None):
    runtime = get_runtime(request)
    session = runtime.repository.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    if session["status"] not in {"completed", "stopped"}:
        raise HTTPException(status_code=409, detail="Итоговый отчёт доступен только после завершения или остановки сессии")
    payload = payload or {}
    launch_report_task(runtime, session_id, payload.get("provider"), payload.get("model"))
    return {
        "ok": True,
        "report": runtime.repository.get_latest_report(session_id),
        "status": "queued",
    }


@router.get("/api/sessions/{session_id}/fact-check")
async def get_session_fact_check(request: Request, session_id: str, run_id: str | None = None):
    runtime = get_runtime(request)
    if not runtime.repository.get_session(session_id):
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    run = runtime.repository.get_fact_check_run(run_id) if run_id else runtime.repository.get_latest_fact_check_run(session_id)
    if run_id and not run:
        raise HTTPException(status_code=404, detail="Запуск фактчекинга не найден")
    return {"factCheck": run}


@router.post("/api/sessions/{session_id}/fact-check")
async def run_session_fact_check(request: Request, session_id: str, payload: dict | None = None):
    runtime = get_runtime(request)
    session = runtime.repository.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    if session["status"] not in {"paused", "completed", "stopped"}:
        raise HTTPException(status_code=409, detail="Ручной фактчекинг доступен на паузе или после завершения сессии")

    payload = payload or {}
    scope, target_round = resolve_fact_check_scope(session, payload.get("scope"), payload.get("targetRound"))
    reusable = runtime.repository.find_reusable_fact_check_run(session_id, scope, target_round)
    if reusable:
        if reusable["status"] in {"queued", "running"}:
            launch_fact_check_task(runtime, reusable["id"])
        return {"factCheck": reusable, "reused": True}

    snapshot = runtime.repository.get_session_snapshot(session_id, make_current=False)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    internet_mode = snapshot["room"].get("internetMode") or "auto"
    run = runtime.repository.create_fact_check_run(
        room_id=snapshot["room"]["id"],
        session_id=session_id,
        scope=scope,
        target_round=target_round,
        internet_mode=internet_mode,
        provider=session.get("observerProvider") or snapshot["room"].get("observerProvider"),
        model=session.get("observerModel") or snapshot["room"].get("observerModel"),
    )
    launch_fact_check_task(runtime, run["id"])
    return {"factCheck": run, "reused": False}


@router.post("/api/sessions/{session_id}/open")
async def open_session(request: Request, session_id: str):
    runtime = get_runtime(request)
    snapshot = runtime.repository.set_current_session(session_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    payload = room_loaded_payload(runtime, snapshot, current_room_id=snapshot["room"]["id"])
    await runtime.manager.broadcast(payload)
    return payload


@router.post("/api/sessions/{session_id}/continue")
async def continue_session_endpoint(request: Request, session_id: str):
    runtime = get_runtime(request)
    if runtime.engine.running:
        cid = runtime.engine.current_session_id
        if cid and cid != session_id:
            raise HTTPException(status_code=409, detail="Сначала остановите текущую сессию")
    await runtime.engine.continue_session(session_id)
    snapshot = runtime.repository.get_session_snapshot(session_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    return room_loaded_payload(runtime, snapshot, current_room_id=snapshot["room"]["id"])


@router.post("/api/sessions/{session_id}/fork")
async def fork_session(request: Request, session_id: str):
    runtime = get_runtime(request)
    session = runtime.repository.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    new_session = runtime.repository.create_session_from_final(session_id)
    if not new_session:
        raise HTTPException(status_code=400, detail="Не удалось создать продолжение")
    snapshot = runtime.repository.get_session_snapshot(new_session["id"], make_current=True)
    await runtime.manager.broadcast(room_loaded_payload(runtime, snapshot, current_room_id=snapshot["room"]["id"]))
    return snapshot


@router.patch("/api/sessions/{session_id}")
async def patch_session(request: Request, session_id: str, payload: dict):
    runtime = get_runtime(request)
    if not runtime.repository.get_session(session_id):
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    runtime.repository.rename_session(session_id, payload.get("title") or "")
    snapshot = runtime.repository.get_session_snapshot(session_id)
    return room_loaded_payload(runtime, snapshot, current_room_id=snapshot["room"]["id"])


@router.delete("/api/sessions/{session_id}")
async def delete_session(request: Request, session_id: str):
    runtime = get_runtime(request)
    if runtime.engine.current_session_id == session_id and runtime.engine.running:
        raise HTTPException(status_code=409, detail="Сначала остановите текущую сессию")
    session = runtime.repository.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    snapshot = runtime.repository.get_session_snapshot(session_id)
    room_id = snapshot["room"]["id"]
    runtime.repository.delete_session(session_id)
    current_room_id = runtime.repository.get_current_room_id()
    current_snapshot = runtime.repository.get_room_snapshot(current_room_id) if current_room_id else None
    await runtime.manager.broadcast(room_loaded_payload(runtime, current_snapshot, current_room_id=current_room_id))
    return {"ok": True, "roomId": room_id}


@router.get("/api/sessions/{session_id}/export.md")
async def export_session(request: Request, session_id: str):
    runtime = get_runtime(request)
    text = runtime.repository.export_session_markdown(session_id)
    if text is None:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    return PlainTextResponse(
        text,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="circletable-{session_id}.md"'},
    )


@router.post("/api/messages/{message_id}/pin")
async def toggle_message_pin(request: Request, message_id: str, payload: dict):
    runtime = get_runtime(request)
    session_id = payload.get("sessionId")
    room_id = payload.get("roomId")
    if not session_id or not room_id:
        raise HTTPException(status_code=400, detail="Не хватает roomId или sessionId")
    result = runtime.repository.toggle_message_pin(room_id, session_id, message_id)
    snapshot = runtime.repository.get_session_snapshot(session_id)
    await runtime.manager.broadcast({
        "type": "message_pin_toggled",
        "messageId": result["messageId"],
        "pinned": result["pinned"],
        "pinnedMessages": result["pinnedMessages"],
        "messages": snapshot["messages"] if snapshot else [],
    })
    return result
