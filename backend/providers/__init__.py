from .anthropic_provider import AnthropicProvider
from .openai_provider import OpenAIProvider
from .ollama_provider import OllamaProvider

PROVIDERS = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "ollama": OllamaProvider,
}


def get_provider(name: str):
    cls = PROVIDERS.get(name)
    if cls is None:
        raise ValueError(f"Unknown provider: {name}")
    return cls()
