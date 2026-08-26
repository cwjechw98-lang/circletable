from __future__ import annotations

import asyncio

import pytest

from debate import DebateEngine, RoundState, parse_mentions


class FakeStreamProvider:
    def __init__(self, text="Согласен, но с оговоркой про рынок."):
        self.text = text
        self.calls: list[dict] = []

    def is_available(self):
        return True

    async def list_models(self):
        return []

    async def stream_chat(self, model, messages, on_token):
        self.calls.append({"model": model, "messages": messages})
        return self.text


def test_parse_mentions_matches_active_names():
    names = ["Логос", "Шутник", "Аркадий"]
    assert parse_mentions("Полностью за @Логос, а @шутник пусть уточнит", names) == ["Логос", "Шутник"]
    assert parse_mentions("Без обращений, просто мысль.", names) == []
    assert parse_mentions("@Незнакомец прав", names) == []


def _round_state(names):
    return RoundState(
        round_id="r1",
        round_number=1,
        order=[{"id": f"p{i}", "name": name, "provider": "fake", "model": "m"} for i, name in enumerate(names)],
    )


def _bare_engine(repo) -> DebateEngine:
    engine = DebateEngine.__new__(DebateEngine)
    engine.repo = repo

    async def _broadcast(self, payload):
        return payload

    import types

    engine._broadcast = types.MethodType(_broadcast, engine)
    return engine


def test_mention_priority_swaps_next_speaker(tmp_path):
    from storage import Repository

    engine = _bare_engine(Repository(str(tmp_path / "m.db")))
    state = _round_state(["Аня", "Борис", "Вика"])
    state.next_index = 0
    engine._apply_mention_priority(state, ["Вика"])
    assert state.order[0]["name"] == "Вика"
    assert [item["name"] for item in state.order] == ["Вика", "Борис", "Аня"]

    # Уже запланированный следующий упомянут — порядок не трогаем.
    state2 = _round_state(["Аня", "Борис", "Вика"])
    engine._apply_mention_priority(state2, ["Аня"])
    assert state2.order[0]["name"] == "Аня"


def test_reaction_generated_and_stored(monkeypatch, tmp_path):
    from storage import Repository
    from tests.test_cross_dialog import FakeStreamProvider  # self-import guard

    repo = Repository(str(tmp_path / "react.db"))
    monkeypatch.setattr("debate.get_provider", lambda name: FakeStreamProvider())
    monkeypatch.setattr("debate.random.random", lambda: 0.0)

    engine = _bare_engine(repo)
    state = _round_state(["Аня", "Борис", "Вика"])
    state.next_index = 2  # Вика только что говорила; следующая по очереди Аня
    speaker = state.order[2]
    engine._last_message_for_reaction = {
        "speaker": speaker,
        "content": "Предлагаю сфокусироваться на удержании клиентов.",
        "mentions": ["Борис"],
    }

    stored = asyncio.run(engine._maybe_reaction("room1", "sess1", state, speaker))
    assert stored is not None
    assert stored["type"] == "agent_reaction"
    # Упомянутый Борис (вес x3) перебивает чаще, чем предыдущий оратор Вика (x0.15);
    # при нашем раскладе единственные кандидаты кроме Вики — Аня(1.0)/Борис(3.0).
    assert stored["agent_name"] in {"Борис", "Аня"}
    assert stored["replyTo"] == "Вика"
    assert len(stored["content"].split()) <= 26

    messages = repo.list_round_messages("sess1", 1)
    assert any(msg.get("type") == "agent_reaction" for msg in messages)


def test_reaction_disabled_by_setting(monkeypatch, tmp_path):
    from storage import Repository

    repo = Repository(str(tmp_path / "off.db"))
    repo.set_setting("cross_dialog_enabled", "0")
    monkeypatch.setattr("debate.random.random", lambda: 0.0)

    engine = _bare_engine(repo)
    state = _round_state(["Аня", "Борис"])
    speaker = state.order[0]
    engine._last_message_for_reaction = {"speaker": speaker, "content": "текст", "mentions": []}

    stored = asyncio.run(engine._maybe_reaction("room1", "sess1", state, speaker))
    assert stored is None
