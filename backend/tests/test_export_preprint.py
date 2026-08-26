from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from http_api import routes_export
from main import create_app
from storage import Repository
from tests.test_main_api import (
    AppRuntime,
    ConnectionManager,
    FakeDebateEngine,
    FakeFactCheckService,
    FakeGraphBuilder,
    FakeReportGenerator,
    fake_providers_payload,
)


@pytest.fixture
def export_env(monkeypatch):
    tmpdir = Path(tempfile.mkdtemp())
    repository = Repository(str(tmpdir / "export.db"))
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
        yield {"client": client, "repo": repository}


def _seed_session(repo) -> str:
    room_id = repo.create_room(
        "Комната экспорта",
        observer_mode="auto",
        observer_provider="ollama",
        observer_model="gemma4:31b-cloud",
    )
    session_id = repo.create_session(room_id, "Тема: стратегия удержания B2B клиентов", observer_mode="auto")["id"]
    repo.append_message(
        room_id,
        session_id,
        {
            "type": "agent_message",
            "agent_name": "Логос",
            "name": "Логос",
            "role": "logician",
            "content": "Предлагаю сфокусироваться на корпоративном сегменте.",
            "author_type": "agent",
            "round": 1,
        },
        message_type="agent_message",
        author_type="agent",
    )
    repo.update_session(session_id, {"chronicle": "Раунд 1: сошлись на B2B-фокусе."})
    return session_id


def test_export_messages_format(export_env):
    client, repo = export_env["client"], export_env["repo"]
    session_id = _seed_session(repo)

    response = client.get(f"/api/export/session/{session_id}?format=messages")
    assert response.status_code == 200
    line = response.text.strip().splitlines()[0]
    payload = json.loads(line)
    assert payload["topic"].startswith("Тема:")
    assert payload["messages"][0]["name"] == "Логос"
    assert "attachment" in response.headers["content-disposition"]


def test_export_sharegpt_format(export_env):
    client, repo = export_env["client"], export_env["repo"]
    session_id = _seed_session(repo)

    data = client.get(f"/api/export/session/{session_id}?format=sharegpt").json()
    assert isinstance(data, dict)
    conversations = data.get("conversations", [])
    assert conversations[0]["from"] == "system"
    assert any(item["from"] == "gpt" and "Логос" in item["value"] for item in conversations)


def test_export_unknown_session_404(export_env):
    response = export_env["client"].get("/api/export/session/char_ghost?format=messages")
    assert response.status_code == 404


def test_preprint_template_fallback_without_llm(export_env, monkeypatch):
    client, repo = export_env["client"], export_env["repo"]
    session_id = _seed_session(repo)

    async def fail_llm(messages, temperature=0.3):
        raise RuntimeError("LLM недоступна")

    monkeypatch.setattr(routes_export, "memory_llm_chat", fail_llm)
    result = client.post(f"/api/preprint/{session_id}").json()
    assert result["fallback"] is True
    markdown = result["markdown"]
    for section in ("Постановка задачи", "Метод и ход обсуждения", "Результаты", "Открытые вопросы"):
        assert section in markdown
    # Препринт сохранён как отчёт сессии.
    assert repo.get_latest_report(session_id) is not None


def test_token_usage_recorded_and_summarized(export_env):
    from token_accounting import record_usage

    repo = export_env["repo"]
    session_id = _seed_session(repo)
    record_usage(
        repo,
        session_id=session_id,
        round_number=1,
        kind="agent_message",
        provider="openrouter",
        model="stealth/ox-alpha",
        prompt_text="Тема обсуждения " * 10,
        completion_text="Короткий ответ.",
    )
    summary = repo.token_usage_summary(session_id)
    assert summary["total"]["calls"] == 1
    assert summary["byKind"]["agent_message"]["calls"] == 1
    assert summary["byModel"]["stealth/ox-alpha"]["promptTokens"] > 0

    api_summary = export_env["client"].get(f"/api/stats/tokens/{session_id}").json()
    assert api_summary["total"]["completionTokens"] > 0
