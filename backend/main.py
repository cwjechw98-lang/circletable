from __future__ import annotations

import asyncio
import json
import os
import subprocess
from contextlib import asynccontextmanager
from itertools import count
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from casting import suggest_characters
from debate import DebateEngine
from defaults import build_default_profiles, pick_observer_provider
from providers import PROVIDERS
from storage import Repository

load_dotenv()


class ConnectionManager:
    def __init__(self):
        self._ws: list[WebSocket] = []
        self._lock = asyncio.Lock()
        self._event_ids = count(1)

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._ws.append(ws)

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            if ws in self._ws:
                self._ws.remove(ws)

    async def broadcast(self, data: dict):
        if "event_id" not in data:
            data = {**data, "event_id": next(self._event_ids)}
        payload = json.dumps(data, ensure_ascii=False)
        dead: list[WebSocket] = []
        for ws in list(self._ws):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)


manager = ConnectionManager()
repository: Repository | None = None
engine: DebateEngine | None = None


def _spawn_shutdown_helper():
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
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


async def _providers_payload() -> dict[str, dict[str, Any]]:
    result = {}
    for name, provider_cls in PROVIDERS.items():
        provider = provider_cls()
        available = provider.is_available()
        models = await provider.list_models() if available else []
        result[name] = {"available": available, "models": models}
    return result


def repo() -> Repository:
    if repository is None:
        raise RuntimeError("Repository is not initialized")
    return repository


def debate_engine() -> DebateEngine:
    if engine is None:
        raise RuntimeError("DebateEngine is not initialized")
    return engine


async def _init_payload() -> dict:
    providers = await _providers_payload()
    current_room_id = repo().get_current_room_id()
    room_snapshot = repo().get_room_snapshot(current_room_id) if current_room_id else None
    session = room_snapshot["session"] if room_snapshot else None
    effective_state = debate_engine().state
    if effective_state == "idle" and session and session.get("status") not in {"completed", "stopped"}:
        effective_state = session["status"]
    return {
        "type": "init",
        "providers": providers,
        "rooms": repo().list_rooms(),
        "currentRoomId": current_room_id,
        "roomSnapshot": room_snapshot,
        "sessionState": {
            "roomId": current_room_id,
            "state": effective_state,
            "session": session,
        },
        "defaultAgents": room_snapshot["participants"]["active"] if room_snapshot else [],
    }


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global repository, engine

    db_path = os.path.join(os.path.dirname(__file__), "data", "circletable.db")
    repository = Repository(db_path)
    providers = await _providers_payload()
    default_profiles = build_default_profiles(providers)
    observer_provider, observer_model = pick_observer_provider(providers)
    repository.bootstrap(default_profiles, observer_provider, observer_model)
    repository.normalize_incomplete_sessions()
    engine = DebateEngine(broadcast=manager.broadcast, repository=repository)
    yield
    await engine.shutdown()
    repository.close()


