"""Клиент Artificial Analysis Data API.

Используется оркестратором подбора моделей для новых персонажей.
Ключ читается из переменной окружения AA_API_KEY (обычно backend/.env,
который не попадает в git).
"""
from __future__ import annotations

import os
import time
from typing import Any

import httpx

AA_MODELS_URL = "https://artificialanalysis.ai/api/v2/data/llms/models"
CACHE_TTL_SECONDS = 12 * 3600

# Профили подбора: как важны интеллект / скорость / цена.
SCORING_PROFILES = {
    "smart": {"intelligence": 0.70, "speed": 0.10, "price": 0.20},
    "fast": {"intelligence": 0.25, "speed": 0.55, "price": 0.20},
    "cheap": {"intelligence": 0.30, "speed": 0.10, "price": 0.60},
    "balanced": {"intelligence": 0.50, "speed": 0.25, "price": 0.25},
}


def get_api_key() -> str:
    return (os.environ.get("AA_API_KEY") or "").strip()


def is_configured() -> bool:
    return bool(get_api_key())


def normalize_model_entry(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Приводит запись AA к плоской структуре для оркестратора и UI."""
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or raw.get("slug") or "").strip()
    if not name:
        return None
    evaluations = raw.get("evaluations") or {}
    pricing = raw.get("pricing") or {}
    creator = (raw.get("model_creator") or {}).get("name", "")
    return {
        "slug": str(raw.get("slug") or ""),
        "name": name,
        "creator": creator,
        "releaseDate": raw.get("release_date"),
        "intelligenceIndex": _as_float(evaluations.get("artificial_analysis_intelligence_index")),
        "codingIndex": _as_float(evaluations.get("artificial_analysis_coding_index")),
        "mathIndex": _as_float(evaluations.get("artificial_analysis_math_index")),
        "blendedPricePer1m": _as_float(pricing.get("price_1m_blended_3_to_1")),
        "inputPricePer1m": _as_float(pricing.get("price_1m_input_tokens")),
        "outputPricePer1m": _as_float(pricing.get("price_1m_output_tokens")),
        "outputTokensPerSecond": _as_float(raw.get("median_output_tokens_per_second")),
        "timeToFirstTokenSeconds": _as_float(raw.get("median_time_to_first_token_seconds")),
    }


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


class ArtificialAnalysisClient:
    """Тонкий клиент с TTL-кэшем каталога моделей."""

    def __init__(self, ttl_seconds: int = CACHE_TTL_SECONDS):
        self._ttl = ttl_seconds
        self._cache: list[dict[str, Any]] | None = None
        self._cached_at: float = 0.0
        self._last_error: str | None = None

    def is_configured(self) -> bool:
        return is_configured()

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def cache_age_seconds(self) -> float | None:
        if not self._cached_at:
            return None
        return round(time.time() - self._cached_at, 1)

    async def fetch_models(self, *, force_refresh: bool = False) -> list[dict[str, Any]]:
        api_key = get_api_key()
        if not api_key:
            raise RuntimeError("AA_API_KEY не задан")
        if (
            not force_refresh
            and self._cache is not None
            and time.time() - self._cached_at < self._ttl
        ):
            return self._cache

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(
                AA_MODELS_URL,
                headers={"X-API-Key": api_key},
            )
            if resp.status_code != 200:
                self._last_error = f"AA API вернул {resp.status_code}"
                raise RuntimeError(self._last_error)
            payload = resp.json()

        items = payload.get("data", payload) if isinstance(payload, dict) else payload
        normalized: list[dict[str, Any]] = []
        for raw in items or []:
            entry = normalize_model_entry(raw)
            if entry:
                normalized.append(entry)
        self._cache = normalized
        self._cached_at = time.time()
        self._last_error = None
        return normalized

    def cached_models(self) -> list[dict[str, Any]] | None:
        return self._cache


def score_candidates(
    candidates: list[dict[str, Any]],
    profile: str = "balanced",
) -> list[dict[str, Any]]:
    """Присваивает каждой кандидат-модели score по выбранному профилю.

    Кандидат: {provider, model, aa?: {...метрики...}}. Модели без данных AA
    получают score=None и уходят в конец списка.
    """
    weights = SCORING_PROFILES.get(profile, SCORING_PROFILES["balanced"])
    known = [c for c in candidates if c.get("aa")]
    unknown = [c for c in candidates if not c.get("aa")]

    if known:
        intel_vals = [c["aa"]["intelligenceIndex"] for c in known]
        speed_vals = [c["aa"]["outputTokensPerSecond"] or 0.0 for c in known]
        price_vals = [c["aa"]["blendedPricePer1m"] for c in known]
        intel_range = _range(intel_vals)
        speed_range = _range(speed_vals)
        price_range = _range(price_vals)

        for candidate in known:
            aa = candidate["aa"]
            intel_score = _norm(aa["intelligenceIndex"], intel_range)
            speed_score = _norm(aa["outputTokensPerSecond"] or 0.0, speed_range)
            price_score = 1.0 - _norm(_first_not_none(aa["blendedPricePer1m"], 0.0), price_range)
            candidate["scoreParts"] = {
                "intelligence": round(intel_score, 3),
                "speed": round(speed_score, 3),
                "price": round(price_score, 3),
            }
            candidate["score"] = round(
                weights["intelligence"] * intel_score
                + weights["speed"] * speed_score
                + weights["price"] * price_score,
                4,
            )

    for candidate in unknown:
        candidate["score"] = None
        candidate["scoreParts"] = None

    known.sort(key=lambda c: c.get("score") or 0.0, reverse=True)
    return known + unknown


def _range(values: list[float | None]) -> tuple[float, float]:
    clean = [float(v) for v in values if v is not None]
    if not clean:
        return (0.0, 0.0)
    return (min(clean), max(clean))


def _norm(value: float | None, bounds: tuple[float, float]) -> float:
    low, high = bounds
    if value is None:
        return 0.0
    if high - low < 1e-9:
        return 1.0
    return max(0.0, min(1.0, (value - low) / (high - low)))


def _first_not_none(*values):
    for value in values:
        if value is not None:
            return value
    return None
