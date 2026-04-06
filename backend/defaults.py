from __future__ import annotations

from copy import deepcopy


DEFAULT_STATS = {
    "insight": 50,
    "focus": 50,
    "depth": 50,
    "cooperation": 50,
    "showmanship": 50,
}


DEFAULT_PROFILES = [
    {
        "id": "strategist",
        "name": "Аркадий",
        "role": "strategist",
        "specialty": "product-manager",
        "emoji": "🦉",
        "mascot": "owl",
    },
    {
        "id": "creative",
        "name": "Искра",
        "role": "creative",
        "specialty": "brand-content",
        "emoji": "🤖",
        "mascot": "robot",
    },
    {
        "id": "critic",
        "name": "Резон",
        "role": "critic",
        "specialty": "lawyer",
        "emoji": "🐱",
        "mascot": "cat",
    },
    {
        "id": "analyst",
        "name": "Логос",
        "role": "analyst",
        "specialty": "economist",
        "emoji": "🦊",
        "mascot": "fox",
    },
    {
        "id": "diplomat",
        "name": "Мирра",
        "role": "diplomat",
        "specialty": "psychologist",
        "emoji": "💎",
        "mascot": "crystal",
    },
]

FAST_OLLAMA_CLOUD_MODELS = [
    "gemini-3-flash-preview:cloud",
    "qwen3.5:cloud",
    "glm-5:cloud",
    "minimax-m2.5:cloud",
]


def pick_preferred_model(provider_name: str, models: list[str]) -> str | None:
    if not models:
        return None

    preferred_by_provider = {
        "anthropic": ["claude-sonnet-4-20250514", "claude-3-5-sonnet-latest", "claude-haiku-3-5-20241022"],
        "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4.1-mini", "o4-mini"],
        "ollama": [
            *FAST_OLLAMA_CLOUD_MODELS,
            "deepseek-r1",
            "deepseek-r1:8b",
            "qwen3:4b",
            "qwen3",
            "gemma3:4b",
            "gemma3",
            "llama3.2",
        ],
    }
    preferred = preferred_by_provider.get(provider_name, [])
    exact_match = next((model for model in preferred if model in models), None)
    if exact_match:
        return exact_match

    if provider_name == "ollama":
        non_embedding = [
            model
            for model in models
            if all(marker not in model.lower() for marker in ("embed", "embedding", "nomic-embed", "bge", "e5"))
        ]
        cloud_first = next((model for model in non_embedding if model.endswith(":cloud")), None)
        if cloud_first:
            return cloud_first
        if non_embedding:
            return non_embedding[0]

    return models[0]


def pick_fast_default_provider(providers: dict) -> tuple[str | None, str | None]:
    ollama_config = providers.get("ollama", {})
    if ollama_config.get("available"):
        model = pick_preferred_model("ollama", ollama_config.get("models", []))
        if model and model.endswith(":cloud"):
            return "ollama", model
    return None, None


def pick_observer_provider(providers: dict) -> tuple[str | None, str | None]:
    fast_provider = pick_fast_default_provider(providers)
    if fast_provider != (None, None):
        return fast_provider

    ranking = ["anthropic", "openai", "ollama"]
    for provider_name in ranking:
        config = providers.get(provider_name, {})
        if not config.get("available"):
            continue

        model = pick_preferred_model(provider_name, config.get("models", []))
        if model:
            return provider_name, model

    return None, None


def build_default_profiles(providers: dict) -> list[dict]:
    fast_provider_name, _ = pick_fast_default_provider(providers)
    if fast_provider_name:
        ranking = [fast_provider_name]
    else:
        ranking = [
            provider_name
            for provider_name in ("anthropic", "openai", "ollama")
            if providers.get(provider_name, {}).get("available")
        ]
    if not ranking:
        ranking = list(providers.keys())

    profiles: list[dict] = []
    for index, template in enumerate(DEFAULT_PROFILES):
        provider_name = ranking[index % len(ranking)] if ranking else "ollama"
        models = providers.get(provider_name, {}).get("models", [])
        profiles.append({
            **deepcopy(template),
            "provider": provider_name,
            "model": pick_preferred_model(provider_name, models) or "",
            "stats": deepcopy(DEFAULT_STATS),
            "strengths": [],
            "weaknesses": [],
            "summary": "",
            "last_note": "Новый герой ещё не прошёл ни одной полной сессии.",
            "is_saved": 1,
            "system_provided": 1,
        })
    return profiles
