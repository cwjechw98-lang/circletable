from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from itertools import count
from pathlib import Path
from typing import Any, Awaitable, Callable

from casting import suggest_characters
from debate import DebateEngine
from defaults import build_default_profiles, pick_observer_provider
from factcheck import FactCheckService
from knowledge.graph_builder import GraphBuilder
from meta_memory import format_insight_recall, select_relevant_session_insights
from providers import PROVIDERS
from reports import ReportGenerator
from storage import Repository


class ConnectionManager:
    def __init__(self):
        self._ws: list[Any] = []
        self._lock = asyncio.Lock()
        self._event_ids = count(1)

    async def connect(self, ws):
        await ws.accept()
        async with self._lock:
            self._ws.append(ws)

    async def disconnect(self, ws):
        async with self._lock:
            if ws in self._ws:
                self._ws.remove(ws)

    async def broadcast(self, data: dict):
        if "event_id" not in data:
            data = {**data, "event_id": next(self._event_ids)}
        payload = json.dumps(data, ensure_ascii=False)
        dead: list[Any] = []
        for ws in list(self._ws):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)


ProviderPayloadLoader = Callable[[], Awaitable[dict[str, dict[str, Any]]]]
RuntimeFactory = Callable[[], Awaitable["AppRuntime"] | "AppRuntime"]


async def default_providers_payload() -> dict[str, dict[str, Any]]:
    result = {}
    for name, provider_cls in PROVIDERS.items():
        provider = provider_cls()
        available = provider.is_available()
        models = await provider.list_models() if available else []
        result[name] = {"available": available, "models": models}
    return result


@dataclass
class AppRuntime:
    repository: Repository
    engine: DebateEngine
    graph_builder: GraphBuilder
    report_generator: ReportGenerator
    fact_check_service: FactCheckService
    manager: ConnectionManager = field(default_factory=ConnectionManager)
    report_tasks: dict[str, asyncio.Task] = field(default_factory=dict)
    fact_check_tasks: dict[str, asyncio.Task] = field(default_factory=dict)
    uploads_root: Path = field(default_factory=lambda: Path(__file__).resolve().parent / "data" / "uploads")
    background_tasks_enabled: bool = True
    providers_payload_loader: ProviderPayloadLoader = default_providers_payload
    suggest_characters_fn: Callable[..., Awaitable[dict[str, Any]]] = suggest_characters
    select_relevant_session_insights_fn: Callable[..., list[dict[str, Any]]] = select_relevant_session_insights
    format_insight_recall_fn: Callable[..., str] = format_insight_recall

    async def providers_payload(self) -> dict[str, dict[str, Any]]:
        return await self.providers_payload_loader()


async def build_default_runtime() -> AppRuntime:
    db_path = os.getenv("CIRCLETABLE_DB_PATH") or os.path.join(os.path.dirname(__file__), "data", "circletable.db")
    repository = Repository(db_path)
    providers = await default_providers_payload()
    default_profiles = build_default_profiles(providers)
    observer_provider, observer_model = pick_observer_provider(providers)
    repository.bootstrap(default_profiles, observer_provider, observer_model)
    repository.normalize_incomplete_sessions()

    manager = ConnectionManager()
    engine = DebateEngine(broadcast=manager.broadcast, repository=repository)
    graph_builder = GraphBuilder(chunk_size=500, chunk_overlap=50)
    report_generator = ReportGenerator(repository)
    fact_check_service = FactCheckService(repository)
    return AppRuntime(
        repository=repository,
        engine=engine,
        graph_builder=graph_builder,
        report_generator=report_generator,
        fact_check_service=fact_check_service,
        manager=manager,
    )


async def shutdown_runtime(runtime: AppRuntime):
    await runtime.engine.shutdown()
    for task in list(runtime.report_tasks.values()):
        task.cancel()
    for task in list(runtime.fact_check_tasks.values()):
        task.cancel()
    pending = list(runtime.report_tasks.values()) + list(runtime.fact_check_tasks.values())
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    runtime.repository.close()
