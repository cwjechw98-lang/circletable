"""Tests for long-term meta memory helpers."""
from __future__ import annotations

import meta_memory
from meta_memory import (
    build_session_insight,
    build_observer_memory_entry,
    casting_graph_id,
    format_insight_recall,
    observer_graph_id,
    query_casting_memory,
    select_relevant_session_insights,
)


def test_observer_graph_id_is_model_specific():
    assert observer_graph_id("ollama", "gemma4:31b-cloud") == "observer-ollama-gemma4-31b-cloud"
    assert casting_graph_id("ollama", "glm-5.1:cloud") == "casting-ollama-glm-5-1-cloud"


def test_build_observer_memory_entry_contains_model_and_roster():
    entry = build_observer_memory_entry(
        room={"name": "Комната памяти", "observerProvider": "ollama", "observerModel": "gemma4:31b-cloud"},
        session={
            "id": "session_1",
            "topic": "AI ethics",
            "status": "completed",
            "lastRoundNumber": 4,
            "observerProvider": "ollama",
            "observerModel": "gemma4:31b-cloud",
            "chronicle": "Хроника сессии.",
        },
        participants=[
            {
                "name": "Логос",
                "profileId": "prof_1",
                "role": "analyst",
                "specialty": "data-analytics",
                "provider": "ollama",
                "model": "glm-5.1:cloud",
            }
        ],
        review={"recommendation": "complete", "roundSummary": "Нашли общий вывод."},
        observer_reviews=[{"roundNumber": 4, "summary": "Финальный раунд", "recommendation": "complete"}],
    )

    assert "gemma4:31b-cloud" in entry
    assert "Логос" in entry
    assert "glm-5.1:cloud" in entry
    assert "Нашли общий вывод" in entry


def test_build_session_insight_emits_tags_and_casting_outcome():
    insight = build_session_insight(
        room={"id": "room_1", "name": "Комната памяти", "observerProvider": "ollama", "observerModel": "gemma4:31b-cloud"},
        session={
            "id": "session_1",
            "topic": "AI ethics",
            "status": "completed",
            "lastRoundNumber": 5,
            "observerProvider": "ollama",
            "observerModel": "gemma4:31b-cloud",
            "endedAt": "2026-04-12T00:00:00+00:00",
        },
        participants=[
            {
                "name": "Логос",
                "profileId": "prof_1",
                "role": "analyst",
                "specialty": "data-analytics",
                "provider": "ollama",
                "model": "glm-5.1:cloud",
            },
            {
                "name": "Резон",
                "profileId": "prof_2",
                "role": "critic",
                "specialty": "lawyer",
                "provider": "ollama",
                "model": "deepseek-r1:70b",
            },
        ],
        review={
            "recommendation": "complete",
            "roundSummary": "Состав дошёл до общего вывода.",
            "tableComment": "Критик и аналитик дали продуктивный конфликт.",
            "missingExpertHint": "Не хватало медиатора.",
            "progress": {"novelty": 73, "focus": 67, "convergence": 41},
        },
        observer_reviews=[{"roundNumber": 5, "summary": "Финальный раунд", "recommendation": "complete"}],
    )

    assert insight["observerModel"] == "gemma4:31b-cloud"
    assert "productive_conflict" in insight["tags"]
    assert "missing_expert" in insight["tags"]
    assert "ready_to_close" in insight["tags"]
    assert insight["participantProfileIds"] == ["prof_1", "prof_2"]
    assert "нехватку экспертизы" in insight["castingOutcome"]


def test_select_relevant_session_insights_prefers_profile_overlap():
    insights = [
        {
            "topic": "AI ethics",
            "observerProvider": "ollama",
            "observerModel": "gemma4:31b-cloud",
            "participantProfileIds": ["prof_1", "prof_2"],
            "participantModelPairs": [{"name": "Логос", "role": "analyst", "model": "glm"}],
            "tags": ["role_analyst", "strong_synthesis"],
            "summary": "Сильный синтез по спорной теме.",
            "castingOutcome": "Состав оказался самодостаточным.",
        },
        {
            "topic": "Marketing",
            "observerProvider": "ollama",
            "observerModel": "other-model",
            "participantProfileIds": ["prof_9"],
            "participantModelPairs": [{"name": "Искра", "role": "creative", "model": "gemini"}],
            "tags": ["role_creative"],
            "summary": "Посторонняя тема.",
            "castingOutcome": "Нерелевантно.",
        },
    ]

    selected = select_relevant_session_insights(
        insights,
        topic="AI ethics and governance",
        participants=[
            {"profileId": "prof_1", "role": "analyst"},
            {"profileId": "prof_x", "role": "critic"},
        ],
        observer_provider="ollama",
        observer_model="gemma4:31b-cloud",
        audience="observer",
    )

    assert len(selected) == 1
    assert selected[0]["summary"] == "Сильный синтез по спорной теме."
    rendered = format_insight_recall(selected, audience="observer")
    assert "AI ethics" in rendered
    assert "strong_synthesis" in rendered


def test_query_casting_memory_merges_model_and_global_context(monkeypatch):
    responses = {
        "casting-ollama-gemma4-31b-cloud": "Модельно-специфичная память.",
        "casting-global": "Глобальная память помощника.",
    }

    def fake_query_graph(graph_id, query, mode="hybrid", top_k=30, root_dir=None):
        return responses.get(graph_id, "")

    monkeypatch.setattr(meta_memory, "query_graph", fake_query_graph)
    merged = query_casting_memory(
        topic="Спорная тема",
        helper_provider="ollama",
        helper_model="gemma4:31b-cloud",
        active_participants=[{"name": "Логос", "role": "analyst", "specialty": "data-analytics"}],
        mode="gap_fill",
        missing_expert_hint="Нужен критик",
    )

    assert "Модельно-специфичная память." in merged
    assert "Глобальная память помощника." in merged
