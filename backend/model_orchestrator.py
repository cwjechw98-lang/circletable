"""Оркестратор подбора моделей для новых персонажей.

Логика:
1. Собираем кандидатов из реально доступных провайдеров (ollama/openai/anthropic/custom).
2. Сопоставляем их с каталогом Artificial Analysis (метрики интеллекта, цены, скорости).
3. Пингуем шорт-лист живых кандидатов крошечным запросом, отсеивая мёртвые модели.
4. Для каждого персонажа выбираем лучшую модель по профилю подбора.
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Any, Awaitable, Callable

from artificial_analysis import ArtificialAnalysisClient, score_candidates

PING_TIMEOUT_SECONDS = 25.0
PING_SHORTLIST_SIZE = 6
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_NOISE_TOKENS = {
    "cloud", "latest", "preview", "instruct", "chat", "b", "it", "pro", "mini",
    "free", "experimental", "stable", "turbo", "new", "v", "v1", "v2", "v3",
}

# Роли персонажей и предпочтительный профиль подбора по умолчанию.
ROLE_PROFILE_HINTS = {
    "analyst": "smart",
    "critic": "smart",
    "philosopher": "smart",
    "investigator": "smart",
    "strategist": "balanced",
    "synthesizer": "balanced",
    "diplomat": "balanced",
    "mentor": "balanced",
    "pragmatist": "cheap",
    "skeptic": "cheap",
    "creative": "fast",
    "comedian": "fast",
    "showman": "fast",
    "provocateur": "fast",
}


def _tokens(value: str) -> set[str]:
    return {token for token in _TOKEN_RE.findall((value or "").lower()) if token not in _NOISE_TOKENS and len(token) > 1}


class ModelOrchestrator:
    def __init__(self, aa_client: ArtificialAnalysisClient | None = None):
        self.aa = aa_client or ArtificialAnalysisClient()

    async def build_candidates(self, providers_payload: dict[str, Any]) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for provider_name, info in (providers_payload or {}).items():
            if not isinstance(info, dict):
                continue
            available = bool(info.get("available"))
            for model in info.get("models") or []:
                candidates.append({
                    "provider": provider_name,
                    "model": str(model),
                    "providerAvailable": available,
                    "aa": None,
                })
        return self._attach_aa_matches(candidates)

    def _attach_aa_matches(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        catalog = self.aa.cached_models()
        if not catalog:
            return candidates
        # Простой индекс по токенам slug.
        token_index: dict[str, list[dict[str, Any]]] = {}
        for entry in catalog:
            for token in _tokens(entry["slug"]) | _tokens(entry["name"].lower()):
                token_index.setdefault(token, []).append(entry)

        for candidate in candidates:
            model_tokens = _tokens(candidate["model"])
            if not model_tokens:
                continue
            best: dict[str, Any] | None = None
            best_overlap = 0
            seen_ids: set[int] = set()
            for token in model_tokens:
                for entry in token_index.get(token, []):
                    entry_id = id(entry)
                    if entry_id in seen_ids:
                        continue
                    seen_ids.add(entry_id)
                    overlap = len(model_tokens & (_tokens(entry["slug"]) | _tokens(entry["name"].lower())))
                    if overlap > best_overlap:
                        best_overlap = overlap
                        best = entry
            if best and best_overlap >= max(1, min(2, len(model_tokens))):
                candidate["aa"] = best
        return candidates

    async def ping_model(
        self,
        provider_name: str,
        model: str,
        get_provider_fn: Callable[[str], Any],
    ) -> dict[str, Any]:
        """Крошечный запрос к модели, чтобы убедиться что она реально отвечает."""
        started = time.perf_counter()
        try:
            provider = get_provider_fn(provider_name)
            await asyncio.wait_for(
                provider.stream_chat(
                    model,
                    [{"role": "user", "content": "Ответь одним словом: ОК"}],
                    None,
                ),
                timeout=PING_TIMEOUT_SECONDS,
            )
            return {
                "provider": provider_name,
                "model": model,
                "alive": True,
                "latencyMs": int((time.perf_counter() - started) * 1000),
            }
        except Exception as exc:  # noqa: BLE001 — пинг не должен рвать поток
            return {
                "provider": provider_name,
                "model": model,
                "alive": False,
                "latencyMs": int((time.perf_counter() - started) * 1000),
                "error": str(exc)[:200],
            }

    async def recommend(
        self,
        *,
        characters: list[dict[str, Any]],
        profile: str | None,
        providers_payload: dict[str, Any],
        get_provider_fn: Callable[[str], Any],
        do_ping: bool = True,
        refresh_catalog: bool = False,
    ) -> dict[str, Any]:
        if not characters:
            raise ValueError("Список персонажей пуст")
        try:
            await self.aa.fetch_models(force_refresh=refresh_catalog)
        except Exception as exc:  # noqa: BLE001 — без каталога работаем на локальных данных
            catalog_error = str(exc)[:200]
        else:
            catalog_error = None

        candidates = await self.build_candidates(providers_payload)

        recommendations: list[dict[str, Any]] = []
        for character in characters:
            role = str(character.get("role") or "").strip()
            effective_profile = profile or ROLE_PROFILE_HINTS.get(role) or "balanced"
            ranked = score_candidates(
                [dict(candidate) for candidate in candidates],
                effective_profile,
            )
            shortlist = [c for c in ranked[:PING_SHORTLIST_SIZE] if c.get("providerAvailable")]
            alive_map: dict[tuple[str, str], dict[str, Any]] = {}
            if do_ping and shortlist:
                pings = await asyncio.gather(*[
                    self.ping_model(c["provider"], c["model"], get_provider_fn)
                    for c in shortlist
                ])
                alive_map = {(p["provider"], p["model"]): p for p in pings}
            chosen: dict[str, Any] | None = None
            alternatives: list[dict[str, Any]] = []
            for candidate in shortlist:
                ping = alive_map.get((candidate["provider"], candidate["model"]))
                entry = {
                    "provider": candidate["provider"],
                    "model": candidate["model"],
                    "score": candidate.get("score"),
                    "aa": candidate.get("aa"),
                    "ping": ping or {"alive": True, "skipped": True},
                }
                if chosen is None and (not alive_map or (ping and ping.get("alive"))):
                    chosen = entry
                elif len(alternatives) < 4:
                    alternatives.append(entry)
            if chosen is None and shortlist:
                fallback = shortlist[0]
                chosen = {
                    "provider": fallback["provider"],
                    "model": fallback["model"],
                    "score": fallback.get("score"),
                    "aa": fallback.get("aa"),
                    "ping": alive_map.get((fallback["provider"], fallback["model"]))
                    or {"alive": True, "skipped": True},
                }
            recommendations.append({
                "character": {"name": character.get("name"), "role": role},
                "profile": effective_profile,
                "choice": chosen,
                "alternatives": alternatives,
            })

        return {
            "recommendations": recommendations,
            "catalogError": catalog_error,
            "catalogSize": len(self.aa.cached_models() or []),
            "pingEnabled": bool(do_ping),
        }
