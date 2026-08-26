"""Unit tests for the Repository (storage layer)."""
from __future__ import annotations

import os
import tempfile
import pytest
from storage import Repository, utc_now, make_id


@pytest.fixture
def repo():
    """Create a temporary in-memory-like repository for each test."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test.db")
    r = Repository(db_path)
    yield r
    r.close()


def _create_room(repo, name="Тест"):
    """Helper — create a room with all required arguments."""
    return repo.create_room(
        name=name,
        observer_mode="suggest",
        observer_provider="ollama",
        observer_model="test-model",
    )


def _make_profile_data(name="Герой", role="critic", specialty="lawyer"):
    return {
        "name": name,
        "role": role,
        "specialty": specialty,
        "provider": "ollama",
        "model": "test-model",
        "emoji": "🧙",
        "mascot": "wizard",
        "stats": {"insight": 50, "focus": 50, "depth": 50, "cooperation": 50, "showmanship": 50},
        "strengths": [],
        "weaknesses": [],
        "summary": "",
        "last_note": "Тестовый.",
    }


# ── Basic operations ──────────────────────────

class TestRoomOperations:
    def test_create_room(self, repo):
        room_id = _create_room(repo, name="Комната 1")
        assert room_id is not None
        rooms = repo.list_rooms()
        assert len(rooms) == 1
        assert rooms[0]["name"] == "Комната 1"

    def test_set_current_room(self, repo):
        room_id = _create_room(repo, name="Комната")
        repo.set_current_room(room_id)
        assert repo.get_current_room_id() == room_id

    def test_room_exists(self, repo):
        room_id = _create_room(repo, name="Тест")
        assert repo.room_exists(room_id) is True
        assert repo.room_exists("nonexistent") is False

    def test_delete_room(self, repo):
        room_id = _create_room(repo, name="Удалить")
        repo.delete_room(room_id)
        assert repo.room_exists(room_id) is False

    def test_update_room_settings(self, repo):
        room_id = _create_room(repo, name="Настройки")
        repo.update_room_settings(room_id, name="Новое имя", observer_mode="auto")
        snapshot = repo.get_room_snapshot(room_id)
        assert snapshot["room"]["name"] == "Новое имя"
        assert snapshot["room"]["observerMode"] == "auto"

    def test_room_tool_settings_roundtrip(self, repo):
        room_id = _create_room(repo, name="Инструменты")
        snapshot = repo.get_room_snapshot(room_id)
        assert snapshot["room"]["internetMode"] == "auto"
        assert snapshot["room"]["toolsEnabled"] is False
        assert "search_knowledge" in snapshot["room"]["availableTools"]

        repo.update_room_settings(
            room_id,
            settings={"tools_enabled": True, "available_tools": ["calculate", "web_search"]},
        )
        updated = repo.get_room_snapshot(room_id)
        assert updated["room"]["internetMode"] == "auto"
        assert updated["room"]["toolsEnabled"] is True
        assert updated["room"]["availableTools"] == ["calculate", "web_search"]

    def test_room_snapshot_structure(self, repo):
        room_id = _create_room(repo, name="Снимок")
        snapshot = repo.get_room_snapshot(room_id)
        assert "room" in snapshot
        assert "participants" in snapshot
        assert "active" in snapshot["participants"]
        assert "benched" in snapshot["participants"]
        assert "inventory" in snapshot
        assert "session" in snapshot
        assert "messages" in snapshot

    def test_room_graph_id_roundtrip(self, repo):
        room_id = _create_room(repo, name="Граф")
        assert repo.get_room_graph_id(room_id) is None

        repo.set_room_graph_id(room_id, "graph_test_123")
        assert repo.get_room_graph_id(room_id) == "graph_test_123"

        snapshot = repo.get_room_snapshot(room_id)
        assert snapshot["room"]["graphId"] == "graph_test_123"


# ── Profile operations ────────────────────────

class TestProfileOperations:
    def test_create_saved_profile(self, repo):
        data = _make_profile_data("Тестовый Герой")
        profile_id = repo.create_profile(data, is_saved=True, system_provided=False)
        assert profile_id is not None
        profile = repo.get_profile(profile_id)
        assert profile["name"] == "Тестовый Герой"

    def test_list_saved_profiles(self, repo):
        repo.create_profile(_make_profile_data("А"), is_saved=True, system_provided=False)
        repo.create_profile(_make_profile_data("Б"), is_saved=True, system_provided=False)
        repo.create_profile(_make_profile_data("В"), is_saved=False, system_provided=False)
        profiles = repo.list_saved_profiles()
        names = [p["name"] for p in profiles]
        assert "А" in names
        assert "Б" in names
        assert "В" not in names

    def test_update_profile(self, repo):
        profile_id = repo.create_profile(_make_profile_data("Старый"), is_saved=True, system_provided=False)
        repo.update_profile(profile_id, {"name": "Новый"})
        profile = repo.get_profile(profile_id)
        assert profile["name"] == "Новый"

    def test_profile_memory_graph_id_roundtrip(self, repo):
        profile_id = repo.create_profile(_make_profile_data("С памятью"), is_saved=True, system_provided=False)
        assert repo.get_profile_memory_graph_id(profile_id) is None

        repo.set_profile_memory_graph_id(profile_id, "char_memory_1")
        assert repo.get_profile_memory_graph_id(profile_id) == "char_memory_1"

        profile = repo.get_profile(profile_id)
        assert profile["memoryGraphId"] == "char_memory_1"
        assert profile["hasMemory"] is True

    def test_delete_profile(self, repo):
        profile_id = repo.create_profile(_make_profile_data(), is_saved=True, system_provided=False)
        repo.delete_profile(profile_id)
        assert repo.get_profile(profile_id) is None


# ── Participant operations ────────────────────

class TestParticipantOperations:
    def test_add_participant_from_profile(self, repo):
        room_id = _create_room(repo, name="Участники")
        profile_id = repo.create_profile(_make_profile_data("Боец"), is_saved=True, system_provided=False)
        participant_id = repo.add_participant_from_profile(room_id, profile_id, status="active")
        assert participant_id is not None
        participant = repo.get_participant(participant_id)
        assert participant["name"] == "Боец"

    def test_bench_and_restore(self, repo):
        room_id = _create_room(repo, name="Скамейка")
        profile_id = repo.create_profile(_make_profile_data("Запас"), is_saved=True, system_provided=False)
        participant_id = repo.add_participant_from_profile(room_id, profile_id, status="active")

        active = repo.get_active_participants(room_id)
        assert any(p["id"] == participant_id for p in active)

        repo.bench_participant(participant_id)
        active = repo.get_active_participants(room_id)
        assert not any(p["id"] == participant_id for p in active)

        repo.restore_participant(participant_id)
        active = repo.get_active_participants(room_id)
        assert any(p["id"] == participant_id for p in active)


# ── Session operations ────────────────────────

class TestSessionOperations:
    def test_create_session(self, repo):
        room_id = _create_room(repo, name="Сессия")
        session = repo.create_session(room_id, "Тестовая тема", "suggest")
        assert session["topic"] == "Тестовая тема"
        assert session["status"] == "running"
        assert session["observerProvider"] == "ollama"
        assert session["observerModel"] == "test-model"

    def test_update_session(self, repo):
        room_id = _create_room(repo, name="Сессия")
        session = repo.create_session(room_id, "Тема", "suggest")
        repo.update_session(session["id"], {"status": "paused"})
        updated = repo.get_session(session["id"])
        assert updated["status"] == "paused"

    def test_list_room_sessions(self, repo):
        room_id = _create_room(repo, name="Архив")
        repo.create_session(room_id, "Тема 1", "suggest")
        repo.create_session(room_id, "Тема 2", "auto")
        sessions = repo.list_room_sessions(room_id)
        assert len(sessions) == 2

    def test_session_snapshot(self, repo):
        room_id = _create_room(repo, name="Снимок")
        session = repo.create_session(room_id, "Тема", "suggest")
        snapshot = repo.get_session_snapshot(session["id"])
        assert snapshot is not None
        assert "room" in snapshot
        assert "session" in snapshot

    def test_create_session_from_final_preserves_observer_identity(self, repo):
        room_id = _create_room(repo, name="Финал")
        session = repo.create_session(room_id, "Тема", "suggest")
        repo.update_session(session["id"], {"status": "completed", "chronicle": "Итог"})
        next_session = repo.create_session_from_final(session["id"])
        assert next_session is not None
        assert next_session["observerProvider"] == "ollama"
        assert next_session["observerModel"] == "test-model"

    def test_observer_reviews_are_returned_in_round_order(self, repo):
        room_id = _create_room(repo, name="Обзоры")
        session = repo.create_session(room_id, "Тема", "suggest")
        round1 = repo.create_round(room_id, session["id"], 1)
        round2 = repo.create_round(room_id, session["id"], 2)

        repo.save_observer_review(room_id, session["id"], round1, 1, {
            "roundSummary": "Первый раунд",
            "chronicleBefore": "",
            "chronicle": "Итог 1",
            "recommendation": "continue",
            "participantComments": {},
            "achievements": [],
            "statsDelta": {},
            "progress": {},
        })
        repo.save_observer_review(room_id, session["id"], round2, 2, {
            "roundSummary": "Второй раунд",
            "chronicleBefore": "Итог 1",
            "chronicle": "Итог 2",
            "recommendation": "complete",
            "participantComments": {},
            "achievements": [],
            "statsDelta": {},
            "progress": {},
        })

        reviews = repo.get_observer_reviews(session["id"])
        assert [review["roundNumber"] for review in reviews] == [1, 2]

    def test_observer_review_roundtrip_keeps_decision_progress_and_roster_advice(self, repo):
        room_id = _create_room(repo, name="Советы")
        session = repo.create_session(room_id, "Тема", "suggest")
        round_id = repo.create_round(room_id, session["id"], 1)
        repo.save_observer_review(room_id, session["id"], round_id, 1, {
            "roundSummary": "Раунд сфокусировался на вариантах.",
            "chronicleBefore": "",
            "chronicle": "Есть варианты решения.",
            "recommendation": "continue",
            "participantComments": {},
            "achievements": [],
            "statsDelta": {},
            "progress": {
                "novelty": 56,
                "focus": 63,
                "convergence": 48,
                "decisionProgress": {
                    "stage": "converge",
                    "readiness": 64,
                    "blocker": "Не хватает коммерческого угла.",
                    "nextAction": "add_expert",
                },
            },
            "rosterAdvice": {
                "missingExpertHint": "Практик по продажам.",
                "excessParticipant": {
                    "participantId": "part_1",
                    "profileId": "prof_1",
                    "name": "Шумный",
                    "reason": "Уводит разговор в сторону.",
                    "confidence": 71,
                },
                "balanceNote": "Нужна фокусировка состава.",
                "gapStatus": "conflicted",
            },
        })

        review = repo.get_observer_reviews(session["id"])[0]
        assert review["progress"]["decisionProgress"]["readiness"] == 64
        assert review["rosterAdvice"]["missingExpertHint"] == "Практик по продажам."
        assert review["rosterAdvice"]["excessParticipant"]["name"] == "Шумный"
        markdown = repo.export_session_markdown(session["id"])
        assert "## Динамика решения" in markdown
        assert "Практик по продажам" in markdown

    def test_legacy_observer_review_rows_default_roster_advice(self, repo):
        room_id = _create_room(repo, name="Старые обзоры")
        session = repo.create_session(room_id, "Тема", "suggest")
        round_id = repo.create_round(room_id, session["id"], 1)
        repo.conn.execute(
            """
            INSERT INTO observer_reviews (
                id, room_id, session_id, round_id, round_number, summary,
                chronicle_before, chronicle_after, recommendation, suggested_rounds_left,
                comments_json, achievements_json, stats_delta_json, progress_json,
                final_reason, missing_expert_hint, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                make_id("review"),
                room_id,
                session["id"],
                round_id,
                1,
                "Старый обзор",
                "",
                "Хроника",
                "continue",
                None,
                "{}",
                "[]",
                "{}",
                "{}",
                "",
                "",
                utc_now(),
            ),
        )
        repo.conn.commit()
        review = repo.get_observer_reviews(session["id"])[0]
        assert review["rosterAdvice"] == {}

    def test_session_insights_roundtrip(self, repo):
        room_id = _create_room(repo, name="Память")
        session = repo.create_session(room_id, "Тема памяти", "suggest")
        saved = repo.save_session_insight(
            {
                "sessionId": session["id"],
                "roomId": room_id,
                "topic": "Тема памяти",
                "observerProvider": "ollama",
                "observerModel": "test-model",
                "rosterHash": "abc123",
                "participantProfileIds": ["prof_1", "prof_2"],
                "participantModelPairs": [{"name": "Логос", "profileId": "prof_1", "role": "analyst", "model": "glm"}],
                "tags": ["strong_synthesis", "role_analyst"],
                "summary": "Сильная сессия.",
                "castingOutcome": "Состав оказался самодостаточным.",
                "curatedAt": "2026-04-12T00:00:00+00:00",
            }
        )
        assert saved is not None
        assert saved["observerModel"] == "test-model"
        listed = repo.list_session_insights(observer_provider="ollama", observer_model="test-model")
        assert len(listed) == 1
        assert listed[0]["summary"] == "Сильная сессия."
        assert listed[0]["participantProfileIds"] == ["prof_1", "prof_2"]

    def test_report_roundtrip(self, repo):
        room_id = _create_room(repo, name="Отчёт")
        session = repo.create_session(room_id, "Тема", "suggest")

        report = repo.save_report(
            session["id"],
            room_id,
            "# Report\n\nText\n",
            [{"id": "summary", "title": "1. Резюме", "markdown": "Text"}],
            "heuristic",
            "local-fallback",
        )
        assert report["sessionId"] == session["id"]
        assert report["provider"] == "heuristic"

        latest = repo.get_latest_report(session["id"])
        assert latest is not None
        assert latest["markdown"].startswith("# Report")
        assert latest["sections"][0]["id"] == "summary"

        snapshot = repo.get_session_snapshot(session["id"])
        assert snapshot["report"]["id"] == report["id"]

    def test_fact_check_roundtrip_and_snapshot(self, repo):
        room_id = _create_room(repo, name="Фактчекинг")
        session = repo.create_session(room_id, "Тема", "suggest")

        run = repo.create_fact_check_run(
            room_id=room_id,
            session_id=session["id"],
            scope="round",
            target_round=2,
            internet_mode="off",
            provider="ollama",
            model="test-model",
        )
        repo.replace_fact_check_claims(run["id"], [
            {
                "messageId": "msg_1",
                "roundNumber": 2,
                "participantId": "part_1",
                "profileId": "prof_1",
                "agentName": "Логос",
                "provider": "ollama",
                "model": "test-model",
                "claimText": "По данным отчёта, выручка выросла на 20%.",
                "verdict": "confirmed",
                "evidence": "Документы комнаты подтверждают рост на 20%.",
                "sourceType": "knowledge",
                "sourceLabel": "Документы комнаты",
            }
        ])
        updated = repo.update_fact_check_run(
            run["id"],
            status="completed",
            progress=100,
            summary="Фактчекинг раунда 2 завершён.",
            counts={"confirmed": 1, "unverified": 0, "contradicted": 0, "disputed": 0, "insufficient_evidence": 0},
            model_deltas=[],
            external_sources_used=False,
            completed_at=utc_now(),
        )

        assert updated["status"] == "completed"
        assert updated["internetMode"] == "off"
        assert len(updated["claims"]) == 1

        latest = repo.get_latest_fact_check_run(session["id"])
        assert latest["id"] == run["id"]

        snapshot = repo.get_session_snapshot(session["id"])
        assert snapshot["factCheck"]["id"] == run["id"]

    def test_model_reliability_rollup_accumulates(self, repo):
        deltas_first = repo.apply_model_reliability_rollup([
            {"provider": "ollama", "model": "gemma", "verdict": "confirmed"},
            {"provider": "ollama", "model": "gemma", "verdict": "contradicted"},
        ])
        deltas_second = repo.apply_model_reliability_rollup([
            {"provider": "ollama", "model": "gemma", "verdict": "confirmed"},
        ])

        rollup = repo.get_model_reliability("ollama", "gemma")
        assert deltas_first[0]["checkedClaimsAfter"] == 2
        assert deltas_second[0]["checkedClaimsBefore"] == 2
        assert rollup["checkedClaims"] == 3
        assert rollup["counts"]["confirmed"] == 2
        assert rollup["counts"]["contradicted"] == 1


