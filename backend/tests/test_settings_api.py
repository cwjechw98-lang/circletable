from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from http_api import routes_settings
from knowledge.lightrag_adapter import get_memory_llm_config, set_memory_llm_config
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
def settings_env(monkeypatch):
    import tempfile
    from pathlib import Path

    tmpdir = Path(tempfile.mkdtemp())
    repository = Repository(str(tmpdir / "settings.db"))
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

    set_memory_llm_config(base_url="", model="", api_key="")
    monkeypatch.setattr(routes_settings, "_apply_settings_overrides", routes_settings._apply_settings_overrides)

    with TestClient(create_app(runtime_factory=runtime_factory)) as client:
        yield {"client": client, "repo": repository}
    set_memory_llm_config(base_url="", model="", api_key="")


def test_get_settings_masks_secret(settings_env):
    client = settings_env["client"]
    data = client.get("/api/settings").json()["settings"]
    assert "memory_llm_base_url" in data
    assert data["memory_llm_api_key"] == ""


def test_put_and_persist_settings_with_override(settings_env):
    client, repo = settings_env["client"], settings_env["repo"]
    response = client.put("/api/settings", json={"settings": {
        "memory_llm_base_url": "https://openrouter.ai/api/v1",
        "memory_llm_model": "deepseek/deepseek-chat-v4",
        "memory_llm_api_key": "sk-or-test-7777",
        "reaction_chance": "0.4",
        "cross_dialog_enabled": "1",
    }})
    assert response.status_code == 200

    assert repo.get_setting("memory_llm_base_url") == "https://openrouter.ai/api/v1"
    config = get_memory_llm_config()
    assert config["base_url"] == "https://openrouter.ai/api/v1"
    assert config["model"] == "deepseek/deepseek-chat-v4"
    assert config["api_key"] == "sk-or-test-7777"

    # Ключ наружу отдаётся маской; повторный PUT с маской не затирает секрет.
    masked = client.get("/api/settings").json()["settings"]["memory_llm_api_key"]
    assert masked.endswith("7777") and "sk-or" not in masked
    client.put("/api/settings", json={"settings": {"memory_llm_api_key": masked}})
    assert repo.get_setting("memory_llm_api_key") == "sk-or-test-7777"


def test_unknown_setting_rejected(settings_env):
    response = settings_env["client"].put("/api/settings", json={"settings": {"hacker_key": "x"}})
    assert response.status_code == 400
