from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request

from http_api.deps import get_runtime
from knowledge.lightrag_adapter import get_memory_llm_config, set_memory_llm_config


router = APIRouter()

# Разрешённые ключи настроек (UI-editable). Значения хранятся строками в app_settings.
SETTING_KEYS = {
    "memory_llm_base_url": str,
    "memory_llm_model": str,
    "memory_llm_api_key": str,
    "default_agent_provider": str,
    "default_agent_model": str,
    "cross_dialog_enabled": str,
    "reaction_chance": str,
}
SECRET_KEYS = {"memory_llm_api_key"}


def _apply_settings_overrides(repository) -> None:
    """Применить сохранённые настройки к рантайму (память)."""
    settings = repository.all_settings()
    set_memory_llm_config(
        base_url=settings.get("memory_llm_base_url"),
        model=settings.get("memory_llm_model"),
        api_key=settings.get("memory_llm_api_key"),
    )


@router.get("/api/settings")
async def get_settings(request: Request):
    runtime = get_runtime(request)
    stored = runtime.repository.all_settings()
    memory_config = get_memory_llm_config()
    result = {}
    for key in SETTING_KEYS:
        value = stored.get(key)
        if key == "memory_llm_base_url" and not value:
            value = memory_config["base_url"]
        if key == "memory_llm_model" and not value:
            value = memory_config["model"]
        if key in SECRET_KEYS and value:
            value = f"...{value[-4:]}" if len(value) > 4 else "***"
        result[key] = value or ""
    return {"settings": result}


@router.put("/api/settings")
async def update_settings(request: Request, payload: dict):
    runtime = get_runtime(request)
    updates = payload.get("settings") or {}
    unknown = [key for key in updates if key not in SETTING_KEYS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Неизвестные настройки: {', '.join(unknown)}")

    clean: dict[str, str] = {}
    for key, value in updates.items():
        text = "" if value is None else str(value).strip()
        if key == "reaction_chance" and text != "":
            try:
                text = str(max(0.0, min(float(text), 1.0)))
            except ValueError:
                raise HTTPException(status_code=400, detail="reaction_chance должен быть числом 0..1")
        # Пустой секрет = «не менять», чтобы UI не затирал ключ пустотой.
        if key in SECRET_KEYS and (text == "" or text.startswith("...") or text == "***"):
            continue
        clean[key] = text

    for key, value in clean.items():
        runtime.repository.set_setting(key, value)
    _apply_settings_overrides(runtime.repository)
    await runtime.manager.broadcast({"type": "settings_updated"})
    return {"ok": True, "saved": sorted(clean.keys()), "maskedKeys": sorted(SECRET_KEYS)}


@router.post("/api/settings/test-memory-llm")
async def test_memory_llm(request: Request):
    config = get_memory_llm_config()
    headers = {"Content-Type": "application/json"}
    if config["api_key"]:
        headers["Authorization"] = f"Bearer {config['api_key']}"
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{config['base_url']}/chat/completions",
                json={
                    "model": config["model"],
                    "messages": [{"role": "user", "content": "Ответь одним словом: ОК"}],
                    "stream": False,
                    # reasoning-модели тратят бюджет на размышления — даём запас
                    "max_tokens": 400,
                },
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        usage = data.get("usage") or {}
        return {
            "ok": True,
            "baseUrl": config["base_url"],
            "model": config["model"],
            "sample": (content or "").strip()[:60],
            "usage": {
                "promptTokens": usage.get("prompt_tokens"),
                "completionTokens": usage.get("completion_tokens"),
                "cost": usage.get("cost"),
            },
        }
    except Exception as exc:  # noqa: BLE001 - ошибку отдаём пользователю в UI
        raise HTTPException(status_code=502, detail=f"LLM памяти недоступна: {exc}")


@router.get("/api/stats/tokens/{session_id}")
async def token_usage_stats(request: Request, session_id: str):
    runtime = get_runtime(request)
    return runtime.repository.token_usage_summary(session_id)
