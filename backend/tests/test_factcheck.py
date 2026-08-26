from __future__ import annotations

import asyncio
import tempfile

import pytest

from factcheck import FactCheckService
from storage import Repository


@pytest.fixture
def repo():
    tmpdir = tempfile.mkdtemp()
    repository = Repository(f"{tmpdir}/factcheck.db")
    room_id = repository.create_room(
        name="Фактчекинг",
        observer_mode="suggest",
        observer_provider="ollama",
        observer_model="observer-model",
    )
    yield repository, room_id
    repository.close()


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


def test_factcheck_round_scope_checks_only_target_round(repo, monkeypatch):
    repository, room_id = repo
    session = repository.create_session(room_id, "Business metrics", "suggest")
    repository.update_session(session["id"], {"status": "paused", "last_round_number": 2})
    round1 = repository.create_round(room_id, session["id"], 1)
    round2 = repository.create_round(room_id, session["id"], 2)

    _append_agent_message(repository, room_id, session["id"], round1, 1, content="По данным отчёта, выручка выросла на 10%.")
    _append_agent_message(repository, room_id, session["id"], round2, 2, content="По данным отчёта, выручка выросла на 20%.")

    monkeypatch.setattr("factcheck.query_graph", lambda *_args, **_kwargs: "Документы комнаты: выручка выросла на 20%.")

    async def fake_external(*_args, **_kwargs):
        return [], {"source": "none", "internetMode": "off", "scienceFirst": False}

    monkeypatch.setattr("factcheck.search_external_snippets", fake_external)

    run = repository.create_fact_check_run(
        room_id=room_id,
        session_id=session["id"],
        scope="round",
        target_round=2,
        internet_mode="off",
        provider="ollama",
        model="observer-model",
    )
    service = FactCheckService(repository)
    result = asyncio.run(service.run(run["id"]))

    assert result["scope"] == "round"
    assert result["targetRound"] == 2
    assert len(result["claims"]) == 1
    assert result["claims"][0]["roundNumber"] == 2


def test_factcheck_session_scope_checks_whole_session(repo, monkeypatch):
    repository, room_id = repo
    session = repository.create_session(room_id, "Clinical review", "suggest")
    repository.update_session(session["id"], {"status": "completed", "last_round_number": 2})
    round1 = repository.create_round(room_id, session["id"], 1)
    round2 = repository.create_round(room_id, session["id"], 2)

    _append_agent_message(repository, room_id, session["id"], round1, 1, content="Clinical study reported a 15% reduction in risk.")
    _append_agent_message(repository, room_id, session["id"], round2, 2, content="Clinical study reported a 22% increase in adherence.")

    monkeypatch.setattr("factcheck.query_graph", lambda *_args, **_kwargs: "")

    async def fake_external(*_args, **_kwargs):
        return [], {"source": "none", "internetMode": "on", "scienceFirst": True}

    monkeypatch.setattr("factcheck.search_external_snippets", fake_external)

    run = repository.create_fact_check_run(
        room_id=room_id,
        session_id=session["id"],
        scope="session",
        target_round=None,
        internet_mode="on",
        provider="ollama",
        model="observer-model",
    )
    service = FactCheckService(repository)
    result = asyncio.run(service.run(run["id"]))

    assert result["scope"] == "session"
    assert len(result["claims"]) == 2


def test_factcheck_marks_disputed_without_contradicted_for_mixed_evidence(repo, monkeypatch):
    repository, room_id = repo
    session = repository.create_session(room_id, "Clinical review", "suggest")
    repository.update_session(session["id"], {"status": "completed", "last_round_number": 1})
    repository.set_room_graph_id(room_id, "graph_support")
    round1 = repository.create_round(room_id, session["id"], 1)

    _append_agent_message(repository, room_id, session["id"], round1, 1, content="Clinical study reported a 20% reduction in risk.")

    monkeypatch.setattr("factcheck.query_graph", lambda *_args, **_kwargs: "Clinical study reported a 20% reduction in risk.")

    service = FactCheckService(repository)
    snapshot = repository.get_session_snapshot(session["id"], make_current=False)
    claim = {
        "messageId": "msg_1",
        "roundNumber": 1,
        "participantId": "part_1",
        "profileId": "prof_1",
        "agentName": "Логос",
        "provider": "ollama",
        "model": "speaker-model",
        "claimText": "Clinical study reported a 20% reduction in risk.",
    }

    async def mixed_external(_query, _ctx):
        from tools import SearchSnippet

        return [
            SearchSnippet("science", "PubMed", "Clinical study", "Clinical study reported a 35% reduction in risk."),
        ], {"source": "science", "internetMode": "on", "scienceFirst": True}

    monkeypatch.setattr("factcheck.search_external_snippets", mixed_external)
    checked = asyncio.run(service._check_single_claim(snapshot, claim, "on"))

    assert checked["verdict"] == "disputed"


def test_factcheck_offline_marks_missing_external_sources(repo, monkeypatch):
    repository, room_id = repo
    session = repository.create_session(room_id, "Unknown claim", "suggest")
    repository.update_session(session["id"], {"status": "paused", "last_round_number": 1})
    round1 = repository.create_round(room_id, session["id"], 1)

    _append_agent_message(repository, room_id, session["id"], round1, 1, content="По данным исследования, показатель составил 77%.")

    monkeypatch.setattr("factcheck.query_graph", lambda *_args, **_kwargs: "")

    async def should_not_run(*_args, **_kwargs):
        raise AssertionError("external search should not run in offline mode")

    monkeypatch.setattr("factcheck.search_external_snippets", should_not_run)

    run = repository.create_fact_check_run(
        room_id=room_id,
        session_id=session["id"],
        scope="round",
        target_round=1,
        internet_mode="off",
        provider="ollama",
        model="observer-model",
    )
    service = FactCheckService(repository)
    result = asyncio.run(service.run(run["id"]))

    assert result["externalSourcesUsed"] is False
    assert "Внешние источники не использовались" in result["summary"]
