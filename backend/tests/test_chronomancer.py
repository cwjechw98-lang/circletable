"""Unit tests for the Chronomancer observer."""
from __future__ import annotations

import asyncio

import pytest
from chronomancer import Chronomancer, STAT_LABELS


@pytest.fixture
def chrono():
    return Chronomancer()


def _make_participants(count=3):
    return [
        {
            "id": f"p_{i}",
            "profileId": f"prof_{i}",
            "name": f"Agent_{i}",
            "role": "critic",
            "specialty": "lawyer",
        }
        for i in range(count)
    ]


def _make_messages(participants, contents=None):
    if contents is None:
        contents = [f"Реплика участника {p['name']}." for p in participants]
    return [
        {
            "participant_id": p["id"],
            "agent_id": p["id"],
            "name": p["name"],
            "content": content,
        }
        for p, content in zip(participants, contents)
    ]


# ── Heuristic review ─────────────────────────

class TestHeuristicReview:
    def test_returns_required_keys(self, chrono):
        participants = _make_participants()
        messages = _make_messages(participants)
        review = chrono._heuristic_review(
            topic="Тестовая тема",
            chronicle="",
            round_number=1,
            round_messages=messages,
            participants=participants,
            room_events=[],
            wrap_requested=False,
            final_round_planned=False,
            extension_count=0,
            observer_mode="suggest",
        )
        assert "chronicle" in review
        assert "roundSummary" in review
        assert "tableComment" in review
        assert "recommendation" in review
        assert "statsDelta" in review
        assert "participantComments" in review
        assert "achievements" in review
        assert "decisionProgress" in review
        assert "rosterAdvice" in review

    def test_recommendation_continue_early_rounds(self, chrono):
        participants = _make_participants()
        messages = _make_messages(participants)
        review = chrono._heuristic_review(
            topic="Тема",
            chronicle="",
            round_number=1,
            round_messages=messages,
            participants=participants,
            room_events=[],
            wrap_requested=False,
            final_round_planned=False,
            extension_count=0,
            observer_mode="suggest",
        )
        assert review["recommendation"] == "continue"

    def test_recommendation_complete_when_final_planned(self, chrono):
        participants = _make_participants()
        messages = _make_messages(participants)
        review = chrono._heuristic_review(
            topic="Тема",
            chronicle="",
            round_number=3,
            round_messages=messages,
            participants=participants,
            room_events=[],
            wrap_requested=True,
            final_round_planned=True,
            extension_count=0,
            observer_mode="auto",
        )
        assert review["recommendation"] == "complete"

    def test_recommendation_suggest_final_after_round_4(self, chrono):
        participants = _make_participants()
        messages = _make_messages(participants)
        review = chrono._heuristic_review(
            topic="Тема",
            chronicle="",
            round_number=5,
            round_messages=messages,
            participants=participants,
            room_events=[],
            wrap_requested=False,
            final_round_planned=False,
            extension_count=0,
            observer_mode="suggest",
        )
        assert review["recommendation"] == "suggest_final"

    def test_recommendation_continue_in_manual_mode(self, chrono):
        participants = _make_participants()
        messages = _make_messages(participants)
        review = chrono._heuristic_review(
            topic="Тема",
            chronicle="",
            round_number=10,
            round_messages=messages,
            participants=participants,
            room_events=[],
            wrap_requested=False,
            final_round_planned=False,
            extension_count=0,
            observer_mode="manual",
        )
        assert review["recommendation"] == "continue"

    def test_stats_delta_per_participant(self, chrono):
        participants = _make_participants(2)
        messages = _make_messages(participants, [
            "Отличная идея, я согласен с этим решением!",
            "Есть серьёзный риск, однако нужно рассмотреть ограничения.",
        ])
        review = chrono._heuristic_review(
            topic="Бизнес-стратегия",
            chronicle="",
            round_number=1,
            round_messages=messages,
            participants=participants,
            room_events=[],
            wrap_requested=False,
            final_round_planned=False,
            extension_count=0,
            observer_mode="suggest",
        )
        for p in participants:
            profile_id = p["profileId"]
            assert profile_id in review["statsDelta"]
            delta = review["statsDelta"][profile_id]
            for stat in STAT_LABELS:
                assert stat in delta
                assert isinstance(delta[stat], int)
                assert 1 <= delta[stat] <= 5

    def test_tool_calls_boost_insight_and_depth(self, chrono):
        participants = _make_participants(1)
        messages = _make_messages(participants, ["Короткий ответ."])
        messages[0]["toolCalls"] = [{"tool": "calculate", "query": "2 + 2", "result": "4", "ok": True}]
        review = chrono._heuristic_review(
            topic="Тема",
            chronicle="",
            round_number=1,
            round_messages=messages,
            participants=participants,
            room_events=[],
            wrap_requested=False,
            final_round_planned=False,
            extension_count=0,
            observer_mode="suggest",
        )
        delta = review["statsDelta"][participants[0]["profileId"]]
        assert delta["insight"] >= 2
        assert delta["depth"] >= 2

    def test_chronicle_appends(self, chrono):
        participants = _make_participants()
        messages = _make_messages(participants)
        review = chrono._heuristic_review(
            topic="Тема",
            chronicle="Раунд 1: всё началось.",
            round_number=2,
            round_messages=messages,
            participants=participants,
            room_events=[],
            wrap_requested=False,
            final_round_planned=False,
            extension_count=0,
            observer_mode="suggest",
        )
        assert "Раунд 1" in review["chronicle"]
        assert "Раунд 2" in review["chronicle"]

    def test_event_note_for_added_participant(self, chrono):
        participants = _make_participants()
        messages = _make_messages(participants)
        events = [
            {"type": "participant_added", "payload": {"name": "Новичок"}},
        ]
        review = chrono._heuristic_review(
            topic="Тема",
            chronicle="",
            round_number=1,
            round_messages=messages,
            participants=participants,
            room_events=events,
            wrap_requested=False,
            final_round_planned=False,
            extension_count=0,
            observer_mode="suggest",
        )
        assert "Новичок" in review["tableComment"] or "новый угол" in review["tableComment"].lower()

    def test_wrap_requested_triggers_suggest_final(self, chrono):
        participants = _make_participants()
        messages = _make_messages(participants)
        review = chrono._heuristic_review(
            topic="Тема",
            chronicle="",
            round_number=2,
            round_messages=messages,
            participants=participants,
            room_events=[],
            wrap_requested=True,
            final_round_planned=False,
            extension_count=0,
            observer_mode="suggest",
        )
        assert review["recommendation"] == "suggest_final"

    def test_heuristic_excess_participant_stays_null_when_confidence_is_low(self, chrono):
        participants = _make_participants(4)
        messages = _make_messages(participants, [
            "Обсуждаем внедрение RAG и аккуратную проверку источников.",
            "Согласен: нужно отделить факты от интерпретаций и вести к решению.",
            "Добавлю риск: без источников итог будет слабым.",
            "Нужен план внедрения и понятный следующий шаг.",
        ])
        review = chrono._heuristic_review(
            topic="Как внедрять RAG и проверку источников",
            chronicle="",
            round_number=2,
            round_messages=messages,
            participants=participants,
            room_events=[],
            wrap_requested=False,
            final_round_planned=False,
            extension_count=0,
            observer_mode="suggest",
        )
        assert review["rosterAdvice"]["excessParticipant"] is None


