from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from http_api import routes_lab
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
from tests.test_lab_api import _make_profile


@pytest.fixture
def reindex_env(monkeypatch):
    import tempfile
    from pathlib import Path

    tmpdir = Path(tempfile.mkdtemp())
    repository = Repository(str(tmpdir / "reindex.db"))
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

    inserted: list[list[str]] = []
    deleted: list[str] = []
    created: list[str] = []

    monkeypatch.setattr(routes_lab, "read_profile_documents", lambda graph_id: [
        {"content": "Тема: стратегия. Логос отстаивал B2B-фокус.", "create_time": 100},
        {"content": "тема: стратегия.   Логос отстаивал B2B-фокус.", "create_time": 110},
        {"content": "Тема: найм. Шутник предлагал нанимать на аутсорсе.", "create_time": 200},
        {"content": "короткая", "create_time": 300},
    ])
    monkeypatch.setattr(routes_lab, "_dedupe_documents", routes_lab._dedupe_documents)
    monkeypatch.setattr(routes_lab, "delete_profile_graph", lambda gid: deleted.append(gid))
    monkeypatch.setattr(routes_lab, "create_profile_graph", lambda pid: created.append(pid) or pid)
    monkeypatch.setattr(
        routes_lab,
        "insert_text",
        lambda gid, texts, root_dir=None: inserted.extend([texts]),
    )

    with TestClient(create_app(runtime_factory=runtime_factory)) as client:
        routes_lab._REINDEX_STATE.clear()
        yield {"client": client, "repo": repository, "inserted": inserted, "deleted": deleted}
    set_custom_providers_cleanup()


def set_custom_providers_cleanup():
    from providers import set_custom_providers

    set_custom_providers([])


def test_dedupe_keeps_latest_unique_normalized():
    docs = [
        {"content": "Тема: A. Длинный текст про стратегию продукта и рынок.", "create_time": 1},
        {"content": "тема: a. длинный текст про стратегию продукта и рынок.", "create_time": 2},
        {"content": "Тема: B. Совершенно другой разговор про найм команды.", "create_time": 3},
    ]
    result = routes_lab._dedupe_documents(docs)
    assert len(result) == 2
    # Свежие записи идут первыми (сортировка по create_time по убыванию).
    assert "найм" in result[0]


def test_reindex_rejects_without_memory(reindex_env):
    client, repo = reindex_env["client"], reindex_env["repo"]
    profile_id = _make_profile(repo)
    response = client.post(f"/api/lab/profiles/{profile_id}/memory/reindex")
    assert response.status_code == 400


def test_reindex_full_flow_dedupes_and_recreates(reindex_env):
    import time

    client, repo = reindex_env["client"], reindex_env["repo"]
    profile_id = _make_profile(repo)
    repo.set_profile_memory_graph_id(profile_id, profile_id)

    started = client.post(f"/api/lab/profiles/{profile_id}/memory/reindex")
    assert started.status_code == 200
    payload = started.json()
    assert payload["started"] is True
    assert payload["total"] == 2  # дубль и коротышка отброшены

    deadline = time.time() + 5
    status = {}
    while time.time() < deadline:
        status = client.get(f"/api/lab/profiles/{profile_id}/memory/reindex-status").json()
        if status.get("status") in ("done", "error"):
            break
        time.sleep(0.05)

    assert status["status"] == "done"
    assert status["processed"] == 2
    assert reindex_env["deleted"] == [profile_id]
    assert all(len(batch) <= 10 for batch in reindex_env["inserted"])


def test_reindex_status_idle_for_unknown(reindex_env):
    response = reindex_env["client"].get("/api/lab/profiles/char_x/memory/reindex-status")
    assert response.json() == {"status": "idle"}
