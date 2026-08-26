"""Профилирование стоимости: оценка и накопление расхода токенов.

Оценка эвристическая (кириллица ~0.55 токена/символ, латиница ~0.28),
зато работает для любого провайдера без обращения к API usage.
"""
from __future__ import annotations

import logging
import uuid

from storage import Repository, utc_now


logger = logging.getLogger(__name__)


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    cyr = sum(1 for ch in text if "а" <= ch.lower() <= "я" or ch.lower() == "ё")
    other = len(text) - cyr
    return max(1, int(cyr * 0.55 + other * 0.28) + 1)


def record_usage(
    repository: Repository,
    *,
    session_id: str | None = None,
    room_id: str | None = None,
    round_number: int | None = None,
    kind: str = "other",
    provider: str | None = None,
    model: str | None = None,
    prompt_text: str = "",
    completion_text: str = "",
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
) -> None:
    """Одна строка расхода. Никогда не ломает основной поток дебатов."""
    try:
        repository.add_token_usage(
            id=uuid.uuid4().hex[:20],
            session_id=session_id,
            room_id=room_id,
            round_number=round_number,
            kind=kind,
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens if prompt_tokens is not None else estimate_tokens(prompt_text),
            completion_tokens=completion_tokens if completion_tokens is not None else estimate_tokens(completion_text),
        )
    except Exception:
        logger.warning("token_usage: не удалось записать расход (%s/%s)", kind, model, exc_info=True)
