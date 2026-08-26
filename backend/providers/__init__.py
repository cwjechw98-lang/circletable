from .anthropic_provider import AnthropicProvider
from .custom_provider import CustomOpenAIProvider
from .openai_provider import OpenAIProvider
from .ollama_provider import OllamaProvider

PROVIDERS = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "ollama": OllamaProvider,
}

# Динамические кастомные провайдеры: ключ "custom:<id>" → инстанс.
_CUSTOM_INSTANCES: dict[str, CustomOpenAIProvider] = {}


def set_custom_providers(items: list[dict]):
    """Пересобирает реестр кастомных провайдеров из строк БД."""
    _CUSTOM_INSTANCES.clear()
    for item in items or []:
        provider_id = str(item.get("id") or "").strip()
        if not provider_id:
            continue
        key = f"custom:{provider_id}"
        _CUSTOM_INSTANCES[key] = CustomOpenAIProvider(
            provider_id=provider_id,
            name=item.get("name") or provider_id,
            base_url=item.get("base_url") or item.get("baseUrl") or "",
            api_key=item.get("api_key") or item.get("apiKey") or "",
        )


def register_custom_provider(provider: CustomOpenAIProvider):
    _CUSTOM_INSTANCES[f"custom:{provider.provider_id}"] = provider


def unregister_custom_provider(provider_id: str):
    _CUSTOM_INSTANCES.pop(f"custom:{provider_id}", None)


def iter_custom_instances() -> list[CustomOpenAIProvider]:
    return list(_CUSTOM_INSTANCES.values())


def get_provider(name: str):
    if isinstance(name, str) and name.startswith("custom:"):
        instance = _CUSTOM_INSTANCES.get(name)
        if instance is None:
            raise ValueError(f"Неизвестный кастомный провайдер: {name}")
        return instance
    cls = PROVIDERS.get(name)
    if cls is None:
        raise ValueError(f"Unknown provider: {name}")
    return cls()
