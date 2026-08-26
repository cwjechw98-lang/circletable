from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from artificial_analysis import SCORING_PROFILES
from http_api.deps import get_runtime
from model_orchestrator import ModelOrchestrator


router = APIRouter()

orchestrator = ModelOrchestrator()


@router.get("/api/orchestrator/status")
async def orchestrator_status(request: Request):
    runtime = get_runtime(request)
    providers = await runtime.providers_payload()
    return {
        "aaConfigured": orchestrator.aa.is_configured(),
        "catalogSize": len(orchestrator.aa.cached_models() or []),
        "cacheAgeSeconds": orchestrator.aa.cache_age_seconds,
        "lastError": orchestrator.aa.last_error,
        "profiles": list(SCORING_PROFILES.keys()),
        "providers": {
            name: {"available": bool(info.get("available")), "modelCount": len(info.get("models") or [])}
            for name, info in (providers or {}).items()
            if isinstance(info, dict)
        },
    }


@router.get("/api/orchestrator/catalog")
async def orchestrator_catalog(request: Request, profile: str = "balanced", limit: int = 25):
    runtime = get_runtime(request)
    if profile not in SCORING_PROFILES:
        raise HTTPException(status_code=400, detail=f"Неизвестный профиль: {profile}")
    try:
        models = await orchestrator.aa.fetch_models()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Каталог AA недоступен: {exc}")
    candidates = [
        {"provider": "-", "model": entry["name"], "aa": entry}
        for entry in models
    ]
    ranked = score_candidates(candidates, profile)[: max(1, min(limit, 100))]
    return {
        "profile": profile,
        "total": len(models),
        "models": ranked,
    }


@router.post("/api/orchestrator/ping")
async def orchestrator_ping(request: Request, payload: dict):
    runtime = get_runtime(request)
    provider_name = str(payload.get("provider") or "").strip()
    model = str(payload.get("model") or "").strip()
    if not provider_name or not model:
        raise HTTPException(status_code=400, detail="Нужны provider и model")

    def get_provider_fn(name: str):
        from providers import get_provider

        return get_provider(name)

    result = await orchestrator.ping_model(provider_name, model, get_provider_fn)
    return result


@router.post("/api/orchestrator/recommend")
async def orchestrator_recommend(request: Request, payload: dict):
    runtime = get_runtime(request)
    characters = payload.get("characters") or []
    if not isinstance(characters, list) or not characters:
        raise HTTPException(status_code=400, detail="Передайте characters: [{name, role}]")
    providers = await runtime.providers_payload()

    def get_provider_fn(name: str):
        from providers import get_provider

        return get_provider(name)

    try:
        result = await orchestrator.recommend(
            characters=characters,
            profile=payload.get("profile"),
            providers_payload=providers,
            get_provider_fn=get_provider_fn,
            do_ping=bool(payload.get("ping", True)),
            refresh_catalog=bool(payload.get("refreshCatalog", False)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return result
