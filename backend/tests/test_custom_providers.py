from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from main import create_app
from providers import get_provider, set_custom_providers
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
def providers_env():
    import tempfile
    from pathlib import Path

    tmpdir = Path(tempfile.mkdtemp())
    repository = Repository(str(tmpdir / "providers.db"))
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
        set_custom_providers([])
        yield {"client": client, "repo": repository}


def test_presets_listed(providers_env):
    response = providers_env["client"].get("/api/custom-providers/presets")
    assert response.status_code == 200
    presets = response.json()["presets"]
    labels = {preset["id"] for preset in presets}
    assert {"deepseek", "openrouter", "groq", "gemini-openai"} & labels


def test_custom_provider_crud_and_resolution(providers_env):
    client, repo = providers_env["client"], providers_env["repo"]

    created = client.post("/api/custom-providers", json={
        "name": "Мой шлюз",
        "baseUrl": "https://gw.example.com/v1/",
        "apiKey": "sk-secret-9999",
    })
    assert created.status_code == 200
    provider = created.json()["customProvider"]
    assert provider["baseUrl"] == "https://gw.example.com/v1"
    # Ключ маскируется: видны только последние 4 символа.
    assert provider["keyHint"].endswith("9999")
    assert "sk-secret" not in provider["keyHint"]

    listed = client.get("/api/custom-providers").json()["customProviders"]
    assert [item["id"] for item in listed] == [provider["id"]]

    # get_provider резолвит динамический инстанс с полным ключом внутри.
    instance = get_provider(f"custom:{provider['id']}")
    assert instance.base_url == "https://gw.example.com/v1"
    assert instance.api_key == "sk-secret-9999"

    deleted = client.delete(f"/api/custom-providers/{provider['id']}")
    assert deleted.status_code == 200
    try:
        get_provider(f"custom:{provider['id']}")
        raise AssertionError("Ожидался ValueError после удаления")
    except ValueError:
        pass


def test_records_survive_restart_via_set_custom_providers(providers_env):
    repo = providers_env["repo"]
    repo.create_custom_provider("Локальный vLLM", "http://localhost:8000/v1", "")
    records = repo.list_custom_provider_records()
    set_custom_providers(records)
    instance = get_provider("custom:" + records[0]["id"])
    assert instance.is_available()
