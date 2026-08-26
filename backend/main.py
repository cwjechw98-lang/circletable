from __future__ import annotations

import inspect
import json
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app_runtime import RuntimeFactory, build_default_runtime, shutdown_runtime
from http_api.deps import get_ws_runtime
from http_api.helpers import build_init_payload
from http_api.routes_casting import router as casting_router
from http_api.routes_characters import router as characters_router
from http_api.routes_lab import router as lab_router
from http_api.routes_rooms import router as rooms_router
from http_api.routes_sessions import router as sessions_router
from http_api.routes_system import router as system_router

load_dotenv()


def create_app(*, runtime_factory: RuntimeFactory | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        factory = runtime_factory or build_default_runtime
        built = factory()
        runtime = await built if inspect.isawaitable(built) else built
        _app.state.runtime = runtime
        try:
            yield
        finally:
            await shutdown_runtime(runtime)

    app_instance = FastAPI(title="AI Round Table", lifespan=lifespan)
    app_instance.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for router in (
        system_router,
        casting_router,
        rooms_router,
        characters_router,
        sessions_router,
        lab_router,
    ):
        app_instance.include_router(router)

    @app_instance.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        runtime = get_ws_runtime(ws)
        await runtime.manager.connect(ws)
        await ws.send_text(json.dumps(await build_init_payload(runtime), ensure_ascii=False))
        try:
            while True:
                raw = await ws.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                action = msg.get("type")
                if action == "get_providers":
                    await ws.send_text(
                        json.dumps(
                            {"type": "providers", "providers": await runtime.providers_payload()},
                            ensure_ascii=False,
                        )
                    )
                elif action == "load_room":
                    await runtime.engine.load_room(msg.get("roomId"))
                elif action == "load_session":
                    await runtime.engine.load_session(msg.get("sessionId"))
                elif action == "continue_session":
                    await runtime.engine.continue_session(msg.get("sessionId"))
                elif action == "start_session":
                    await runtime.engine.start_session(
                        topic=msg.get("topic"),
                        room_id=msg.get("roomId"),
                        observer_mode=msg.get("observerMode"),
                    )
                elif action == "pause_session":
                    await runtime.engine.pause_session()
                elif action == "resume_session":
                    await runtime.engine.resume_session(msg.get("roomId"))
                elif action == "stop_session":
                    await runtime.engine.stop_session()
                elif action == "request_wrap":
                    await runtime.engine.request_wrap()
                elif action == "request_final_round":
                    await runtime.engine.request_final_round()
                elif action == "submit_user_question":
                    await runtime.engine.submit_user_question(msg.get("content", ""))
                elif action == "add_participant_from_inventory":
                    await runtime.engine.add_participant_from_inventory(
                        msg.get("roomId") or runtime.repository.get_current_room_id(),
                        msg.get("profileId"),
                    )
                elif action == "create_and_add_participant":
                    await runtime.engine.create_and_add_participant(
                        msg.get("roomId") or runtime.repository.get_current_room_id(),
                        msg.get("participant") or {},
                        bool(msg.get("saveToInventory")),
                    )
                elif action == "bench_participant":
                    await runtime.engine.bench_participant(msg.get("participantId"))
                elif action == "restore_participant":
                    await runtime.engine.restore_participant(msg.get("participantId"))
                elif action == "observer_mode_changed":
                    await runtime.engine.set_observer_mode(
                        msg.get("roomId") or runtime.repository.get_current_room_id(),
                        msg.get("observerMode") or "suggest",
                    )
                elif action in ("start", "stop", "reset"):
                    if action == "start":
                        await runtime.engine.start(msg.get("topic"), msg.get("agents", []))
                    elif action == "stop":
                        await runtime.engine.stop()
                    else:
                        await runtime.engine.reset()
                elif action == "update_agents":
                    runtime.engine.update_agents(msg.get("agents", []))
        except WebSocketDisconnect:
            await runtime.manager.disconnect(ws)

    return app_instance


app = create_app()


__all__ = ["app", "create_app"]