# ── Message operations ────────────────────────

class TestMessageOperations:
    def test_append_and_list_messages(self, repo):
        room_id = _create_room(repo, name="Чат")
        session = repo.create_session(room_id, "Тема", "suggest")
        payload = {"type": "agent_message", "content": "Привет от агента."}
        stored = repo.append_message(
            room_id, session["id"], payload,
            message_type="agent_message", author_type="agent",
        )
        assert stored["content"] == "Привет от агента."

        messages = repo.list_session_messages(session["id"])
        assert len(messages) >= 1
        assert any(m["content"] == "Привет от агента." for m in messages)


# ── Planned event operations ──────────────────

class TestPlannedEventOperations:
    def test_planned_event_crud(self, repo):
        room_id = _create_room(repo, name="События")
        session = repo.create_session(room_id, "Тема", "suggest")

        event = repo.create_planned_event(room_id, 3, "Бюджет сокращён.", session["id"])
        assert event["targetRound"] == 3
        assert event["description"] == "Бюджет сокращён."
        assert event["fired"] is False

        events = repo.list_planned_events(room_id, session["id"])
        assert [item["id"] for item in events] == [event["id"]]

        updated = repo.update_planned_event(room_id, event["id"], {"targetRound": 4, "description": "Новый риск."})
        assert updated["targetRound"] == 4
        assert updated["description"] == "Новый риск."

        assert repo.delete_planned_event(room_id, event["id"]) is True
        assert repo.list_planned_events(room_id, session["id"]) == []

    def test_pending_events_mark_fired(self, repo):
        room_id = _create_room(repo, name="Вброс")
        session = repo.create_session(room_id, "Тема", "suggest")
        event = repo.create_planned_event(room_id, 2, "Появился новый конкурент.", session["id"])

        pending = repo.get_pending_events(room_id, session["id"], 2)
        assert len(pending) == 1
        assert pending[0]["id"] == event["id"]

        fired = repo.mark_event_fired(event["id"])
        assert fired["fired"] is True
        assert fired["firedAt"]
        assert repo.get_pending_events(room_id, session["id"], 2) == []


# ── Round operations ──────────────────────────

class TestRoundOperations:
    def test_create_round(self, repo):
        room_id = _create_room(repo, name="Раунд")
        session = repo.create_session(room_id, "Тема", "suggest")
        round_id = repo.create_round(room_id, session["id"], 1)
        assert round_id is not None

    def test_complete_round(self, repo):
        room_id = _create_room(repo, name="Раунд")
        session = repo.create_session(room_id, "Тема", "suggest")
        round_id = repo.create_round(room_id, session["id"], 1)
        review = {
            "roundSummary": "Тест.",
            "chronicle": "Хроника.",
            "recommendation": "continue",
        }
        repo.complete_round(round_id, review)
        # No error means success


# ── Utility functions ─────────────────────────

class TestUtilities:
    def test_utc_now_format(self):
        ts = utc_now()
        assert "T" in ts
        assert "+" in ts or "Z" in ts or "UTC" in ts or ts.endswith("+00:00")

    def test_make_id_prefix(self):
        id1 = make_id("room")
        assert id1.startswith("room_")
        id2 = make_id("sess")
        assert id2.startswith("sess_")

    def test_make_id_unique(self):
        ids = {make_id("test") for _ in range(100)}
        assert len(ids) == 100
