from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from http_api.deps import get_runtime
from providers import (
    iter_custom_instances,
    register_custom_provider,
    set_custom_providers,
    unregister_custom_provider,
)
from providers.custom_provider import CustomOpenAIProvider


router = APIRouter()

# Библиотека пресетов в стиле настроек провайдеров DeepSeek Harness:
# готовые карточки + возможность добавить полностью кастомный endpoint.
PROVIDER_PRESETS = [
    {"id": "deepseek", "label": "DeepSeek", "baseUrl": "https://api.deepseek.com/v1", "hint": "Ключ platform.deepseek.com", "docsUrl": "https://api-docs.deepseek.com/"},
    {"id": "openrouter", "label": "OpenRouter", "baseUrl": "https://openrouter.ai/api/v1", "hint": "Сотни моделей одним ключом", "docsUrl": "https://openrouter.ai/docs"},
    {"id": "groq", "label": "Groq", "baseUrl": "https://api.groq.com/openai/v1", "hint": "Очень быстрый инференс", "docsUrl": "https://console.groq.com/docs/openai"},
    {"id": "mistral", "label": "Mistral", "baseUrl": "https://api.mistral.ai/v1", "hint": "Ключ console.mistral.ai", "docsUrl": "https://docs.mistral.ai/"},
    {"id": "together", "label": "Together AI", "baseUrl": "https://api.together.xyz/v1", "hint": "Open-source модели в облаке", "docsUrl": "https://docs.together.ai/"},
    {"id": "xai", "label": "xAI (Grok)", "baseUrl": "https://api.x.ai/v1", "hint": "Модели Grok", "docsUrl": "https://docs.x.ai/"},
    {"id": "gemini-openai", "label": "Google Gemini (OpenAI-совместимый)", "baseUrl": "https://generativelanguage.googleapis.com/v1beta/openai", "hint": "Ключ Google AI Studio", "docsUrl": "https://ai.google.dev/gemini-api/docs/openai"},
    {"id": "fireworks", "label": "Fireworks AI", "baseUrl": "https://api.fireworks.ai/inference/v1", "hint": "Быстрый хостинг open-source", "docsUrl": "https://docs.fireworks.ai/"},
    {"id": "lmstudio-local", "label": "LM Studio (локально)", "baseUrl": "http://localhost:1234/v1", "hint": "Локальный сервер без ключа", "docsUrl": "https://lmstudio.io/docs/local-server"},
]


def _sync_from_repository(repository) -> None:
    set_custom_providers(repository.list_custom_provider_records())


@router.get("/api/custom-providers/presets")
async def list_presets():
    return {"presets": PROVIDER_PRESETS}


@router.get("/api/custom-providers")
async def list_custom_providers(request: Request):
    runtime = get_runtime(request)
    return {"customProviders": runtime.repository.list_custom_providers()}


@router.post("/api/custom-providers")
async def create_custom_provider(request: Request, payload: dict):
    runtime = get_runtime(request)
    name = str(payload.get("name") or "").strip()
    base_url = str(payload.get("baseUrl") or "").strip()
    api_key = str(payload.get("apiKey") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Укажите имя провайдера")
    if not base_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="base_url должен начинаться с http(s)://")

    provider = runtime.repository.create_custom_provider(name, base_url, api_key)
    register_custom_provider(CustomOpenAIProvider(
        provider_id=provider["id"],
        name=provider["name"],
        base_url=provider["baseUrl"],
        api_key=api_key,
    ))
    await runtime.manager.broadcast({"type": "providers_changed"})
    return {"customProvider": provider}


@router.delete("/api/custom-providers/{provider_id}")
async def delete_custom_provider(request: Request, provider_id: str):
    runtime = get_runtime(request)
    removed = runtime.repository.delete_custom_provider(provider_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Провайдер не найден")
    unregister_custom_provider(provider_id)
    await runtime.manager.broadcast({"type": "providers_changed"})
    return {"ok": True}


@router.post("/api/custom-providers/{provider_id}/test")
async def test_custom_provider(request: Request, provider_id: str):
    runtime = get_runtime(request)
    instance = next((p for p in iter_custom_instances() if p.provider_id == provider_id), None)
    if instance is None:
        _sync_from_repository(runtime.repository)
        instance = next((p for p in iter_custom_instances() if p.provider_id == provider_id), None)
    if instance is None:
        raise HTTPException(status_code=404, detail="Провайдер не найден")
    models = await instance.list_models()
    return {
        "ok": bool(models),
        "modelCount": len(models),
        "modelsSample": models[:12],
    }


@router.post("/api/custom-providers/sync")
async def sync_custom_providers(request: Request):
    runtime = get_runtime(request)
    _sync_from_repository(runtime.repository)
    return {"ok": True, "count": len(iter_custom_instances())}
