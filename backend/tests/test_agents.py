"""Unit tests for the agents module — emotion detection & Agent prompt building."""
from __future__ import annotations

import asyncio

import pytest
from agents import (
    Agent,
    AgentConfig,
    detect_emotion,
    detect_emotion_scored,
    VALID_EMOTIONS,
    ROLE_DESCRIPTIONS,
    SPECIALTY_DESCRIPTIONS,
)


# ── detect_emotion (keyword) ──────────────────

class TestDetectEmotion:
    def test_happy_keywords(self):
        assert detect_emotion("I absolutely agree, this is excellent!") == "happy"

    def test_happy_russian(self):
        assert detect_emotion("Это отлично, замечательно и прекрасно!") == "happy"

    def test_excited_keywords(self):
        assert detect_emotion("Imagine a breakthrough revolutionary idea!") == "excited"

    def test_excited_russian(self):
        assert detect_emotion("Представьте себе: у меня есть прорывная идея!") == "excited"

    def test_laughing_keywords(self):
        assert detect_emotion("Haha that's hilarious, what a funny joke!") == "laughing"

    def test_laughing_russian(self):
        assert detect_emotion("Ха-ха, это так смешно, какая забавная шутка!") == "laughing"

    def test_nervous_keywords(self):
        assert detect_emotion("I'm worried about the risk and danger here.") == "nervous"

    def test_nervous_russian(self):
        assert detect_emotion("Есть серьёзный риск, тревожные опасения и сомнения.") == "nervous"

    def test_angry_keywords(self):
        assert detect_emotion("That's ridiculous nonsense, completely wrong!") == "angry"

    def test_angry_russian(self):
        assert detect_emotion("Это чушь и бред, совершенно неверно и нелепо!") == "angry"

    def test_neutral_empty(self):
        assert detect_emotion("") == "neutral"

    def test_neutral_no_keywords(self):
        assert detect_emotion("The meeting is at 3pm in room B.") == "neutral"

    def test_returns_valid_emotion(self):
        for text in ["hello", "great", "risk", "nonsense", "haha", "idea", ""]:
            assert detect_emotion(text) in VALID_EMOTIONS


# ── detect_emotion_scored ─────────────────────

class TestDetectEmotionScored:
    def test_returns_tuple(self):
        result = detect_emotion_scored("I agree")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_high_confidence_happy(self):
        emotion, confidence = detect_emotion_scored(
            "I absolutely agree, excellent, wonderful, perfect!"
        )
        assert emotion == "happy"
        assert confidence > 0.3

    def test_zero_confidence_neutral(self):
        emotion, confidence = detect_emotion_scored("plain text with no emotional words")
        assert emotion == "neutral"
        assert confidence == 0.0

    def test_confidence_range(self):
        _, confidence = detect_emotion_scored("Great risk but also an exciting idea")
        assert 0.0 <= confidence <= 1.0


# ── Agent prompt building ─────────────────────

