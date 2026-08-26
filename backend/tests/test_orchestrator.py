from __future__ import annotations

import asyncio

import pytest

from artificial_analysis import normalize_model_entry, score_candidates
from model_orchestrator import ModelOrchestrator, ROLE_PROFILE_HINTS


AA_CATALOG = [
    {
        "name": "Titan Ultra",
        "slug": "titan-ultra",
        "model_creator": {"name": "TitanLab"},
        "evaluations": {"artificial_analysis_intelligence_index": 44.0},
        "pricing": {"price_1m_blended_3_to_1": 12.0},
        "median_output_tokens_per_second": 40.0,
        "median_time_to_first_token_seconds": 1.2,
    },
    {
        "name": "Nimbus Flash",
        "slug": "nimbus-flash",
        "model_creator": {"name": "NimbusAI"},
        "evaluations": {"artificial_analysis_intelligence_index": 18.0},
        "pricing": {"price_1m_blended_3_to_1": 0.05},
        "median_output_tokens_per_second": 210.0,
        "median_time_to_first_token_seconds": 0.3,
    },
]


class FakeAAClient:
    def __init__(self):
        self._models = [normalize_model_entry(entry) for entry in AA_CATALOG]
        self.calls = 0

    def is_configured(self):
        return True

    def cached_models(self):
        return self._models

    async def fetch_models(self, *, force_refresh=False):
        self.calls += 1
        return self._models


def _candidates():
    catalog = {entry["slug"]: entry for entry in (normalize_model_entry(item) for item in AA_CATALOG)}
    return [
        {"provider": "custom", "model": "titan-ultra-2025", "aa": catalog["titan-ultra"]},
        {"provider": "custom", "model": "nimbus-flash", "aa": catalog["nimbus-flash"]},
    ]


def test_score_candidates_prefers_intelligence_for_smart_profile():
    ranked = score_candidates([dict(c) for c in _candidates()], "smart")
    assert ranked[0]["model"] == "titan-ultra-2025"
    assert ranked[0]["score"] is not None


def test_score_candidates_prefers_price_and_speed_for_fast_profile():
    ranked = score_candidates([dict(c) for c in _candidates()], "fast")
    assert ranked[0]["model"] == "nimbus-flash"


def test_attach_aa_matches_by_slug_tokens():
    orchestrator = ModelOrchestrator(aa_client=FakeAAClient())
    candidates = [
        {"provider": "custom", "model": "titan-ultra-high", "aa": None},
        {"provider": "custom", "model": "полностью-неизвестная-модель", "aa": None},
    ]
    matched = orchestrator._attach_aa_matches(candidates)
    assert matched[0]["aa"]["slug"] == "titan-ultra"
    assert matched[1]["aa"] is None


def test_recommend_pings_shortlist_and_applies_role_hints():
    orchestrator = ModelOrchestrator(aa_client=FakeAAClient())

    class FakeProvider:
        async def stream_chat(self, model, messages, on_token):
            return "ОК"

    def get_provider_fn(name):
        return FakeProvider()

    providers_payload = {
        "custom": {"available": True, "models": ["titan-ultra-high", "nimbus-flash"]}
    }
    result = asyncio.run(orchestrator.recommend(
        characters=[
            {"name": "Мудрец", "role": "analyst"},
            {"name": "Шут", "role": "comedian"},
        ],
        profile=None,
        providers_payload=providers_payload,
        get_provider_fn=get_provider_fn,
        do_ping=True,
    ))

    assert result["recommendations"][0]["profile"] == ROLE_PROFILE_HINTS["analyst"]
    assert result["recommendations"][1]["profile"] == ROLE_PROFILE_HINTS["comedian"]
    analyst_choice = result["recommendations"][0]["choice"]
    comedian_choice = result["recommendations"][1]["choice"]
    assert analyst_choice["model"] == "titan-ultra-high"
    assert comedian_choice["model"] == "nimbus-flash"
    assert all(choice["ping"]["alive"] for choice in (analyst_choice, comedian_choice))
