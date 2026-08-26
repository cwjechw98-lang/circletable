"""Tests for casting assistant model assignment."""
from __future__ import annotations

import asyncio
import httpx

import casting
from casting import _assign_character_models, suggest_characters


def test_assign_character_models_prefers_diverse_models_when_available():
    characters = [
        {"name": "А", "role": "strategist", "specialty": "product-manager"},
        {"name": "Б", "role": "critic", "specialty": "lawyer"},
        {"name": "В", "role": "creative", "specialty": "brand-content"},
    ]
    providers_payload = {
        "ollama": {
            "available": True,
            "models": [
                "gemma4:31b-cloud",
                "deepseek-r1:70b",
                "gemini-3-flash-preview:cloud",
            ],
        }
    }

    assigned = _assign_character_models(
        characters,
        providers_payload,
        helper_provider="ollama",
        helper_model="gemma4:31b-cloud",
        topic="Проверка распределения моделей",
    )

    models = [item["model"] for item in assigned]
    assert len(set(models)) == len(models)


def test_assign_character_models_falls_back_to_single_available_model():
    characters = [
        {"name": "А", "role": "strategist", "specialty": "product-manager"},
        {"name": "Б", "role": "critic", "specialty": "lawyer"},
    ]
    providers_payload = {
        "ollama": {
            "available": True,
            "models": ["gemma4:31b-cloud"],
        }
    }

    assigned = _assign_character_models(
        characters,
        providers_payload,
        helper_provider="ollama",
        helper_model="gemma4:31b-cloud",
        topic="Проверка одиночной модели",
    )

    assert all(item["provider"] == "ollama" for item in assigned)
    assert all(item["model"] == "gemma4:31b-cloud" for item in assigned)


def test_suggest_characters_includes_historical_memory_in_prompt(monkeypatch):
    captured = {}

    class FakeProvider:
        async def stream_chat(self, model, messages, on_token=None):
            captured["prompt"] = messages[1]["content"]
            return (
                '{"characters":['
                '{"name":"Вектор","role":"strategist","specialty":"product-manager","mascot":"owl","summary":"стратег"},'
                '{"name":"Искра","role":"creative","specialty":"brand-content","mascot":"robot","summary":"креатив"}'
                ']}'
            )

    monkeypatch.setattr(casting, "query_casting_memory", lambda **kwargs: "Раньше похожий состав хорошо работал на конфликте критика и стратега.")
    monkeypatch.setitem(casting.PROVIDERS, "ollama", lambda: FakeProvider())

    result = asyncio.run(
        suggest_characters(
            topic="Как обсуждать спорные гипотезы",
            count=2,
            providers_payload={"ollama": {"available": True, "models": ["gemma4:31b-cloud"]}},
            mode="gap_fill",
            provider_name="ollama",
            model="gemma4:31b-cloud",
            active_participants=[{"name": "Логос", "role": "analyst", "specialty": "data-analytics"}],
            missing_expert_hint="Нужен сильный скептик",
            curated_recall="Куратор памяти: составы с сильным критиком и аналитиком часто дают полезный конфликт.",
        )
    )

    assert result["source"] == "model"
    assert "Куратор памяти о прошлых удачных и неудачных составах" in captured["prompt"]
    assert "полезный конфликт" in captured["prompt"]
    assert "Память помощника о похожих прошлых сессиях" in captured["prompt"]
    assert "хорошо работал на конфликте" in captured["prompt"]