class TestReviewRoundFallback:
    def test_review_round_falls_back_to_heuristics_if_llm_path_raises(self, chrono, monkeypatch):
        participants = _make_participants()
        messages = _make_messages(participants)

        async def broken_llm(**kwargs):
            raise asyncio.TimeoutError()

        monkeypatch.setattr(chrono, "_try_llm_review", broken_llm)

        review = asyncio.run(
            chrono.review_round(
                topic="Тема",
                observer_provider="ollama",
                observer_model="gemma4:31b-cloud",
                observer_mode="suggest",
                chronicle="",
                round_number=1,
                round_messages=messages,
                participants=participants,
                room_events=[],
                wrap_requested=False,
                final_round_planned=False,
                extension_count=0,
            )
        )

        assert review["roundSummary"]
        assert review["recommendation"] == "continue"
        assert review["chronicle"].startswith("Раунд 1:")

    def test_try_llm_review_includes_observer_memory(self, chrono, monkeypatch):
        participants = _make_participants(2)
        messages = _make_messages(participants)
        captured = {}

        class FakeProvider:
            def is_available(self):
                return True

            async def stream_chat(self, model, messages, on_token=None):
                captured["prompt"] = messages[1]["content"]
                return (
                    '{"roundSummary":"Итог","chronicle":"Хроника","tableComment":"Комментарий",'
                    '"recommendation":"continue","suggestedRoundsLeft":null,"finalReason":"",'
                    '"missingExpertHint":"","progress":{"novelty":55,"focus":62,"convergence":34},'
                    '"participantComments":{},"statsDelta":{},"achievements":[]}'
                )

        monkeypatch.setattr("chronomancer.get_provider", lambda _provider: FakeProvider())
        monkeypatch.setattr("chronomancer.query_observer_memory", lambda **kwargs: "Раньше этот состав уже спорил о похожей теме.")

        review = asyncio.run(
            chrono._try_llm_review(
                topic="Тема",
                observer_provider="ollama",
                observer_model="gemma4:31b-cloud",
                observer_mode="suggest",
                chronicle="",
                round_number=2,
                round_messages=messages,
                participants=participants,
                room_events=[],
                wrap_requested=False,
                final_round_planned=False,
                extension_count=0,
                curated_recall="Куратор памяти: похожие столы хорошо работали при мягком синтезе после конфликта.",
            )
        )

        assert review is not None
        assert "Куратор памяти" in captured["prompt"]
        assert "Раньше этот состав уже спорил" in captured["prompt"]


