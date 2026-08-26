from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app_runtime import AppRuntime, ConnectionManager
from main import create_app
from storage import Repository, utc_now


class FakeDebateEngine:
    def __init__(self, repository: Repository):
        self.repository = repository
        self.running = False
        self.state = "idle"
        self.current_session_id: str | None = None

    async def shutdown(self):
        return None

    async def load_room(self, room_id: str | None = None):
        if room_id:
            self.repository.set_current_room(room_id)

    async def load_session(self, session_id: str | None = None):
        self.current_session_id = session_id

    async def continue_session(self, session_id: str | None = None):
        self.current_session_id = session_id

    async def start_session(self, topic: str | None = None, room_id: str | None = None, observer_mode: str | None = None):
        return None

    async def pause_session(self):
        return None

    async def resume_session(self, room_id: str | None = None):
        return None

    async def stop_session(self):
        return None

    async def request_wrap(self):
        return None

    async def request_final_round(self):
        return None

    async def submit_user_question(self, content: str):
        return None

    async def add_participant_from_inventory(self, room_id: str, profile_id: str):
        return None

    async def create_and_add_participant(self, room_id: str, data: dict, save_to_inventory: bool):
        return None

    async def bench_participant(self, participant_id: str):
        return None

    async def restore_participant(self, participant_id: str):
        return None

    async def set_observer_mode(self, room_id: str, mode: str):
        return None

    def update_agents(self, agents_cfg: list[dict]):
        return None


class FakeGraphBuilder:
    def __init__(self):
        self.statuses: dict[str, dict] = {}

    def get_status(self, room_id: str) -> dict:
        return self.statuses.get(
            room_id,
            {
                "roomId": room_id,
                "status": "idle",
                "progress": 0,
                "graphId": None,
                "fileCount": 0,
                "chunkCount": 0,
                "files": [],
                "error": None,
                "updatedAt": None,
            },
        )

    async def cancel(self, room_id: str):
        self.statuses[room_id] = self.get_status(room_id)

    async def start_build_from_files(self, files, room_id: str, on_success=None, on_error=None):
        self.statuses[room_id] = {
            "roomId": room_id,
            "status": "ready",
            "progress": 100,
            "graphId": f"graph_{room_id}",
            "fileCount": len(files),
            "chunkCount": len(files),
            "files": [Path(path).name for path in files],
            "error": None,
            "updatedAt": utc_now(),
        }
        if on_success:
            result = on_success(f"graph_{room_id}")
            if hasattr(result, "__await__"):
                await result


class FakeReportGenerator:
    def __init__(self, repository: Repository):
        self.repository = repository

    async def generate(self, session_id: str, provider_name: str = None, model: str = None, *, progress_callback=None):
        if progress_callback is not None:
            await progress_callback(100)
        snapshot = self.repository.get_session_snapshot(session_id, make_current=False)
        room_id = snapshot["room"]["id"] if snapshot else None
        return self.repository.save_report(
            session_id,
            room_id,
            "# Report",
            [{"id": "summary", "title": "1. Резюме", "markdown": "OK"}],
            provider_name or "fake",
            model or "fake-model",
        )


class FakeFactCheckService:
    def __init__(self, repository: Repository):
        self.repository = repository

    async def run(self, run_id: str, *, progress_callback=None):
        if progress_callback is not None:
            await progress_callback(100)
        self.repository.update_fact_check_run(
            run_id,
            status="completed",
            progress=100,
            summary="Фактчекинг завершён.",
            counts={},
            model_deltas=[],
            external_sources_used=False,
            completed_at=utc_now(),
        )
        return self.repository.get_fact_check_run(run_id, include_claims=True)

    async def fail(self, run_id: str, error):
        return self.repository.update_fact_check_run(
            run_id,
            status="failed",
            progress=100,
            error=str(error),
            completed_at=utc_now(),
        )


async def fake_providers_payload():
    return {"ollama": {"available": True, "models": ["test-model"]}}


