from __future__ import annotations

import asyncio
import os
import tempfile

import pytest

from reports import ReportGenerator
from storage import Repository


@pytest.fixture
def repo():
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test.db")
    repository = Repository(db_path)
    yield repository
    repository.close()


def test_report_generator_uses_local_fallback(repo):
    room_id = repo.create_room(
        name="Отчётная комната",
        observer_mode="suggest",
        observer_provider="ollama",
        observer_model="missing-model",
    )
    session = repo.create_session(room_id, "Как внедрять RAG в дискуссии", "suggest")
    round_id = repo.create_round(room_id, session["id"], 1)
    repo.append_message(
        room_id,
        session["id"],
        {
            "type": "agent_message",
            "name": "Логос",
            "agent_name": "Логос",
            "role": "critic",
            "specialty": "lawyer",
            "content": "Нужно отделить проверяемые факты от интерпретаций.",
            "author_type": "agent",
            "round": 1,
        },
        round_id=round_id,
        round_number=1,
        message_type="agent_message",
        author_type="agent",
    )
    repo.save_observer_review(room_id, session["id"], round_id, 1, {
        "roundSummary": "Участники сошлись на том, что факты нужно подмешивать в системный контекст, а не в пользовательский.",
        "chronicleBefore": "",
        "chronicle": "Наметился консенсус по аккуратной интеграции RAG.",
        "recommendation": "complete",
        "participantComments": {"Логос": "Сильно держал юридическую рамку аргумента."},
        "achievements": [],
        "statsDelta": {},
        "progress": {
            "novelty": 45,
            "focus": 78,
            "convergence": 82,
            "decisionProgress": {
                "stage": "decide",
                "readiness": 88,
                "blocker": "Нужно зафиксировать формат интеграции.",
                "nextAction": "final_round",
            },
        },
        "finalReason": "Главный вывод уже сформулирован.",
        "rosterAdvice": {
            "missingExpertHint": "",
            "excessParticipant": None,
            "balanceNote": "Состав достаточен.",
            "gapStatus": "resolved",
        },
    })
    repo.update_session(session["id"], {
        "status": "completed",
        "chronicle": "Наметился консенсус по аккуратной интеграции RAG.",
        "lastRoundNumber": 1,
        "endedAt": "2026-04-12T00:00:00+00:00",
    })

    generator = ReportGenerator(repo)
    report = asyncio.run(generator.generate(session["id"], provider_name="missing"))

    assert report["provider"] == "heuristic"
    assert report["model"] == "local-fallback"
    assert "## 1. Резюме" in report["markdown"]
    assert "## Динамика решения" in report["markdown"]
    assert "готовность 88%" in report["markdown"]
    assert len(report["sections"]) == 5
