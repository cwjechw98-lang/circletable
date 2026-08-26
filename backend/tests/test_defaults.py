"""Unit tests for defaults module."""
from __future__ import annotations

import pytest
from defaults import (
    build_default_profiles,
    pick_preferred_model,
    pick_observer_provider,
    pick_fast_default_provider,
    DEFAULT_STATS,
    DEFAULT_PROFILES,
)


MOCK_PROVIDERS = {
    "ollama": {
        "available": True,
        "models": ["gemma3:4b", "qwen3:4b", "gemini-3-flash-preview:cloud"],
    },
    "openai": {
        "available": True,
        "models": ["gpt-4o", "gpt-4o-mini"],
    },
    "anthropic": {
        "available": False,
        "models": [],
    },
}


class TestPickPreferredModel:
    def test_picks_exact_match(self):
        model = pick_preferred_model("openai", ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"])
        assert model == "gpt-4o"

    def test_picks_cloud_first_for_ollama(self):
        model = pick_preferred_model("ollama", ["some-local", "test:cloud"])
        # cloud models are preferred for ollama if no exact match
        assert model is not None

    def test_skips_embedding_models(self):
        model = pick_preferred_model("ollama", ["nomic-embed-text", "gemma3:4b"])
        assert model == "gemma3:4b"

    def test_empty_models(self):
        model = pick_preferred_model("ollama", [])
        assert model is None

    def test_fallback_to_first(self):
        model = pick_preferred_model("openai", ["unknown-model-xyz"])
        assert model == "unknown-model-xyz"


class TestPickObserverProvider:
    def test_picks_available_provider(self):
        provider, model = pick_observer_provider(MOCK_PROVIDERS)
        assert provider is not None
        assert model is not None

    def test_prefers_fast_cloud(self):
        provider, model = pick_observer_provider(MOCK_PROVIDERS)
        # Should prefer ollama cloud model if available
        assert provider == "ollama"
        assert ":cloud" in model

    def test_all_unavailable(self):
        empty = {
            "ollama": {"available": False, "models": []},
            "openai": {"available": False, "models": []},
            "anthropic": {"available": False, "models": []},
        }
        provider, model = pick_observer_provider(empty)
        assert provider is None
        assert model is None


class TestPickFastDefault:
    def test_picks_cloud_ollama(self):
        provider, model = pick_fast_default_provider(MOCK_PROVIDERS)
        assert provider == "ollama"
        assert model is not None and ":cloud" in model

    def test_no_cloud_available(self):
        providers = {
            "ollama": {"available": True, "models": ["gemma3:4b"]},
        }
        provider, model = pick_fast_default_provider(providers)
        assert provider is None


class TestBuildDefaultProfiles:
    def test_returns_all_defaults(self):
        profiles = build_default_profiles(MOCK_PROVIDERS)
        assert len(profiles) == len(DEFAULT_PROFILES)

    def test_each_profile_has_required_fields(self):
        profiles = build_default_profiles(MOCK_PROVIDERS)
        for p in profiles:
            assert "name" in p
            assert "role" in p
            assert "specialty" in p
            assert "provider" in p
            assert "model" in p
            assert "stats" in p
            for stat in DEFAULT_STATS:
                assert stat in p["stats"]

    def test_assigns_available_providers(self):
        profiles = build_default_profiles(MOCK_PROVIDERS)
        for p in profiles:
            assert p["provider"] in ("ollama", "openai")
            assert p["model"] != ""