@pytest.fixture
def api_env():
    tmpdir = Path(tempfile.mkdtemp())
    repository = Repository(str(tmpdir / "api.db"))
    runtime = AppRuntime(
        repository=repository,
        engine=FakeDebateEngine(repository),
        graph_builder=FakeGraphBuilder(),
        report_generator=FakeReportGenerator(repository),
        fact_check_service=FakeFactCheckService(repository),
        manager=ConnectionManager(),
        uploads_root=tmpdir / "uploads",
        background_tasks_enabled=False,
        providers_payload_loader=fake_providers_payload,
    )

    async def runtime_factory():
        return runtime

    with TestClient(create_app(runtime_factory=runtime_factory)) as client:
        yield {
            "client": client,
            "repo": repository,
            "runtime": runtime,
            "tmpdir": tmpdir,
        }


def _create_room(repository: Repository, name: str = "Комната API") -> str:
    room_id = repository.create_room(
        name=name,
        observer_mode="suggest",
        observer_provider="ollama",
        observer_model="test-model",
    )
    repository.set_current_room(room_id)
    return room_id


def _append_agent_message(repository: Repository, room_id: str, session_id: str, round_id: str, round_number: int, *, content: str):
    repository.append_message(
        room_id,
        session_id,
        {
            "id": f"msg_{round_number}_{abs(hash(content))}",
            "type": "agent_message",
            "author_type": "agent",
            "name": "Логос",
            "agent_name": "Логос",
            "participantId": "part_1",
            "profileId": "prof_1",
            "provider": "ollama",
            "model": "speaker-model",
            "round": round_number,
            "content": content,
        },
        round_id=round_id,
        round_number=round_number,
        message_type="agent_message",
        author_type="agent",
        participant_id="part_1",
    )


def test_providers_endpoints_return_expected_shape(api_env):
    client = api_env["client"]

    providers = client.get("/api/providers")
    assert providers.status_code == 200
    assert providers.json()["ollama"]["available"] is True

    refreshed = client.post("/api/providers/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["ok"] is True
    assert "providers" in refreshed.json()


def test_rooms_crud_and_internet_mode_roundtrip(api_env):
    client = api_env["client"]

    created = client.post("/api/rooms", json={"name": "Новая комната", "observerMode": "auto"})
    assert created.status_code == 200
    room_id = created.json()["room"]["id"]

    loaded = client.get(f"/api/rooms/{room_id}")
    assert loaded.status_code == 200
    assert loaded.json()["room"]["name"] == "Новая комната"

    patched = client.patch(f"/api/rooms/{room_id}", json={"name": "Переименована", "internetMode": "on"})
    assert patched.status_code == 200
    assert patched.json()["room"]["name"] == "Переименована"
    assert patched.json()["room"]["internetMode"] == "on"

    deleted = client.delete(f"/api/rooms/{room_id}")
    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True}


def test_room_events_crud_preserves_payload_contract(api_env):
    client = api_env["client"]
    repository = api_env["repo"]
    room_id = _create_room(repository, "События")
    session = repository.create_session(room_id, "Тема", "suggest")

    created = client.post(
        f"/api/rooms/{room_id}/events",
        json={"targetRound": 2, "description": "Подмешать внешнее событие"},
    )
    assert created.status_code == 200
    event_id = created.json()["event"]["id"]
    assert len(created.json()["events"]) == 1
    assert created.json()["event"]["sessionId"] == session["id"]

    patched = client.patch(
        f"/api/rooms/{room_id}/events/{event_id}",
        json={"description": "Обновлённое событие"},
    )
    assert patched.status_code == 200
    assert patched.json()["event"]["description"] == "Обновлённое событие"

    listed = client.get(f"/api/rooms/{room_id}/events")
    assert listed.status_code == 200
    assert len(listed.json()["events"]) == 1

    deleted = client.delete(f"/api/rooms/{room_id}/events/{event_id}")
    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True}