class TestAgentPrompts:
    def _make_agent(self, role="critic", specialty="lawyer"):
        return Agent(AgentConfig(
            id="test_1",
            profile_id="prof_1",
            name="Тест",
            role=role,
            specialty=specialty,
            provider="ollama",
            model="test-model",
        ))

    def test_system_prompt_contains_role(self):
        agent = self._make_agent(role="critic")
        prompt = agent._system_prompt()
        assert "critic" in prompt.lower() or "sharp" in prompt.lower()

    def test_system_prompt_contains_specialty(self):
        agent = self._make_agent(specialty="lawyer")
        prompt = agent._system_prompt()
        assert "legal" in prompt.lower() or "lawyer" in prompt.lower()

    def test_build_messages_first_speaker(self):
        agent = self._make_agent()
        ctx = {"topic": "Тестовая тема", "history": []}
        messages = agent._build_messages(ctx)
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "старт" in messages[1]["content"].lower() or "первым" in messages[1]["content"].lower()

    def test_build_messages_with_history(self):
        agent = self._make_agent()
        ctx = {
            "topic": "AI",
            "history": [
                {"author_type": "agent", "agent_name": "Alice", "role": "critic",
                 "specialty": "lawyer", "content": "AI is risky."},
            ],
        }
        messages = agent._build_messages(ctx)
        assert len(messages) == 2
        user_msg = messages[1]["content"]
        assert "Alice" in user_msg
        assert "AI is risky" in user_msg

    def test_build_messages_renders_system_event(self):
        agent = self._make_agent()
        messages = agent._build_messages({
            "topic": "AI",
            "history": [
                {"type": "system_event", "author_type": "system_event", "content": "Бюджет сокращён на 40%."},
            ],
        })
        assert "⚡ СОБЫТИЕ: Бюджет сокращён на 40%." in messages[1]["content"]

    def test_build_messages_includes_rag_context_from_cache(self, monkeypatch):
        agent = self._make_agent()
        monkeypatch.setattr("agents.query_graph", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("query_graph should not be called")))
        ctx = {
            "topic": "AI",
            "graph_id": "graph_1",
            "rag_context": "Документы говорят, что у проекта есть жёсткие ограничения бюджета.",
            "history": [],
        }
        messages = agent._build_messages(ctx)
        assert "Предметный контекст" in messages[0]["content"]
        assert "ограничения бюджета" in messages[0]["content"]

    def test_build_messages_queries_graph_when_needed(self, monkeypatch):
        agent = self._make_agent()
        captured = {}

        def fake_query_graph(graph_id, query, mode="hybrid", top_k=20):
            captured["graph_id"] = graph_id
            captured["query"] = query
            captured["mode"] = mode
            captured["top_k"] = top_k
            return "Факт из графа."

        monkeypatch.setattr("agents.query_graph", fake_query_graph)
        ctx = {
            "topic": "AI strategy",
            "graph_id": "graph_2",
            "history": [
                {"author_type": "agent", "agent_name": "Alice", "role": "critic", "specialty": "lawyer", "content": "First angle."},
                {"author_type": "agent", "agent_name": "Bob", "role": "analyst", "specialty": "data-analytics", "content": "Second angle."},
                {"author_type": "user", "agent_name": "User", "role": "user", "specialty": "prompt", "content": "Need concrete proof."},
            ],
        }
        messages = agent._build_messages(ctx)
        assert captured["graph_id"] == "graph_2"
        assert "AI strategy" in captured["query"]
        assert "Need concrete proof." in captured["query"]
        assert captured["mode"] == "hybrid"
        assert captured["top_k"] == 20
        assert "Факт из графа." in messages[0]["content"]

    def test_rag_context_is_truncated_to_limit(self):
        agent = self._make_agent()
        long_context = ("A" * 7800) + " Полное предложение." + ("B" * 400)
        truncated = agent._truncate_rag_context(long_context, limit=8000)
        assert len(truncated) <= 8000
        assert truncated.endswith(".")

    def test_build_messages_includes_memory_context(self, monkeypatch):
        agent = self._make_agent()
        calls = {"count": 0}

        def fake_query_graph(graph_id, query, mode="hybrid", top_k=30, **kwargs):
            calls["count"] += 1
            assert graph_id == "memory_graph_1"
            assert "Моё мнение: AI ethics" in query
            assert mode == "hybrid"
            assert top_k == 10
            assert "root_dir" in kwargs
            return "Ранее я поддерживал осторожный поэтапный запуск."

        monkeypatch.setattr("agents.query_graph", fake_query_graph)
        ctx = {
            "topic": "AI ethics",
            "memory_graph_id": "memory_graph_1",
            "history": [
                {"author_type": "agent", "agent_name": "Alice", "role": "critic", "specialty": "lawyer", "content": "We need guardrails."},
            ],
        }
        messages = agent._build_messages(ctx)
        assert calls["count"] == 1
        assert "Твои прошлые рассуждения" in messages[0]["content"]
        assert "осторожный поэтапный запуск" in messages[0]["content"]

    def test_build_messages_respects_prefetched_empty_contexts(self, monkeypatch):
        agent = self._make_agent()
        monkeypatch.setattr(
            "agents.query_graph",
            lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("query_graph should not be called")),
        )
        messages = agent._build_messages({
            "topic": "AI ethics",
            "graph_id": "graph_1",
            "memory_graph_id": "memory_graph_1",
            "rag_context": "",
            "memory_context": "",
            "history": [],
        })
        assert len(messages) == 2

    def test_memory_context_is_truncated_to_limit(self, monkeypatch):
        agent = self._make_agent()
        long_memory = ("M" * 3900) + " Полное воспоминание." + ("N" * 300)
        monkeypatch.setattr("agents.query_graph", lambda *args, **kwargs: long_memory)
        messages = agent._build_messages({
            "topic": "AI ethics",
            "memory_graph_id": "memory_graph_2",
            "history": [],
        })
        prompt = messages[0]["content"]
        start = prompt.index("=== Твои прошлые рассуждения по схожим темам ===")
        end = prompt.index("===\nМожешь развивать прежние идеи или пересматривать позицию.")
        memory_block = prompt[start:end]
        assert len(memory_block) <= 4200
        assert "Полное воспоминание." in memory_block

    def test_memory_query_mentions_current_participants(self, monkeypatch):
        agent = self._make_agent()
        captured = {}

        def fake_query_graph(graph_id, query, mode="hybrid", top_k=30, **kwargs):
            captured["query"] = query
            return "Мы уже спорили с этим составом."

        monkeypatch.setattr("agents.query_graph", fake_query_graph)
        agent._build_messages({
            "topic": "AI ethics",
            "memory_graph_id": "memory_graph_3",
            "observer_provider": "ollama",
            "observer_model": "gemma4:31b-cloud",
            "active_participants": [
                {"name": "Тест"},
                {"name": "Алиса"},
                {"name": "Боб"},
            ],
            "history": [],
        })
        assert "Алиса" in captured["query"]
        assert "Боб" in captured["query"]
        assert "gemma4:31b-cloud" in captured["query"]

    def test_enabled_tools_follow_internet_mode_and_graph(self):
        agent = self._make_agent()

        with_graph = agent._enabled_tools({"graph_id": "graph_1", "internet_mode": "auto"})
        assert set(with_graph.keys()) == {"calculate", "search_knowledge", "web_search"}

        offline = agent._enabled_tools({"graph_id": "graph_1", "internet_mode": "off"})
        assert set(offline.keys()) == {"calculate", "search_knowledge"}

        no_graph = agent._enabled_tools({"internet_mode": "on"})
        assert set(no_graph.keys()) == {"calculate", "web_search"}

    def test_force_russian_detection(self):
        agent = self._make_agent()
        # Mostly cyrillic text should force Russian
        assert agent._should_force_russian(
            "Обсуждаем тему искусственного интеллекта",
            [{"content": "Нейросети развиваются быстро"}],
        ) is True
        # Mostly latin text should not
        assert agent._should_force_russian(
            "Discussing artificial intelligence",
            [{"content": "Neural networks are evolving"}],
        ) is False

    def test_wrap_signal_in_context(self):
        agent = self._make_agent()
        ctx = {"topic": "Тест", "history": [], "wrap_signal": True}
        messages = agent._build_messages(ctx)
        assert "закругл" in messages[1]["content"].lower()

    def test_final_signal_in_context(self):
        agent = self._make_agent()
        ctx = {"topic": "Тест", "history": [], "final_signal": True}
        messages = agent._build_messages(ctx)
        assert "финальн" in messages[1]["content"].lower()

    def test_generate_uses_one_tool_then_streams_final(self, monkeypatch):
        agent = self._make_agent()
        calls = []

        class FakeProvider:
            async def stream_chat(self, model, messages, on_token=None):
                calls.append(messages)
                if len(calls) == 1:
                    return '{"action":"use_tool","tool":"calculate","expression":"2 + 2"}'
                assert "Результат инструмента calculate" in messages[1]["content"]
                if on_token:
                    await on_token("Итого: ")
                    await on_token("4.")
                return "Итого: 4."

        async def fake_execute(tool_name, arguments, ctx):
            assert tool_name == "calculate"
            assert arguments["expression"] == "2 + 2"
            return {"tool": "calculate", "query": "2 + 2", "result": "4", "ok": True, "error": ""}

        monkeypatch.setattr("agents.execute_agent_tool", fake_execute)
        agent._provider = FakeProvider()
        streamed = []
        async def collect(token):
            streamed.append(token)

        result = asyncio.run(agent.generate(
            {
                "topic": "Тест",
                "history": [],
                "tools": {"tools_enabled": True, "available_tools": ["calculate"]},
            },
            on_token=collect,
        ))

        assert result == "Итого: 4."
        assert "".join(streamed) == "Итого: 4."
        assert agent.last_tool_call["tool"] == "calculate"
        assert len(calls) == 2

    def test_generate_without_tools_keeps_single_step_streaming(self):
        agent = self._make_agent()
        calls = []

        class FakeProvider:
            async def stream_chat(self, model, messages, on_token=None):
                calls.append(messages)
                if on_token:
                    await on_token("Ответ")
                return "Ответ"

        agent._provider = FakeProvider()
        streamed = []
        async def collect(token):
            streamed.append(token)

        result = asyncio.run(agent.generate(
            {"topic": "Тест", "history": []},
            on_token=collect,
        ))

        assert result == "Ответ"
        assert streamed == ["Ответ"]
        assert agent.last_tool_call is None
        assert len(calls) == 1

    def test_generate_sanitizes_tool_json_if_model_repeats_tool_call(self, monkeypatch):
        agent = self._make_agent()

        class FakeProvider:
            def __init__(self):
                self.calls = 0

            async def stream_chat(self, model, messages, on_token=None):
                self.calls += 1
                if self.calls == 1:
                    return '{"action":"use_tool","tool":"calculate","expression":"2 + 2"}'
                return '{"action":"use_tool","tool":"calculate","expression":"4 + 4"}'

        async def fake_execute(tool_name, arguments, ctx):
            return {"tool": tool_name, "query": arguments.get("expression") or arguments.get("query") or "", "result": "4", "ok": True, "error": ""}

        monkeypatch.setattr("agents.execute_agent_tool", fake_execute)
        agent._provider = FakeProvider()
        streamed = []

        async def collect(token):
            streamed.append(token)

        result = asyncio.run(agent.generate(
            {
                "topic": "Тест",
                "history": [],
                "tools": {"tools_enabled": True, "available_tools": ["calculate"]},
            },
            on_token=collect,
        ))

        assert result == "4"
        assert "".join(streamed) == "4"


# ── Role / Specialty coverage ─────────────────

class TestDescriptionCoverage:
    def test_all_roles_have_descriptions(self):
        for role in ["strategist", "creative", "critic", "synthesizer", "visionary",
                      "analyst", "provocateur", "diplomat", "pragmatist", "skeptic",
                      "philosopher", "mentor", "investigator", "optimist", "pessimist",
                      "comedian", "showman"]:
            assert role in ROLE_DESCRIPTIONS, f"Missing description for role: {role}"

    def test_all_specialties_have_descriptions(self):
        for spec in ["digital-generalist", "marketing-generalist", "product-marketing",
                      "seo-strategy", "brand-content", "sales-funnels", "pr-comms",
                      "backend-architect", "ai-automation", "data-analytics",
                      "psychologist", "lawyer"]:
            assert spec in SPECIALTY_DESCRIPTIONS, f"Missing description for: {spec}"