# ── Normalize review ──────────────────────────

class TestNormalizeReview:
    def test_filters_invalid_profile_ids(self, chrono):
        participants = _make_participants(2)
        raw_review = {
            "roundSummary": "Test",
            "chronicle": "Test chronicle",
            "tableComment": "Хрономант видит.",
            "recommendation": "continue",
            "statsDelta": {
                "prof_0": {"insight": 3, "focus": 2, "depth": 1, "cooperation": 2, "showmanship": 1},
                "prof_999": {"insight": 5},  # invalid profile — should be filtered
            },
            "participantComments": {
                "prof_0": "Хороший ход.",
                "prof_999": "Не должно быть.",
            },
            "achievements": [
                {"profileId": "prof_0", "title": "Тест", "reason": "Тестовая причина"},
                {"profileId": "prof_999", "title": "Нет", "reason": "Не должно быть"},
            ],
        }
        result = chrono._normalize_review(
            review=raw_review,
            chronicle_before="",
            round_number=1,
            participants=participants,
        )
        assert "prof_0" in result["statsDelta"]
        assert "prof_999" not in result["statsDelta"]
        assert "prof_0" in result["participantComments"]
        assert "prof_999" not in result["participantComments"]
        assert len(result["achievements"]) == 1
        assert result["achievements"][0]["profileId"] == "prof_0"

    def test_normalizes_decision_progress_and_roster_advice(self, chrono):
        participants = _make_participants(2)
        raw_review = {
            "roundSummary": "Test",
            "chronicle": "Test chronicle",
            "recommendation": "continue",
            "missingExpertHint": "Практик по продажам.",
            "progress": {"novelty": 61, "focus": 42, "convergence": 55},
            "decisionProgress": {
                "stage": "converge",
                "readiness": 67,
                "blocker": "Не хватает продаж.",
                "nextAction": "add_expert",
                "rationale": "Нужен коммерческий угол.",
            },
            "rosterAdvice": {
                "missingExpertHint": "Практик по продажам.",
                "excessParticipant": {
                    "participantId": "p_1",
                    "profileId": "prof_1",
                    "name": "Agent_1",
                    "reason": "Уводит разговор в спор без пользы.",
                    "confidence": 72,
                },
                "balanceNote": "Состав нужно сфокусировать.",
                "gapStatus": "conflicted",
            },
        }
        result = chrono._normalize_review(
            review=raw_review,
            chronicle_before="",
            round_number=1,
            participants=participants,
        )
        assert result["progress"]["decisionProgress"]["stage"] == "converge"
        assert result["decisionProgress"]["readiness"] == 67
        assert result["rosterAdvice"]["missingExpertHint"] == "Практик по продажам."
        assert result["rosterAdvice"]["excessParticipant"]["participantId"] == "p_1"


# ── Topic keywords ────────────────────────────

class TestTopicKeywords:
    def test_extracts_long_words(self, chrono):
        kw = chrono._topic_keywords("Искусственный интеллект в маркетинге")
        assert len(kw) > 0
        for word in kw:
            assert len(word) >= 4

    def test_limits_to_8(self, chrono):
        kw = chrono._topic_keywords(
            "один два три четыре пять шесть семь восемь девять десять одиннадцать"
        )
        assert len(kw) <= 8