def test_suggest_characters_drops_low_priority_context_before_fresh_round_context(monkeypatch):
    prompts = []

    class FlakyProvider:
        async def stream_chat(self, model, messages, on_token=None):
            prompt = messages[1]["content"]
            prompts.append(prompt)
            if len(prompts) < 5:
                request = httpx.Request("POST", "https://example.test/casting")
                response = httpx.Response(400, request=request)
                raise httpx.HTTPStatusError("prompt rejected", request=request, response=response)
            return (
                '{"characters":['
                '{"name":"Вектор","role":"strategist","specialty":"product-manager","mascot":"owl","summary":"стратег"},'
                '{"name":"Резон","role":"critic","specialty":"lawyer","mascot":"cat","summary":"критик"}'
                ']}'
            )

    monkeypatch.setattr(casting, "query_casting_memory", lambda **kwargs: "Память о составе, которую уберём в компактном ретрае.")
    monkeypatch.setitem(casting.PROVIDERS, "ollama", lambda: FlakyProvider())

    result = asyncio.run(
        suggest_characters(
            topic="Как улучшить обсуждение после спорного раунда",
            count=2,
            providers_payload={"ollama": {"available": True, "models": ["gemma4:31b-cloud"]}},
            mode="gap_fill",
            provider_name="ollama",
            model="gemma4:31b-cloud",
            room_summary=("Длинная память комнаты с множеством деталей. " * 40).strip(),
            session_chronicle=("Хроника сессии стала длинной и именно она провоцирует отказ провайдера. " * 40).strip(),
            latest_round_summary=("В последнем раунде участники зациклились и нужен новый голос. " * 20).strip(),
            active_participants=[{"name": "Логос", "role": "analyst", "specialty": "data-analytics"}],
            missing_expert_hint="Нужен критик, который соберёт противоречия.",
            curated_recall=("Куратор памяти тоже даёт длинную подсказку, которую можно убрать раньше комнаты. " * 35).strip(),
        )
    )

    assert result["source"] == "model"
    assert len(prompts) == 5
    assert "Хроника этой сессии" in prompts[0]
    assert "Память помощника о похожих прошлых сессиях" in prompts[0]
    assert "Память помощника о похожих прошлых сессиях" not in prompts[1]
    assert "Куратор памяти о прошлых удачных и неудачных составах" in prompts[1]
    assert "Куратор памяти о прошлых удачных и неудачных составах" not in prompts[2]
    assert "Память комнаты" in prompts[2]
    assert "Память комнаты" not in prompts[3]
    assert "Хроника этой сессии" in prompts[3]
    assert "Хроника этой сессии" not in prompts[4]
    assert "Сводка последнего раунда" in prompts[4]
    assert len(prompts[1]) < len(prompts[0])
    assert len(prompts[2]) <= len(prompts[1])
    assert len(prompts[3]) < len(prompts[2])
    assert len(prompts[4]) < len(prompts[3])


def test_suggest_characters_fallback_keeps_requested_team_size(monkeypatch):
    class AlwaysFailProvider:
        async def stream_chat(self, model, messages, on_token=None):
            request = httpx.Request("POST", "https://example.test/casting")
            response = httpx.Response(400, request=request)
            raise httpx.HTTPStatusError("prompt rejected", request=request, response=response)

    monkeypatch.setattr(casting, "query_casting_memory", lambda **kwargs: "")
    monkeypatch.setitem(casting.PROVIDERS, "ollama", lambda: AlwaysFailProvider())

    result = asyncio.run(
        suggest_characters(
            topic="Тест fallback на восемь участников",
            count=8,
            providers_payload={"ollama": {"available": True, "models": ["gemma4:31b-cloud"]}},
            mode="full",
            provider_name="ollama",
            model="gemma4:31b-cloud",
            latest_round_summary=("Свежий раунд. " * 20).strip(),
            session_chronicle=("Длинная хроника. " * 40).strip(),
            room_summary=("Память комнаты. " * 30).strip(),
            active_participants=[{"name": "Логос", "role": "analyst", "specialty": "data-analytics"}],
            curated_recall=("Куратор памяти. " * 25).strip(),
        )
    )

    assert result["source"] == "fallback"
    assert len(result["characters"]) == 8


def test_suggest_characters_gap_fill_fallback_prioritizes_missing_critic(monkeypatch):
    monkeypatch.setattr(casting, "query_casting_memory", lambda **kwargs: "")

    result = asyncio.run(
        suggest_characters(
            topic="Как продвигать новый EdTech продукт",
            count=2,
            providers_payload={},
            mode="gap_fill",
            active_participants=[
                {"name": "Искра", "role": "creative", "specialty": "brand-content"},
                {"name": "Пульс", "role": "pragmatist", "specialty": "sales-funnels"},
                {"name": "Логос", "role": "analyst", "specialty": "data-analytics"},
            ],
            missing_expert_hint="Нужен сильный критик, который увидит риски и слепые зоны.",
            latest_round_summary="Последний раунд перекосился в идеи роста и почти не трогал риски.",
        )
    )

    assert result["source"] == "fallback"
    assert result["characters"][0]["role"] == "critic"
    returned_specialties = {item["specialty"] for item in result["characters"]}
    assert "brand-content" not in returned_specialties
    assert "sales-funnels" not in returned_specialties
    assert "data-analytics" not in returned_specialties