app = FastAPI(title="AI Round Table", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/providers")
async def list_providers():
    return await _providers_payload()


@app.post("/api/providers/refresh")
async def refresh_providers():
    providers = await _providers_payload()
    await manager.broadcast({"type": "providers", "providers": providers})
    return {"ok": True, "providers": providers}


@app.post("/api/system/shutdown")
async def shutdown_app():
    current_room_id = repo().get_current_room_id()
    current_session = repo().get_current_session(current_room_id) if current_room_id else None

    if current_room_id and current_session and current_session["status"] not in {"completed", "stopped"}:
        repo().update_session(current_session["id"], {"status": "paused"})
        repo().add_room_event(
            current_room_id,
            current_session["id"],
            "app_shutdown_requested",
            {"source": "ui"},
        )

    repo().normalize_incomplete_sessions()

    await manager.broadcast({
        "type": "app_shutdown_requested",
        "message": "Сеанс сохраняется. Окна запуска сейчас закроются.",
    })

    _spawn_shutdown_helper()
    return {"ok": True}


@app.post("/api/casting/suggest")
async def suggest_casting(payload: dict):
    topic = (payload.get("topic") or "").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Сначала введите тему или вопрос")

    providers = await _providers_payload()
    return await suggest_characters(
        topic=topic,
        count=payload.get("count"),
        providers_payload=providers,
        provider_name=payload.get("provider"),
        model=payload.get("model"),
    )


@app.get("/api/rooms")
async def list_rooms():
    return {
        "rooms": repo().list_rooms(),
        "currentRoomId": repo().get_current_room_id(),
    }


@app.post("/api/rooms")
async def create_room(payload: dict):
    providers = await _providers_payload()
    observer_provider, observer_model = pick_observer_provider(providers)
    room_id = repo().create_room(
        name=(payload.get("name") or "Новая комната").strip(),
        observer_mode=payload.get("observerMode") or "suggest",
        observer_provider=payload.get("observerProvider") or observer_provider,
        observer_model=payload.get("observerModel") or observer_model,
    )
    repo().set_current_room(room_id)
    snapshot = repo().get_room_snapshot(room_id)
    await manager.broadcast({
        "type": "room_loaded",
        "rooms": repo().list_rooms(),
        "currentRoomId": room_id,
        **snapshot,
    })
    return snapshot


@app.get("/api/rooms/{room_id}")
async def get_room(room_id: str):
    snapshot = repo().get_room_snapshot(room_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Комната не найдена")
    return snapshot


@app.patch("/api/rooms/{room_id}")
async def patch_room(room_id: str, payload: dict):
    snapshot = repo().get_room_snapshot(room_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Комната не найдена")
    repo().update_room_settings(
        room_id,
        name=payload.get("name"),
        observer_mode=payload.get("observerMode"),
        observer_provider=payload.get("observerProvider"),
        observer_model=payload.get("observerModel"),
    )
    updated = repo().get_room_snapshot(room_id)
    await manager.broadcast({
        "type": "room_loaded",
        "rooms": repo().list_rooms(),
        "currentRoomId": room_id,
        **updated,
    })
    return updated


@app.delete("/api/rooms/{room_id}")
async def delete_room(room_id: str):
    snapshot = repo().get_room_snapshot(room_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Комната не найдена")
    repo().delete_room(room_id)
    current_room_id = repo().get_current_room_id()
    current_snapshot = repo().get_room_snapshot(current_room_id) if current_room_id else None
    await manager.broadcast({
        "type": "room_loaded",
        "rooms": repo().list_rooms(),
        "currentRoomId": current_room_id,
        "room": current_snapshot["room"] if current_snapshot else None,
        "participants": current_snapshot["participants"] if current_snapshot else {"active": [], "benched": []},
        "inventory": current_snapshot["inventory"] if current_snapshot else repo().list_saved_profiles(),
        "session": current_snapshot["session"] if current_snapshot else None,
        "messages": current_snapshot["messages"] if current_snapshot else [],
        "observerReviews": current_snapshot["observerReviews"] if current_snapshot else [],
    })
    return {"ok": True}


@app.get("/api/characters")
async def list_characters():
    return {"characters": repo().list_saved_profiles()}


@app.post("/api/characters")
async def create_character(payload: dict):
    profile_id = repo().create_profile(payload, is_saved=True, system_provided=False)
    profile = repo().get_profile(profile_id)
    await manager.broadcast({
        "type": "participant_stats_updated",
        "inventory": repo().list_saved_profiles(),
    })
    return profile


@app.patch("/api/characters/{character_id}")
async def update_character(character_id: str, payload: dict):
    if not repo().get_profile(character_id):
        raise HTTPException(status_code=404, detail="Персонаж не найден")
    repo().update_profile(character_id, payload)
    profile = repo().get_profile(character_id)
    await manager.broadcast({
        "type": "participant_stats_updated",
        "inventory": repo().list_saved_profiles(),
    })
    return profile


@app.delete("/api/characters/{character_id}")
async def delete_character(character_id: str):
    if not repo().get_profile(character_id):
        raise HTTPException(status_code=404, detail="Персонаж не найден")
    repo().delete_profile(character_id)
    await manager.broadcast({
        "type": "participant_stats_updated",
        "inventory": repo().list_saved_profiles(),
    })
    return {"ok": True}


@app.get("/api/rooms/{room_id}/inventory")
async def get_room_inventory(room_id: str):
    snapshot = repo().get_room_snapshot(room_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Комната не найдена")
    return {
        "participants": snapshot["participants"],
        "inventory": snapshot["inventory"],
    }


@app.get("/api/rooms/{room_id}/sessions")
async def list_room_sessions(room_id: str, query: str = ""):
    if not repo().room_exists(room_id):
        raise HTTPException(status_code=404, detail="Комната не найдена")
    return {"sessions": repo().list_room_sessions(room_id, query=query)}


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    snapshot = repo().get_session_snapshot(session_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    return snapshot


@app.post("/api/sessions/{session_id}/open")
async def open_session(session_id: str):
    snapshot = repo().set_current_session(session_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    payload = {
        "rooms": repo().list_rooms(),
        "currentRoomId": snapshot["room"]["id"],
        **snapshot,
    }
    await manager.broadcast({"type": "room_loaded", **payload})
    return payload


@app.post("/api/sessions/{session_id}/continue")
async def continue_session(session_id: str):
    if debate_engine().running:
        current_session_id = debate_engine().current_session_id
        if current_session_id and current_session_id != session_id:
            raise HTTPException(status_code=409, detail="Сначала остановите текущую сессию")
    await debate_engine().continue_session(session_id)
    snapshot = repo().get_session_snapshot(session_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    return {
        "rooms": repo().list_rooms(),
        "currentRoomId": snapshot["room"]["id"],
        **snapshot,
    }


@app.patch("/api/sessions/{session_id}")
async def patch_session(session_id: str, payload: dict):
    if not repo().get_session(session_id):
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    repo().rename_session(session_id, payload.get("title") or "")
    snapshot = repo().get_session_snapshot(session_id)
    return {
        "rooms": repo().list_rooms(),
        "currentRoomId": snapshot["room"]["id"],
        **snapshot,
    }


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    if debate_engine().current_session_id == session_id and debate_engine().running:
        raise HTTPException(status_code=409, detail="Сначала остановите текущую сессию")
    session = repo().get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    snapshot = repo().get_session_snapshot(session_id)
    room_id = snapshot["room"]["id"]
    repo().delete_session(session_id)
    current_room_id = repo().get_current_room_id()
    current_snapshot = repo().get_room_snapshot(current_room_id) if current_room_id else None
    await manager.broadcast({
        "type": "room_loaded",
        "rooms": repo().list_rooms(),
        "currentRoomId": current_room_id,
        "room": current_snapshot["room"] if current_snapshot else None,
        "participants": current_snapshot["participants"] if current_snapshot else {"active": [], "benched": []},
        "inventory": current_snapshot["inventory"] if current_snapshot else repo().list_saved_profiles(),
        "session": current_snapshot["session"] if current_snapshot else None,
        "messages": current_snapshot["messages"] if current_snapshot else [],
        "observerReviews": current_snapshot["observerReviews"] if current_snapshot else [],
    })
    return {"ok": True, "roomId": room_id}


@app.get("/api/sessions/{session_id}/export.md")
async def export_session(session_id: str):
    content = repo().export_session_markdown(session_id)
    if content is None:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    headers = {
        "Content-Disposition": f'attachment; filename="circletable-{session_id}.md"',
    }
    return PlainTextResponse(content, media_type="text/markdown; charset=utf-8", headers=headers)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await manager.connect(ws)
    await ws.send_text(json.dumps(await _init_payload(), ensure_ascii=False))

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            action = msg.get("type")

            if action == "get_providers":
                await ws.send_text(json.dumps({
                    "type": "providers",
                    "providers": await _providers_payload(),
                }, ensure_ascii=False))
            elif action == "load_room":
                await debate_engine().load_room(msg.get("roomId"))
            elif action == "load_session":
                await debate_engine().load_session(msg.get("sessionId"))
            elif action == "continue_session":
                await debate_engine().continue_session(msg.get("sessionId"))
            elif action == "start_session":
                await debate_engine().start_session(
                    topic=msg.get("topic"),
                    room_id=msg.get("roomId"),
                    observer_mode=msg.get("observerMode"),
                )
            elif action == "pause_session":
                await debate_engine().pause_session()
            elif action == "resume_session":
                await debate_engine().resume_session(msg.get("roomId"))
            elif action == "stop_session":
                await debate_engine().stop_session()
            elif action == "request_wrap":
                await debate_engine().request_wrap()
            elif action == "request_final_round":
                await debate_engine().request_final_round()
            elif action == "submit_user_question":
                await debate_engine().submit_user_question(msg.get("content", ""))
            elif action == "add_participant_from_inventory":
                await debate_engine().add_participant_from_inventory(msg.get("roomId") or repo().get_current_room_id(), msg.get("profileId"))
            elif action == "create_and_add_participant":
                await debate_engine().create_and_add_participant(
                    msg.get("roomId") or repo().get_current_room_id(),
                    msg.get("participant") or {},
                    bool(msg.get("saveToInventory")),
                )
            elif action == "bench_participant":
                await debate_engine().bench_participant(msg.get("participantId"))
            elif action == "restore_participant":
                await debate_engine().restore_participant(msg.get("participantId"))
            elif action == "observer_mode_changed":
                await debate_engine().set_observer_mode(
                    msg.get("roomId") or repo().get_current_room_id(),
                    msg.get("observerMode") or "suggest",
                )

            # legacy compatibility
            elif action == "start":
                await debate_engine().start(msg.get("topic"), msg.get("agents", []))
            elif action == "stop":
                await debate_engine().stop()
            elif action == "reset":
                await debate_engine().reset()
            elif action == "update_agents":
                debate_engine().update_agents(msg.get("agents", []))

    except WebSocketDisconnect:
        await manager.disconnect(ws)
