from __future__ import annotations

import asyncio
import os
import tempfile

from debate import DebateEngine, PreparedTurn, RoundState
from storage import Repository


def _make_repo() -> Repository:
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "debate-test.db")
    return Repository(db_path)


async def _broadcast(_payload: dict):
    return None


def _create_room(repo: Repository) -> str:
    return repo.create_room(
        name="Комната RAG",
        observer_mode="suggest",
        observer_provider="ollama",
        observer_model="test-model",
    )


def _create_profile(repo: Repository, name: str, role: str = "critic", specialty: str = "lawyer") -> str:
    return repo.create_profile(
        {
            "name": name,
            "role": role,
            "specialty": specialty,
            "provider": "ollama",
            "model": "test-model",
            "emoji": "🧙",
            "mascot": "wizard",
            "stats": {},
            "strengths": [],
            "weaknesses": [],
            "summary": "",
            "lastNote": "",
        },
        is_saved=True,
        system_provided=False,
    )


def _add_participant(repo: Repository, room_id: str, *, name: str, role: str = "critic", specialty: str = "lawyer") -> dict:
    profile_id = _create_profile(repo, name=name, role=role, specialty=specialty)
    participant_id = repo.add_participant_from_profile(room_id, profile_id, status="active")
    return repo.get_participant(participant_id)


def _append_agent_message(repo: Repository, room_id: str, session_id: str, participant: dict, content: str, *, round_id: str | None = None, round_number: int = 1):
    return repo.append_message(
        room_id,
        session_id,
        {
            "type": "agent_message",
            "agent_id": participant["id"],
            "participant_id": participant["id"],
            "profile_id": participant["profileId"],
            "agent_name": participant["name"],
            "name": participant["name"],
            "agent_emoji": participant["emoji"],
            "emoji": participant["emoji"],
            "mascot": participant["mascot"],
            "role": participant["role"],
            "specialty": participant["specialty"],
            "content": content,
            "round": round_number,
            "author_type": "agent",
        },
        round_id=round_id,
        round_number=round_number,
        message_type="agent_message",
        author_type="agent",
        participant_id=participant["id"],
    )


