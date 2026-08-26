from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from app_runtime import AppRuntime
from knowledge.file_parser import SUPPORTED_EXTENSIONS
from knowledge.lightrag_adapter import delete_graph as delete_knowledge_graph
from knowledge.lightrag_adapter import get_knowledge_graph


def spawn_shutdown_helper():
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    script_path = os.path.join(root_dir, "shutdown_round_table.ps1")
    if not os.path.exists(script_path):
        raise FileNotFoundError(script_path)

    creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            script_path,
        ],
        cwd=root_dir,
        creationflags=creationflags,
    )


def room_upload_dir(runtime: AppRuntime, room_id: str) -> Path:
    return runtime.uploads_root / room_id


def list_room_documents(runtime: AppRuntime, room_id: str) -> list[dict[str, Any]]:
    upload_dir = room_upload_dir(runtime, room_id)
    if not upload_dir.exists():
        return []
    return [
        {"name": path.name, "size": path.stat().st_size}
        for path in sorted(upload_dir.iterdir())
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]


def room_document_paths(runtime: AppRuntime, room_id: str) -> list[str]:
    upload_dir = room_upload_dir(runtime, room_id)
    if not upload_dir.exists():
        return []
    return [
        str(path)
        for path in sorted(upload_dir.iterdir())
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]


def knowledge_uploads_exist(runtime: AppRuntime, room_id: str) -> bool:
    room_dir = room_upload_dir(runtime, room_id)
    return room_dir.exists() and any(room_dir.rglob("*"))


def coerce_event_round(payload: dict) -> int:
    raw_round = payload.get("targetRound", payload.get("target_round"))
    try:
        target_round = int(raw_round)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Укажите номер раунда") from exc
    if target_round < 1:
        raise HTTPException(status_code=400, detail="Раунд должен быть больше нуля")
    return target_round


def coerce_event_description(payload: dict) -> str:
    description = str(payload.get("description") or "").strip()
    if not description:
        raise HTTPException(status_code=400, detail="Описание события не может быть пустым")
    return description


def resolve_event_session_id(runtime: AppRuntime, room_id: str, payload: dict) -> str | None:
    explicit = payload.get("sessionId", payload.get("session_id"))
    if explicit == "":
        return None
    if explicit is not None:
        session = runtime.repository.get_session(str(explicit))
        if not session:
            raise HTTPException(status_code=404, detail="Сессия не найдена")
        return str(explicit)

    current_session = runtime.repository.get_current_session(room_id)
    if current_session and current_session["status"] not in {"completed", "stopped"}:
        return current_session["id"]
    return None


def coerce_room_settings(payload: dict, current: dict | None = None) -> dict | None:
    if (
        "internetMode" not in payload
        and "internet_mode" not in payload
        and "toolsEnabled" not in payload
        and "tools_enabled" not in payload
        and "availableTools" not in payload
        and "available_tools" not in payload
    ):
        return None

    settings = dict(current or {})
    requested_mode = payload.get("internetMode", payload.get("internet_mode"))
    if requested_mode is not None:
        normalized = str(requested_mode).strip().lower()
        if normalized not in {"off", "auto", "on"}:
            raise HTTPException(status_code=400, detail="internetMode должен быть Off, Auto или On")
        settings["internet_mode"] = normalized
        return settings

    tools_enabled = bool(payload.get("toolsEnabled", payload.get("tools_enabled", settings.get("tools_enabled", False))))
    raw_tools = payload.get("availableTools", payload.get("available_tools", settings.get("available_tools") or [])) or []
    if raw_tools and not isinstance(raw_tools, list):
        raise HTTPException(status_code=400, detail="availableTools должен быть списком")
    available_tools = {str(tool) for tool in raw_tools}
    settings["internet_mode"] = "auto" if tools_enabled and "web_search" in available_tools else "off"
    return settings


async def broadcast_planned_events(runtime: AppRuntime, room_id: str, session_id: str | None = None):
    await runtime.manager.broadcast({
        "type": "planned_events_updated",
        "roomId": room_id,
        "plannedEvents": runtime.repository.list_planned_events(room_id, session_id),
    })


async def broadcast_custom_specialties(runtime: AppRuntime):
    await runtime.manager.broadcast({
        "type": "custom_specialties_updated",
        "customSpecialtyGroups": runtime.repository.list_custom_specialty_groups(),
    })


