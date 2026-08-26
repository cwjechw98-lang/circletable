from __future__ import annotations

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
def memory_env(monkeypatch):
    import tempfile
    from pathlib import Path

    tmpdir = Path(tempfile.mkdtemp())
    repository = Repository(str(tmpdir / "memory.db"))
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

    deleted: list[str] = []

    def fake_get_knowledge_graph(graph_id, **kwargs):
        return {
            "graph_id": graph_id,
            "nodes": [
                {"uuid": "1", "name": "SEO-стратегия", "labels": ["Concept"], "summary": "Основной фокус прошлой сессии"},
                {"uuid": "2", "name": "Логос", "labels": ["Person"], "summary": "Коллега по столу"},
            ],
            "edges": [
                {
                    "name": "обсуждал",
                    "fact": "Логос обсуждал SEO-стратегию в раунде 3",
                    "source_node_name": "Логос",
                    "target_node_name": "SEO-стратегия",
                },
                {"name": "", "fact": "", "source_node_name": "x", "target_node_name": "y"},
            ],
        }

    def fake_delete_profile_graph(graph_id):
        deleted.append(graph_id)

    monkeypatch.setattr(routes_lab, "get_profile_knowledge_graph", fake_get_knowledge_graph)
    monkeypatch.setattr(routes_lab, "delete_profile_graph", fake_delete_profile_graph)

    with TestClient(create_app(runtime_factory=runtime_factory)) as client:
        yield {
            "client": client,
            "repo": repository,
            "deleted": deleted,
        }
    set_custom_providers_cleanup()


def set_custom_providers_cleanup():
    from providers import set_custom_providers

    set_custom_providers([])


def test_memory_unknown_profile_404(memory_env):
    response = memory_env["client"].get("/api/lab/profiles/char_ghost/memory")
    assert response.status_code == 404


def test_memory_view_empty_when_no_graph(memory_env):
    client, repo = memory_env["client"], memory_env["repo"]
    profile_id = _make_profile(repo)
    data = client.get(f"/api/lab/profiles/{profile_id}/memory").json()
    assert data["hasMemory"] is False
    assert data["entities"] == []


def test_memory_view_returns_entities_and_facts(memory_env):
    client, repo = memory_env["client"], memory_env["repo"]
    profile_id = _make_profile(repo)
    repo.set_profile_memory_graph_id(profile_id, profile_id)

    data = client.get(f"/api/lab/profiles/{profile_id}/memory").json()
    assert data["hasMemory"] is True
    assert data["entityCount"] == 2
    assert {entity["name"] for entity in data["entities"]} == {"Логос", "SEO-стратегия"}
    assert data["factCount"] == 1
    assert "SEO-стратегию" in data["facts"][0]["fact"]


def test_forget_all_clears_graph_and_pointer(memory_env):
    client, repo, deleted = memory_env["client"], memory_env["repo"], memory_env["deleted"]
    profile_id = _make_profile(repo)
    repo.set_profile_memory_graph_id(profile_id, profile_id)

    response = client.delete(f"/api/lab/profiles/{profile_id}/memory")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True and payload["cleared"] is True and payload["clearedGraph"] is True
    assert deleted == [profile_id]
    assert repo.get_profile_memory_graph_id(profile_id) is None

    # Повторный сброс без графа — валидная no-op операция.
    again = client.delete(f"/api/lab/profiles/{profile_id}/memory").json()
    assert again == {"ok": True, "cleared": False, "clearedGraph": False}