class TestDebateEngineRag:
    def test_build_agent_context_includes_graph_id_and_memory_graph_id(self):
        repo = _make_repo()
        try:
            room_id = _create_room(repo)
            repo.set_room_graph_id(room_id, "graph_room_1")
            profile_id = repo.create_profile(
                {
                    "name": "Памятливый",
                    "role": "critic",
                    "specialty": "lawyer",
                    "provider": "ollama",
                    "model": "test-model",
                    "emoji": "🧙",
                    "mascot": "wizard",
                    "stats": {},
                    "strengths": [],
                    "weaknesses": [],
                    "summary": "",
                    "lastNote": "",
                },
                is_saved=True,
                system_provided=False,
            )
            repo.set_profile_memory_graph_id(profile_id, "memory_profile_1")
            session = repo.create_session(room_id, "Тема", "suggest")
            engine = DebateEngine(_broadcast, repo)

            context = engine._build_agent_context(
                room_id,
                session["id"],
                "round_1",
                1,
                participant={"profileId": profile_id, "memoryGraphId": "memory_profile_1"},
            )
            assert context["graph_id"] == "graph_room_1"
            assert context["memory_graph_id"] == "memory_profile_1"
            assert context["round_id"] == "round_1"
        finally:
            repo.close()

    def test_round_rag_cache_reuses_result_within_round(self, monkeypatch):
        repo = _make_repo()
        try:
            room_id = _create_room(repo)
            session = repo.create_session(room_id, "Тема", "suggest")
            engine = DebateEngine(_broadcast, repo)
            calls = {"count": 0}

            def fake_query_graph(graph_id, query, mode="hybrid", top_k=20):
                calls["count"] += 1
                return f"ctx:{graph_id}:{query}"

            monkeypatch.setattr("debate.query_graph", fake_query_graph)
            ctx = {
                "topic": "Тема",
                "graph_id": "graph_room_1",
                "history": [{"content": "Первый аргумент."}],
            }

            first = asyncio.run(engine._get_round_rag_context("round_1", ctx))
            second = asyncio.run(engine._get_round_rag_context("round_1", ctx))

            assert first == second
            assert calls["count"] == 1
        finally:
            repo.close()

    def test_round_rag_cache_clears_when_round_changes(self, monkeypatch):
        repo = _make_repo()
        try:
            room_id = _create_room(repo)
            repo.create_session(room_id, "Тема", "suggest")
            engine = DebateEngine(_broadcast, repo)
            calls = {"count": 0}

            def fake_query_graph(graph_id, query, mode="hybrid", top_k=20):
                calls["count"] += 1
                return f"ctx:{calls['count']}"

            monkeypatch.setattr("debate.query_graph", fake_query_graph)
            ctx = {
                "topic": "Тема",
                "graph_id": "graph_room_1",
                "history": [{"content": "Первый аргумент."}],
            }

            first = asyncio.run(engine._get_round_rag_context("round_1", ctx))
            second = asyncio.run(engine._get_round_rag_context("round_2", ctx))

            assert first != second
            assert calls["count"] == 2
        finally:
            repo.close()

    def test_store_profile_memory_creates_graph_and_persists_text(self, monkeypatch):
        repo = _make_repo()
        try:
            room_id = _create_room(repo)
            profile_id = repo.create_profile(
                {
                    "name": "Мнемоник",
                    "role": "critic",
                    "specialty": "lawyer",
                    "provider": "ollama",
                    "model": "test-model",
                    "emoji": "🧙",
                    "mascot": "wizard",
                    "stats": {},
                    "strengths": [],
                    "weaknesses": [],
                    "summary": "",
                    "lastNote": "",
                },
                is_saved=True,
                system_provided=False,
            )
            engine = DebateEngine(_broadcast, repo)
            created = {}
            inserted = {}

            monkeypatch.setattr("debate.create_profile_graph", lambda current_profile_id: created.setdefault("graph_id", current_profile_id))

            def fake_insert_text(graph_id, texts, root_dir=None):
                inserted["graph_id"] = graph_id
                inserted["texts"] = texts
                inserted["root_dir"] = root_dir

            monkeypatch.setattr("debate.insert_text", fake_insert_text)

            asyncio.run(
                engine._store_profile_memory(
                    room_id,
                    2,
                    {
                        "id": "seat_1",
                        "profileId": profile_id,
                        "name": "Мнемоник",
                        "role": "critic",
                        "specialty": "lawyer",
                    },
                    {
                        "topic": "AI ethics",
                        "room_name": "Комната RAG",
                        "observer_provider": "ollama",
                        "observer_model": "gemma4:31b-cloud",
                        "active_participants": [
                            {"name": "Мнемоник", "role": "critic", "specialty": "lawyer"},
                            {"name": "Alice", "role": "analyst", "specialty": "data-analytics"},
                        ],
                        "history": [
                            {"agent_name": "Alice", "content": "Нужны границы."},
                            {"agent_name": "Bob", "content": "Согласен, но без паралича."},
                        ],
                    },
                    "Я поддерживаю поэтапное внедрение с чёткими правилами.",
                )
            )

            assert created["graph_id"] == profile_id
            assert repo.get_profile_memory_graph_id(profile_id) == profile_id
            assert inserted["graph_id"] == profile_id
            assert inserted["root_dir"] is not None
            assert "AI ethics" in inserted["texts"][0]
            assert "поэтапное внедрение" in inserted["texts"][0]
            assert "Alice" in inserted["texts"][0]
            assert "gemma4:31b-cloud" in inserted["texts"][0]
            assert "Текущий состав" in inserted["texts"][0]
        finally:
            repo.close()

    def test_inject_planned_events_adds_system_message_and_marks_fired(self):
        repo = _make_repo()
        broadcasts = []

        async def capture(payload: dict):
            broadcasts.append(payload)

        try:
            room_id = _create_room(repo)
            session = repo.create_session(room_id, "Тема", "suggest")
            round_id = repo.create_round(room_id, session["id"], 3)
            event = repo.create_planned_event(room_id, 3, "Бюджет сокращён на 40%.", session["id"])
            engine = DebateEngine(capture, repo)

            asyncio.run(engine._inject_planned_events(room_id, session["id"], round_id, 3))

            messages = repo.list_session_messages(session["id"], limit=None)
            system_messages = [message for message in messages if message.get("type") == "system_event"]
            assert len(system_messages) == 1
            assert system_messages[0]["content"] == "Бюджет сокращён на 40%."
            assert repo.get_pending_events(room_id, session["id"], 3) == []
            fired_event = repo.get_planned_event(room_id, event["id"])
            assert fired_event["fired"] is True
            assert any(payload.get("type") == "event_injected" for payload in broadcasts)

            context = engine._build_agent_context(room_id, session["id"], round_id, 3)
            assert any(item["author_type"] == "system_event" for item in context["history"])
        finally:
            repo.close()

    def test_seed_prepared_turn_populates_cache_for_next_order(self, monkeypatch):
        repo = _make_repo()
        try:
            room_id = _create_room(repo)
            first = _add_participant(repo, room_id, name="Alice")
            second = _add_participant(repo, room_id, name="Bob", role="analyst", specialty="data-analytics")
            session = repo.create_session(room_id, "Тема", "suggest")
            round_state = RoundState(round_id="round_1", round_number=1, order=[first, second], next_index=0)
            engine = DebateEngine(_broadcast, repo)
            engine._running_room_id = room_id
            engine._running_session_id = session["id"]
            engine._round_state = round_state

            async def fake_prepare(room_id, session_id, round_state, order_index, participant):
                return PreparedTurn(
                    room_id=room_id,
                    session_id=session_id,
                    round_id=round_state.round_id,
                    round_number=round_state.round_number,
                    participant=dict(participant),
                    participant_id=participant["id"],
                    order_index=order_index,
                    context_base={"topic": "Тема"},
                    prepared_rag_context="rag",
                    prepared_memory_context="memory",
                    snapshot_signature=engine._make_turn_snapshot_signature(
                        room_id, session_id, round_state.round_id, round_state.round_number, participant["id"]
                    ),
                    history_anchor_id=None,
                    prepared_at=0.0,
                )

            monkeypatch.setattr(engine, "_prepare_turn", fake_prepare)

            async def run():
                engine._seed_prepared_turn(room_id, session["id"], round_state, 1)
                await engine._prep_tasks[(round_state.round_id, 1)]

            asyncio.run(run())

            prepared = engine._prepared_turns[(round_state.round_id, 1)]
            assert prepared.participant_id == second["id"]
            assert prepared.prepared_rag_context == "rag"
        finally:
            repo.close()

    def test_execute_prepared_turn_uses_latest_committed_history(self, monkeypatch):
        repo = _make_repo()
        try:
            room_id = _create_room(repo)
            first = _add_participant(repo, room_id, name="Alice")
            second = _add_participant(repo, room_id, name="Bob", role="analyst", specialty="data-analytics")
            session = repo.create_session(room_id, "Тема", "suggest")
            round_id = repo.create_round(room_id, session["id"], 1)
            round_state = RoundState(round_id=round_id, round_number=1, order=[first, second], next_index=1)
            engine = DebateEngine(_broadcast, repo)
            engine._running_room_id = room_id
            engine._running_session_id = session["id"]
            engine._round_state = round_state

            async def fake_rag(*_args, **_kwargs):
                return "RAG"

            async def fake_memory(*_args, **_kwargs):
                return "MEM"

            monkeypatch.setattr(engine, "_get_round_rag_context", fake_rag)
            monkeypatch.setattr(engine, "_get_profile_memory_context", fake_memory)
            monkeypatch.setattr(
                engine,
                "_density_profile",
                lambda _room_id: {
                    "countdown": 0.0,
                    "pre_turn_min": 0.0,
                    "pre_turn_max": 0.0,
                    "pre_generation_min": 0.0,
                    "pre_generation_max": 0.0,
                    "between_turn_min": 0.0,
                    "between_turn_max": 0.0,
                },
            )
            async def fake_store_memory(*_args, **_kwargs):
                return None

            monkeypatch.setattr(engine, "_store_profile_memory", fake_store_memory)
            prepared = asyncio.run(engine._prepare_turn(room_id, session["id"], round_state, 1, second))
            _append_agent_message(repo, room_id, session["id"], first, "Свежий аргумент", round_id=round_id)

            captured = {}

            async def fake_generate(self, ctx, on_token=None):
                captured["history"] = ctx["history"]
                captured["rag_context"] = ctx.get("rag_context")
                captured["memory_context"] = ctx.get("memory_context")
                if on_token:
                    await on_token("Ответ")
                return "Ответ"

            monkeypatch.setattr("debate.Agent.generate", fake_generate)
            asyncio.run(engine._execute_prepared_turn(prepared))

            assert any(item["content"] == "Свежий аргумент" for item in captured["history"])
            assert captured["rag_context"] == "RAG"
            assert captured["memory_context"] == "MEM"
        finally:
            repo.close()

    def test_execute_prepared_turn_records_inter_turn_gap_metrics(self, monkeypatch):
        repo = _make_repo()
        try:
            room_id = _create_room(repo)
            first = _add_participant(repo, room_id, name="Alice")
            second = _add_participant(repo, room_id, name="Bob", role="analyst", specialty="data-analytics")
            session = repo.create_session(room_id, "Тема", "suggest")
            round_id = repo.create_round(room_id, session["id"], 1)
            round_state = RoundState(round_id=round_id, round_number=1, order=[first, second], next_index=1)
            engine = DebateEngine(_broadcast, repo)
            engine._running_room_id = room_id
            engine._running_session_id = session["id"]
            engine._round_state = round_state

            async def fake_rag(*_args, **_kwargs):
                return "RAG"

            async def fake_memory(*_args, **_kwargs):
                return "MEM"

            async def fake_store_memory(*_args, **_kwargs):
                return None

            monkeypatch.setattr(engine, "_get_round_rag_context", fake_rag)
            monkeypatch.setattr(engine, "_get_profile_memory_context", fake_memory)
            monkeypatch.setattr(engine, "_store_profile_memory", fake_store_memory)
            monkeypatch.setattr(
                engine,
                "_density_profile",
                lambda _room_id: {
                    "countdown": 0.0,
                    "pre_turn_min": 0.0,
                    "pre_turn_max": 0.0,
                    "pre_generation_min": 0.0,
                    "pre_generation_max": 0.0,
                    "between_turn_min": 0.0,
                    "between_turn_max": 0.0,
                },
            )
            prepared = asyncio.run(engine._prepare_turn(room_id, session["id"], round_state, 1, second))

            async def fake_generate(self, _ctx, on_token=None):
                if on_token:
                    await on_token("Ответ")
                return "Ответ"

            monkeypatch.setattr("debate.Agent.generate", fake_generate)

            async def run():
                engine._last_turn_committed_at = asyncio.get_running_loop().time() - 0.75
                await engine._execute_prepared_turn(prepared)

            asyncio.run(run())

            messages = repo.list_session_messages(session["id"], limit=None)
            agent_messages = [message for message in messages if message.get("type") == "agent_message"]
            assert len(agent_messages) == 1
            assert agent_messages[0]["responseSeconds"] >= 0.1
            assert agent_messages[0]["interTurnGapSeconds"] >= 0.7

            events = repo.list_recent_room_events(room_id, session["id"], limit=10)
            timing_events = [event for event in events if event.get("type") == "turn_timing"]
            assert len(timing_events) == 1
            assert timing_events[0]["payload"]["participantId"] == second["id"]
            assert timing_events[0]["payload"]["round"] == 1
            assert timing_events[0]["payload"]["responseSeconds"] >= 0.1
            assert timing_events[0]["payload"]["interTurnGapSeconds"] >= 0.7
        finally:
            repo.close()

    def test_prepared_turn_invalidates_when_active_roster_changes(self, monkeypatch):
        repo = _make_repo()
        try:
            room_id = _create_room(repo)
            first = _add_participant(repo, room_id, name="Alice")
            second = _add_participant(repo, room_id, name="Bob", role="analyst", specialty="data-analytics")
            session = repo.create_session(room_id, "Тема", "suggest")
            round_state = RoundState(round_id="round_1", round_number=1, order=[first, second], next_index=1)
            engine = DebateEngine(_broadcast, repo)
            engine._running_room_id = room_id
            engine._running_session_id = session["id"]
            engine._round_state = round_state

            async def fake_rag(*_args, **_kwargs):
                return ""

            async def fake_memory(*_args, **_kwargs):
                return ""

            monkeypatch.setattr(engine, "_get_round_rag_context", fake_rag)
            monkeypatch.setattr(engine, "_get_profile_memory_context", fake_memory)
            prepared = asyncio.run(engine._prepare_turn(room_id, session["id"], round_state, 1, second))

            repo.bench_participant(first["id"])

            assert engine._is_prepared_turn_valid(prepared, round_state) is False
        finally:
            repo.close()
