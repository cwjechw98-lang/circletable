from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from main import create_app
from storage import Repository, utc_now
from tests.test_main_api import (
    FakeDebateEngine,
    FakeFactCheckService,
    FakeGraphBuilder,
    FakeReportGenerator,
    ConnectionManager,
    AppRuntime,
    fake_providers_payload,
)


@pytest.fixture
def lab_env():
    import tempfile
    from pathlib import Path

    tmpdir = Path(tempfile.mkdtemp())
    repository = Repository(str(tmpdir / "lab.db"))
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


def _make_profile(repo: Repository, **overrides) -> str:
    data = {
        "name": "Логос",
        "role": "logician",
        "specialty": "strategy",
        "provider": "ollama",
        "model": "test-model",
        "emoji": "🧠",
        "mascot": "sage",
        "stats": {"insight": 60, "focus": 55, "depth": 50, "cooperation": 45, "showmanship": 40},
        "strengths": ["логика"],
        "weaknesses": [],
        "summary": "Сухой аналитик",
    }
    data.update(overrides)
    return repo.create_profile(data, is_saved=True, system_provided=False)


def _seed_history(repo: Repository, profile_id: str) -> None:
    room_id = repo.create_room(
        name="Лабораторная",
        observer_mode="suggest",
        observer_provider="ollama",
        observer_model="test-model",
    )
    participant_id = repo.add_participant_from_profile(room_id, profile_id)
    session_id = "sess_lab_1"
    round_id = "round_lab_1"
    for index in range(2):
        repo.append_message(
            room_id,
            session_id,
            {
                "id": f"msg_lab_{index}",
                "type": "agent_message",
                "author_type": "agent",
                "name": "Логос",
                "participantId": participant_id,
                "profileId": profile_id,
                "content": f"Тезис {index}",
            },
            round_id=round_id if index == 0 else f"round_lab_{index + 1}",
            round_number=index + 1,
            message_type="agent_message",
            author_type="agent",
            participant_id=participant_id,
        )
    repo.save_observer_review(room_id, session_id, round_id, 1, {
        "statsDelta": {profile_id: {"insight": 3, "focus": 1, "depth": 2, "cooperation": 0, "showmanship": 0}},
        "achievements": [{"profileId": profile_id, "title": "Аналитик раунда", "reason": "Разложил проблему по полочкам."}],
        "participantComments": {profile_id: "Логос усилил показатель «Инсайт»."},
        "roundSummary": "Раунд прошёл продуктивно.",
    })
    repo.save_observer_review(room_id, session_id, "round_lab_2", 2, {
        "statsDelta": {profile_id: {"insight": 1, "focus": 0, "depth": 0, "cooperation": 2, "showmanship": 0}},
        "achievements": [],
        "participantComments": {},
        "roundSummary": "Продолжение дискуссии.",
    })
    return room_id


def test_lab_profiles_lists_saved_characters(lab_env):
    client, repo = lab_env["client"], lab_env["repo"]
    profile_id = _make_profile(repo)
    response = client.get("/api/lab/profiles")
    assert response.status_code == 200
    dossiers = response.json()["dossiers"]
    match = next(item for item in dossiers if item["id"] == profile_id)
    assert match["name"] == "Логос"
    assert match["career"]["messagesCount"] == 0
    assert match["reviewMentions"] == 0


def test_lab_dossier_aggregates_evolution_and_achievements(lab_env):
    client, repo = lab_env["client"], lab_env["repo"]
    profile_id = _make_profile(repo)
    _seed_history(repo, profile_id)

    response = client.get(f"/api/lab/profiles/{profile_id}")
    assert response.status_code == 200
    dossier = response.json()

    assert dossier["career"]["messagesCount"] == 2
    assert dossier["career"]["sessionsCount"] == 1
    assert dossier["career"]["roundsSpoken"] == 2
    assert dossier["reviewMentions"] >= 2

    assert len(dossier["evolution"]) == 2
    first, second = dossier["evolution"]
    assert second["values"]["insight"] == first["values"]["insight"] + 1

    totals = dossier["statsTotals"]
    assert totals["insight"] == 4
    assert totals["cooperation"] == 2
    # Текущий стата 60 = старт + суммарные дельты.
    assert dossier["startValues"]["insight"] + totals["insight"] == 60

    titles = [item["title"] for item in dossier["achievements"]]
    assert titles == ["Аналитик раунда"]
    assert any("Инсайт" in item["text"] for item in dossier["notes"])


def test_lab_dossier_unknown_profile_returns_404(lab_env):
    client = lab_env["client"]
    response = client.get("/api/lab/profiles/char_missing")
    assert response.status_code == 404