def specialty_label_from_hint(hint: str | None) -> str:
    text = re.sub(r"\s+", " ", str(hint or "")).strip()
    if not text:
        return ""
    patterns = [
        r"(?:взгляд[а-яё]*|голос[а-яё]*|эксперт[а-яё]*|экспертиз[а-яё]*)\s+([^,.!?]+?)(?:\s+для|\s+по|$)",
        r"не хватает\s+([^,.!?]+?)(?:\s+для|\s+по|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            candidate = match.group(1).strip(" :;—-")
            if candidate:
                return candidate[:80]
    return text[:80]


async def knowledge_status_payload(runtime: AppRuntime, room_id: str) -> dict:
    status_payload = runtime.graph_builder.get_status(room_id)
    current_graph_id = runtime.repository.get_room_graph_id(room_id)
    uploads_present = knowledge_uploads_exist(runtime, room_id)

    if status_payload["status"] == "ready" and status_payload["graphId"]:
        return {
            **status_payload,
            "hasKnowledge": True,
            "uploadsPresent": uploads_present,
        }
    if status_payload["status"] in {"building", "error"}:
        return {
            **status_payload,
            "hasKnowledge": bool(current_graph_id or status_payload.get("graphId")),
            "uploadsPresent": uploads_present,
        }
    if not current_graph_id:
        return {
            **status_payload,
            "hasKnowledge": False,
            "uploadsPresent": uploads_present,
        }

    graph = await asyncio.to_thread(get_knowledge_graph, current_graph_id)
    return {
        "roomId": room_id,
        "status": "ready",
        "progress": 100,
        "graphId": current_graph_id,
        "fileCount": status_payload.get("fileCount", 0),
        "chunkCount": status_payload.get("chunkCount", 0),
        "nodeCount": graph.get("node_count", len(graph.get("nodes", []))),
        "edgeCount": graph.get("edge_count", len(graph.get("edges", []))),
        "files": status_payload.get("files", []),
        "error": None,
        "updatedAt": status_payload.get("updatedAt"),
        "hasKnowledge": True,
        "uploadsPresent": uploads_present,
    }


async def replace_room_graph(runtime: AppRuntime, room_id: str, new_graph_id: str, previous_graph_id: str | None):
    runtime.repository.set_room_graph_id(room_id, new_graph_id)
    if previous_graph_id and previous_graph_id != new_graph_id:
        await asyncio.to_thread(delete_knowledge_graph, previous_graph_id)
    await runtime.manager.broadcast({
        "type": "knowledge_graph_updated",
        "roomId": room_id,
        "knowledge": await knowledge_status_payload(runtime, room_id),
    })


async def broadcast_knowledge_status(runtime: AppRuntime, room_id: str):
    await runtime.manager.broadcast({
        "type": "knowledge_graph_status",
        "roomId": room_id,
        "knowledge": await knowledge_status_payload(runtime, room_id),
    })


async def start_room_knowledge_rebuild(runtime: AppRuntime, room_id: str, previous_graph_id: str | None = None) -> dict:
    files = room_document_paths(runtime, room_id)
    previous_graph_id = previous_graph_id if previous_graph_id is not None else runtime.repository.get_room_graph_id(room_id)

    if not files:
        await runtime.graph_builder.cancel(room_id)
        runtime.repository.set_room_graph_id(room_id, None)
        if previous_graph_id:
            await asyncio.to_thread(delete_knowledge_graph, previous_graph_id)
        payload = await knowledge_status_payload(runtime, room_id)
        await runtime.manager.broadcast({
            "type": "knowledge_graph_deleted",
            "roomId": room_id,
            "knowledge": payload,
        })
        return payload

    try:
        await runtime.graph_builder.start_build_from_files(
            files,
            room_id,
            on_success=lambda graph_id: replace_room_graph(runtime, room_id, graph_id, previous_graph_id),
            on_error=lambda _exc: broadcast_knowledge_status(runtime, room_id),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await asyncio.sleep(0)
    payload = await knowledge_status_payload(runtime, room_id)
    await runtime.manager.broadcast({
        "type": "knowledge_graph_started",
        "roomId": room_id,
        "knowledge": payload,
    })
    return payload


async def broadcast_session_snapshot(runtime: AppRuntime, session_id: str):
    snapshot = runtime.repository.get_session_snapshot(session_id, make_current=False)
    if not snapshot:
        return
    await runtime.manager.broadcast(room_loaded_payload(runtime, snapshot, current_room_id=snapshot["room"]["id"]))


def resolve_fact_check_scope(session: dict, requested_scope: str | None = None, requested_round: Any = None) -> tuple[str, int | None]:
    scope = str(requested_scope or "").strip().lower()
    status = str(session.get("status") or "").strip().lower()
    if scope not in {"round", "session"}:
        scope = "session" if status in {"completed", "stopped"} else "round"
    if scope == "round":
        target_round = session.get("lastRoundNumber") if requested_round is None else requested_round
        try:
            target_round = int(target_round)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Для проверки текущего раунда нужен номер раунда") from exc
        if target_round < 1:
            raise HTTPException(status_code=400, detail="Для фактчекинга раунда пока нет данных")
        return "round", target_round
    return "session", None


def build_fact_check_status_message(run: dict) -> str:
    if run.get("status") == "completed":
        return run.get("summary") or "Фактчекинг завершён."
    if run.get("status") == "failed":
        return run.get("error") or "Фактчекинг завершился с ошибкой."
    if run.get("status") == "running":
        return "Идёт проверка фактов…"
    return "Фактчекинг поставлен в очередь."


def launch_report_task(runtime: AppRuntime, session_id: str, provider_name: str | None, model: str | None):
    if not runtime.background_tasks_enabled:
        return None
    existing = runtime.report_tasks.get(session_id)
    if existing and not existing.done():
        return existing

    async def runner():
        try:
            await runtime.manager.broadcast({"type": "report_generating", "session_id": session_id, "progress": 5})

            async def on_progress(progress: int):
                await runtime.manager.broadcast({"type": "report_generating", "session_id": session_id, "progress": progress})

            report = await runtime.report_generator.generate(
                session_id,
                provider_name=provider_name,
                model=model,
                progress_callback=on_progress,
            )
            await runtime.manager.broadcast({"type": "report_completed", "session_id": session_id, "report": report})
            await broadcast_session_snapshot(runtime, session_id)
        except Exception as exc:
            await runtime.manager.broadcast({"type": "report_error", "session_id": session_id, "message": str(exc)})
        finally:
            runtime.report_tasks.pop(session_id, None)

    task = asyncio.create_task(runner())
    runtime.report_tasks[session_id] = task
    return task


def launch_fact_check_task(runtime: AppRuntime, run_id: str):
    if not runtime.background_tasks_enabled:
        return None
    existing = runtime.fact_check_tasks.get(run_id)
    if existing and not existing.done():
        return existing

    async def runner():
        run = runtime.repository.get_fact_check_run(run_id)
        if not run:
            runtime.fact_check_tasks.pop(run_id, None)
            return
        session_id = run["sessionId"]
        try:
            await runtime.manager.broadcast({
                "type": "fact_check_updated",
                "session_id": session_id,
                "factCheck": {**run, "summary": build_fact_check_status_message(run)},
            })

            async def on_progress(progress: int):
                updated = runtime.repository.update_fact_check_run(run_id, status="running", progress=progress)
                await runtime.manager.broadcast({
                    "type": "fact_check_updated",
                    "session_id": session_id,
                    "factCheck": updated,
                })

            result = await runtime.fact_check_service.run(run_id, progress_callback=on_progress)
            await runtime.manager.broadcast({
                "type": "fact_check_completed",
                "session_id": session_id,
                "factCheck": result,
            })
            await broadcast_session_snapshot(runtime, session_id)
        except Exception as exc:
            failed = await runtime.fact_check_service.fail(run_id, exc)
            await runtime.manager.broadcast({
                "type": "fact_check_error",
                "session_id": session_id,
                "factCheck": failed,
                "message": str(exc),
            })
            await broadcast_session_snapshot(runtime, session_id)
        finally:
            runtime.fact_check_tasks.pop(run_id, None)

    task = asyncio.create_task(runner())
    runtime.fact_check_tasks[run_id] = task
    return task


def room_loaded_payload(runtime: AppRuntime, snapshot: dict | None, *, current_room_id: str | None = None) -> dict:
    if snapshot:
        effective_room_id = current_room_id if current_room_id is not None else snapshot["room"]["id"]
        return {
            "type": "room_loaded",
            "rooms": runtime.repository.list_rooms(),
            "currentRoomId": effective_room_id,
            **snapshot,
        }
    return {
        "type": "room_loaded",
        "rooms": runtime.repository.list_rooms(),
        "currentRoomId": current_room_id,
        "room": None,
        "participants": {"active": [], "benched": []},
        "inventory": runtime.repository.list_saved_profiles(),
        "teamPresets": runtime.repository.list_team_presets(),
        "customSpecialtyGroups": runtime.repository.list_custom_specialty_groups(),
        "session": None,
        "messages": [],
        "pinnedMessages": [],
        "observerReviews": [],
        "plannedEvents": [],
    }


async def build_init_payload(runtime: AppRuntime) -> dict:
    providers = await runtime.providers_payload()
    current_room_id = runtime.repository.get_current_room_id()
    room_snapshot = runtime.repository.get_room_snapshot(current_room_id) if current_room_id else None
    session = room_snapshot["session"] if room_snapshot else None
    effective_state = runtime.engine.state
    if effective_state == "idle" and session and session.get("status") not in {"completed", "stopped"}:
        effective_state = session["status"]
    return {
        "type": "init",
        "providers": providers,
        "rooms": runtime.repository.list_rooms(),
        "currentRoomId": current_room_id,
        "roomSnapshot": room_snapshot,
        "sessionState": {
            "roomId": current_room_id,
            "state": effective_state,
            "session": session,
        },
        "customSpecialtyGroups": runtime.repository.list_custom_specialty_groups(),
        "defaultAgents": room_snapshot["participants"]["active"] if room_snapshot else [],
    }