def test_session_open_returns_snapshot_contract(api_env):
    client = api_env["client"]
    repository = api_env["repo"]
    room_id = _create_room(repository, "Диалоги")
    session = repository.create_session(room_id, "Архивная тема", "suggest")

    loaded = client.get(f"/api/sessions/{session['id']}")
    assert loaded.status_code == 200
    assert loaded.json()["session"]["id"] == session["id"]

    opened = client.post(f"/api/sessions/{session['id']}/open")
    assert opened.status_code == 200
    payload = opened.json()
    assert payload["type"] == "room_loaded"
    assert payload["currentRoomId"] == room_id
    assert payload["session"]["id"] == session["id"]


def test_report_endpoint_keeps_conflict_and_queue_semantics(api_env):
    client = api_env["client"]
    repository = api_env["repo"]
    room_id = _create_room(repository, "Отчёты")
    running = repository.create_session(room_id, "Текущая тема", "suggest")

    conflict = client.post(f"/api/sessions/{running['id']}/report")
    assert conflict.status_code == 409

    repository.update_session(
        running["id"],
        {"status": "completed", "endedAt": utc_now()},
    )
    queued = client.post(f"/api/sessions/{running['id']}/report", json={"provider": "ollama", "model": "test-model"})
    assert queued.status_code == 200
    assert queued.json()["status"] == "queued"
    assert queued.json()["report"] is None


def test_fact_check_endpoint_handles_conflict_reuse_and_room_internet_mode(api_env):
    client = api_env["client"]
    repository = api_env["repo"]
    room_id = _create_room(repository, "Фактчекинг")
    session = repository.create_session(room_id, "Тема для проверки", "suggest")

    conflict = client.post(f"/api/sessions/{session['id']}/fact-check")
    assert conflict.status_code == 409

    repository.update_session(session["id"], {"status": "paused", "lastRoundNumber": 1})
    reusable = repository.create_fact_check_run(
        room_id=room_id,
        session_id=session["id"],
        scope="round",
        target_round=1,
        internet_mode="auto",
        provider="ollama",
        model="test-model",
    )
    reused = client.post(f"/api/sessions/{session['id']}/fact-check")
    assert reused.status_code == 200
    assert reused.json()["reused"] is True
    assert reused.json()["factCheck"]["id"] == reusable["id"]

    second_session = repository.create_session(room_id, "Новая пауза", "suggest")
    repository.update_session(second_session["id"], {"status": "paused", "lastRoundNumber": 2})
    repository.update_room_settings(room_id, settings={"internet_mode": "on"})
    created = client.post(f"/api/sessions/{second_session['id']}/fact-check", json={"scope": "round", "targetRound": 2})
    assert created.status_code == 200
    assert created.json()["reused"] is False
    assert created.json()["factCheck"]["internetMode"] == "on"
    assert created.json()["factCheck"]["targetRound"] == 2


def test_message_pin_preserves_response_contract(api_env):
    client = api_env["client"]
    repository = api_env["repo"]
    room_id = _create_room(repository, "Пины")
    session = repository.create_session(room_id, "Тема", "suggest")
    round_id = repository.create_round(room_id, session["id"], 1)
    _append_agent_message(repository, room_id, session["id"], round_id, 1, content="Факт для закрепления.")

    message = repository.list_session_messages(session["id"], limit=None)[-1]
    response = client.post(
        f"/api/messages/{message['id']}/pin",
        json={"roomId": room_id, "sessionId": session["id"]},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["messageId"] == message["id"]
    assert payload["pinned"] is True
    assert len(payload["pinnedMessages"]) == 1


def test_documents_and_knowledge_status_work_with_fake_graph_builder(api_env):
    client = api_env["client"]
    repository = api_env["repo"]
    runtime = api_env["runtime"]
    room_id = _create_room(repository, "Документы")
    upload_dir = runtime.uploads_root / room_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / "context.md").write_text("# Context", encoding="utf-8")

    listed = client.get(f"/api/rooms/{room_id}/documents")
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["files"][0]["name"] == "context.md"
    assert payload["knowledge"]["roomId"] == room_id
    assert payload["knowledge"]["hasKnowledge"] is False
