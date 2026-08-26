from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from knowledge.lightrag_adapter import insert_text, query_graph


SYSTEM_GRAPH_ROOT = Path(__file__).resolve().parent / "data" / "system_graphs"
GLOBAL_OBSERVER_GRAPH_ID = "observer-global"
GLOBAL_CASTING_GRAPH_ID = "casting-global"


def _slug(value: str | None) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return text or "unknown"


def _trim(value: str | None, limit: int) -> str:
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    clipped = text[:limit].rstrip()
    cut = max(clipped.rfind("."), clipped.rfind("!"), clipped.rfind("?"), clipped.rfind("\n"))
    if cut >= int(limit * 0.6):
        return clipped[:cut + 1].rstrip()
    whitespace = clipped.rfind(" ")
    if whitespace >= int(limit * 0.6):
        return clipped[:whitespace].rstrip()
    return clipped


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        value = (item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _topic_tokens(value: str | None, *, limit: int = 18) -> set[str]:
    tokens = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]{4,}", (value or "").lower())
    return set(_dedupe(tokens[:limit]))


def _merge_blocks(blocks: list[str], limit: int = 3600) -> str:
    merged: list[str] = []
    seen: set[str] = set()
    total = 0
    for block in blocks:
        text = (block or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        chunk = text if not merged else f"\n\n{text}"
        if total + len(chunk) > limit:
            remaining = limit - total
            if remaining > 220:
                merged.append(_trim(text, remaining))
            break
        merged.append(text)
        total += len(chunk)
    return "\n\n".join(merged).strip()


def observer_graph_id(provider: str | None = None, model: str | None = None) -> str:
    if provider and model:
        return f"observer-{_slug(provider)}-{_slug(model)}"
    return GLOBAL_OBSERVER_GRAPH_ID


def casting_graph_id(provider: str | None = None, model: str | None = None) -> str:
    if provider and model:
        return f"casting-{_slug(provider)}-{_slug(model)}"
    return GLOBAL_CASTING_GRAPH_ID


def _safe_query(graph_id: str, query: str, *, top_k: int) -> str:
    if not query.strip():
        return ""
    try:
        result = query_graph(
            graph_id,
            query,
            mode="hybrid",
            top_k=top_k,
            root_dir=SYSTEM_GRAPH_ROOT,
        )
    except Exception:
        return ""
    return (result or "").strip()


def _format_roster(participants: list[dict[str, Any]] | None) -> str:
    lines: list[str] = []
    for participant in participants or []:
        name = participant.get("name") or "Без имени"
        role = participant.get("role") or "participant"
        specialty = participant.get("specialtyLabel") or participant.get("specialty") or "generalist"
        provider = participant.get("provider") or "?"
        model = participant.get("model") or "?"
        profile_id = participant.get("profileId") or participant.get("profile_id") or "?"
        lines.append(
            f"- {name} | profile_id={profile_id} | роль={role} | профиль={specialty} | модель={provider}/{model}"
        )
    return "\n".join(lines) or "- состав не зафиксирован"


def _format_recent_reviews(observer_reviews: list[dict[str, Any]] | None, limit: int = 4) -> str:
    lines: list[str] = []
    for review in (observer_reviews or [])[-limit:]:
        summary = _trim(review.get("summary") or review.get("roundSummary") or "", 220)
        recommendation = review.get("recommendation") or "continue"
        missing = _trim(review.get("missingExpertHint") or "", 120)
        suffix = f" | кого не хватало: {missing}" if missing else ""
        lines.append(
            f"- Раунд {review.get('roundNumber') or '?'}: {summary or 'без краткой сводки'} | рекомендация={recommendation}{suffix}"
        )
    return "\n".join(lines) or "- обзор по раундам отсутствует"


def _participant_model_pairs(participants: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    pairs: list[dict[str, str]] = []
    for participant in participants or []:
        pairs.append(
            {
                "name": participant.get("name") or "Без имени",
                "profileId": participant.get("profileId") or participant.get("profile_id") or "",
                "role": participant.get("role") or "participant",
                "specialty": participant.get("specialtyLabel") or participant.get("specialty") or "generalist",
                "provider": participant.get("provider") or "",
                "model": participant.get("model") or "",
            }
        )
    return pairs


def _roster_hash(participant_pairs: list[dict[str, str]]) -> str:
    payload = "|".join(
        sorted(
            f"{item.get('profileId') or item.get('name')}:{item.get('role')}:{item.get('specialty')}:{item.get('provider')}:{item.get('model')}"
            for item in participant_pairs
        )
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16] if payload else "empty-roster"


def build_session_tags(
    *,
    session: dict[str, Any] | None,
    participants: list[dict[str, Any]] | None,
    review: dict[str, Any] | None,
    observer_reviews: list[dict[str, Any]] | None,
) -> list[str]:
    review_payload = review or {}
    session_payload = session or {}
    progress = review_payload.get("progress") or {}
    novelty = _coerce_int(progress.get("novelty"))
    focus = _coerce_int(progress.get("focus"))
    convergence = _coerce_int(progress.get("convergence"))
    recommendation = (review_payload.get("recommendation") or session_payload.get("status") or "").strip()
    missing_hint = (review_payload.get("missingExpertHint") or "").strip()
    final_reason = (review_payload.get("finalReason") or "").strip()
    rounds = _coerce_int(session_payload.get("lastRoundNumber"))
    count = len(participants or [])

    tags: list[str] = []
    if novelty >= 70:
        tags.append("high_novelty")
    elif novelty and novelty <= 35:
        tags.append("low_novelty")
    if focus >= 70:
        tags.append("high_focus")
    elif focus and focus <= 40:
        tags.append("low_focus")
    if convergence >= 70:
        tags.append("strong_synthesis")
    elif convergence and convergence <= 35:
        tags.append("high_conflict")
    if focus >= 60 and convergence <= 45:
        tags.append("productive_conflict")
    if novelty >= 60 and convergence < 60:
        tags.append("wide_exploration")
    if recommendation in {"suggest_final", "final_round", "complete"}:
        tags.append("ready_to_close")
    if final_reason:
        tags.append("reasoned_finish")
    if missing_hint:
        tags.append("missing_expert")
    if rounds >= 4 or len(observer_reviews or []) >= 4:
        tags.append("long_session")
    if count <= 2:
        tags.append("duo_table")
    elif count >= 5:
        tags.append("large_table")

    for role in sorted({participant.get("role") or "participant" for participant in participants or []})[:5]:
        tags.append(f"role_{_slug(role)}")

    return _dedupe(tags)[:12]


def build_session_insight(
    *,
    room: dict[str, Any] | None,
    session: dict[str, Any] | None,
    participants: list[dict[str, Any]] | None,
    review: dict[str, Any] | None,
    observer_reviews: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    participant_pairs = _participant_model_pairs(participants)
    participant_profile_ids = [
        item["profileId"]
        for item in participant_pairs
        if item.get("profileId")
    ]
    tags = build_session_tags(
        session=session,
        participants=participants,
        review=review,
        observer_reviews=observer_reviews,
    )
    summary_parts = _dedupe(
        [
            _trim((review or {}).get("roundSummary") or "", 240),
            _trim((review or {}).get("tableComment") or "", 240),
            _trim((review or {}).get("finalReason") or "", 220),
        ]
    )
    summary = " ".join(summary_parts).strip()
    if not summary:
        summary = _trim((review or {}).get("chronicle") or (session or {}).get("chronicle") or "", 320)
    if not summary:
        summary = "Сессия завершилась без подробной итоговой сводки."

    missing_hint = _trim((review or {}).get("missingExpertHint") or "", 160)
    if missing_hint:
        casting_outcome = f"Хрономант отмечал нехватку экспертизы: {missing_hint}."
    elif "strong_synthesis" in tags:
        casting_outcome = "Состав сам дошёл до устойчивого синтеза и выглядел самодостаточным."
    elif "productive_conflict" in tags:
        casting_outcome = "Состав держал полезное напряжение и продвигал разговор через конфликт оптик."
    elif "high_conflict" in tags:
        casting_outcome = "Состав спорил жёстко и нуждался в балансирующей или синтезирующей роли."
    else:
        casting_outcome = "Состав дал рабочую, но без яркого кастингового паттерна динамику."

    session_payload = session or {}
    room_payload = room or {}
    return {
        "sessionId": session_payload.get("id") or "",
        "roomId": room_payload.get("id") or "",
        "topic": session_payload.get("topic") or "",
        "observerProvider": session_payload.get("observerProvider") or room_payload.get("observerProvider"),
        "observerModel": session_payload.get("observerModel") or room_payload.get("observerModel"),
        "rosterHash": _roster_hash(participant_pairs),
        "participantProfileIds": participant_profile_ids,
        "participantModelPairs": participant_pairs,
        "tags": tags,
        "summary": summary,
        "castingOutcome": casting_outcome,
        "curatedAt": session_payload.get("endedAt") or session_payload.get("updatedAt") or session_payload.get("createdAt") or "",
    }


def build_observer_memory_entry(
    *,
    room: dict[str, Any] | None,
    session: dict[str, Any] | None,
    participants: list[dict[str, Any]] | None,
    review: dict[str, Any] | None,
    observer_reviews: list[dict[str, Any]] | None,
    insight: dict[str, Any] | None = None,
) -> str:
    room_name = (room or {}).get("name") or "Без комнаты"
    topic = (session or {}).get("topic") or "Без темы"
    observer_provider = (session or {}).get("observerProvider") or (room or {}).get("observerProvider") or "unknown"
    observer_model = (session or {}).get("observerModel") or (room or {}).get("observerModel") or "unknown"
    status = (session or {}).get("status") or "unknown"
    rounds = (session or {}).get("lastRoundNumber") or 0
    chronicle = _trim((review or {}).get("chronicle") or (session or {}).get("chronicle") or "", 1800)
    final_summary = _trim((review or {}).get("roundSummary") or "", 360)
    final_reason = _trim((review or {}).get("finalReason") or "", 220)
    missing_hint = _trim((review or {}).get("missingExpertHint") or "", 180)
    table_comment = _trim((review or {}).get("tableComment") or "", 220)
    recent_reviews = _format_recent_reviews(observer_reviews)
    roster = _format_roster(participants)
    session_insight = insight or build_session_insight(
        room=room,
        session=session,
        participants=participants,
        review=review,
        observer_reviews=observer_reviews,
    )

    lines = [
        "Память Хрономанта о завершённой сессии.",
        f"Комната: {room_name}",
        f"Session ID: {(session or {}).get('id') or '?'}",
        f"Тема: {topic}",
        f"Наблюдатель: {observer_provider}/{observer_model}",
        f"Статус: {status}",
        f"Раундов: {rounds}",
        f"Финальная рекомендация: {(review or {}).get('recommendation') or 'unknown'}",
        f"Финальная сводка: {final_summary or 'нет'}",
        f"Теги куратора памяти: {', '.join(session_insight.get('tags') or []) or 'нет'}",
        f"Куратор памяти о составе: {session_insight.get('castingOutcome') or 'нет'}",
    ]
    if final_reason:
        lines.append(f"Причина финала: {final_reason}")
    if table_comment:
        lines.append(f"Комментарий Хрономанта: {table_comment}")
    if missing_hint:
        lines.append(f"Подсказка по недостающей экспертизе: {missing_hint}")
    if chronicle:
        lines.extend(["Хроника:", chronicle])
    lines.extend(["Состав:", roster, "Краткая история по раундам:", recent_reviews])
    return "\n".join(lines)


def build_casting_memory_entry(
    *,
    room: dict[str, Any] | None,
    session: dict[str, Any] | None,
    participants: list[dict[str, Any]] | None,
    review: dict[str, Any] | None,
    observer_reviews: list[dict[str, Any]] | None,
    insight: dict[str, Any] | None = None,
) -> str:
    topic = (session or {}).get("topic") or "Без темы"
    observer_provider = (session or {}).get("observerProvider") or (room or {}).get("observerProvider") or "unknown"
    observer_model = (session or {}).get("observerModel") or (room or {}).get("observerModel") or "unknown"
    roster = _format_roster(participants)
    chronicle = _trim((review or {}).get("chronicle") or (session or {}).get("chronicle") or "", 1400)
    missing_hint = _trim((review or {}).get("missingExpertHint") or "", 180)
    progress = (review or {}).get("progress") or {}
    recent_reviews = _format_recent_reviews(observer_reviews, limit=3)
    session_insight = insight or build_session_insight(
        room=room,
        session=session,
        participants=participants,
        review=review,
        observer_reviews=observer_reviews,
    )

    lines = [
        "Память кастинг-помощника о том, какие составы уже работали.",
        f"Тема: {topic}",
        f"Связанный наблюдатель: {observer_provider}/{observer_model}",
        f"Итоговая рекомендация по сессии: {(review or {}).get('recommendation') or (session or {}).get('status') or 'unknown'}",
        f"Прогресс: novelty={progress.get('novelty', '?')}, focus={progress.get('focus', '?')}, convergence={progress.get('convergence', '?')}",
        f"Теги куратора памяти: {', '.join(session_insight.get('tags') or []) or 'нет'}",
        f"Вывод куратора памяти: {session_insight.get('castingOutcome') or 'нет'}",
    ]
    if missing_hint:
        lines.append(f"Кого не хватало по ходу беседы: {missing_hint}")
    lines.extend(["Состав команды:", roster])
    if chronicle:
        lines.extend(["Хроника результата:", chronicle])
    lines.extend(["Последние обзоры раундов:", recent_reviews])
    return "\n".join(lines)


def store_session_memories(
    *,
    room: dict[str, Any] | None,
    session: dict[str, Any] | None,
    participants: list[dict[str, Any]] | None,
    review: dict[str, Any] | None,
    observer_reviews: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    session_payload = session or {}
    provider = session_payload.get("observerProvider") or (room or {}).get("observerProvider")
    model = session_payload.get("observerModel") or (room or {}).get("observerModel")
    insight = build_session_insight(
        room=room,
        session=session,
        participants=participants,
        review=review,
        observer_reviews=observer_reviews,
    )

    observer_entry = build_observer_memory_entry(
        room=room,
        session=session,
        participants=participants,
        review=review,
        observer_reviews=observer_reviews,
        insight=insight,
    )
    insert_text(GLOBAL_OBSERVER_GRAPH_ID, [observer_entry], root_dir=SYSTEM_GRAPH_ROOT)
    if provider and model:
        insert_text(observer_graph_id(provider, model), [observer_entry], root_dir=SYSTEM_GRAPH_ROOT)

    casting_entry = build_casting_memory_entry(
        room=room,
        session=session,
        participants=participants,
        review=review,
        observer_reviews=observer_reviews,
        insight=insight,
    )
    insert_text(GLOBAL_CASTING_GRAPH_ID, [casting_entry], root_dir=SYSTEM_GRAPH_ROOT)
    if provider and model:
        insert_text(casting_graph_id(provider, model), [casting_entry], root_dir=SYSTEM_GRAPH_ROOT)
    return insight


def query_observer_memory(
    *,
    topic: str,
    observer_provider: str | None,
    observer_model: str | None,
    participants: list[dict[str, Any]] | None,
    chronicle: str | None = None,
) -> str:
    names = ", ".join(
        participant.get("name") or "без имени"
        for participant in (participants or [])[:6]
    )
    query = ". ".join(
        part
        for part in [
            f"Тема: {topic}".strip(),
            f"Наблюдатель: {observer_provider}/{observer_model}" if observer_provider and observer_model else "",
            f"Участники: {names}" if names else "",
            _trim(chronicle or "", 260),
        ]
        if part
    )
    blocks = [
        _safe_query(observer_graph_id(observer_provider, observer_model), query, top_k=8)
        if observer_provider and observer_model
        else "",
        _safe_query(GLOBAL_OBSERVER_GRAPH_ID, query, top_k=6),
    ]
    return _merge_blocks(blocks, limit=3200)


def query_casting_memory(
    *,
    topic: str,
    helper_provider: str | None,
    helper_model: str | None,
    active_participants: list[dict[str, Any]] | None,
    mode: str,
    missing_expert_hint: str | None = None,
) -> str:
    roster = "; ".join(
        f"{participant.get('name') or 'без имени'}:{participant.get('role') or 'participant'}/{participant.get('specialty') or 'generalist'}"
        for participant in (active_participants or [])[:6]
    )
    query = ". ".join(
        part
        for part in [
            f"Тема: {topic}".strip(),
            f"Режим кастинга: {mode}",
            f"Модель помощника: {helper_provider}/{helper_model}" if helper_provider and helper_model else "",
            f"Текущий состав: {roster}" if roster else "",
            f"Недостающая экспертиза: {missing_expert_hint}" if missing_expert_hint else "",
        ]
        if part
    )
    blocks = [
        _safe_query(casting_graph_id(helper_provider, helper_model), query, top_k=8)
        if helper_provider and helper_model
        else "",
        _safe_query(GLOBAL_CASTING_GRAPH_ID, query, top_k=6),
    ]
    return _merge_blocks(blocks, limit=3200)


def select_relevant_session_insights(
    insights: list[dict[str, Any]] | None,
    *,
    topic: str,
    participants: list[dict[str, Any]] | None = None,
    observer_provider: str | None = None,
    observer_model: str | None = None,
    missing_expert_hint: str | None = None,
    audience: str = "observer",
    limit: int = 3,
) -> list[dict[str, Any]]:
    current_topic_tokens = _topic_tokens(topic)
    hint_tokens = _topic_tokens(missing_expert_hint)
    current_profile_ids = {
        participant.get("profileId") or participant.get("profile_id")
        for participant in (participants or [])
        if participant.get("profileId") or participant.get("profile_id")
    }
    current_roles = {
        participant.get("role") or "participant"
        for participant in (participants or [])
        if participant.get("role")
    }

    scored: list[tuple[int, int, dict[str, Any]]] = []
    for index, insight in enumerate(insights or []):
        score = 0
        tags = set(insight.get("tags") or [])
        insight_profiles = set(insight.get("participantProfileIds") or [])
        insight_roles = {
            tag[5:]
            for tag in tags
            if tag.startswith("role_")
        }
        insight_text_tokens = _topic_tokens(
            " ".join(
                [
                    insight.get("topic") or "",
                    insight.get("summary") or "",
                    insight.get("castingOutcome") or "",
                    " ".join(tags),
                ]
            ),
            limit=32,
        )

        score += len(current_topic_tokens & insight_text_tokens) * 2
        score += len(current_profile_ids & insight_profiles) * 5
        score += len(current_roles & insight_roles) * 2
        if observer_provider and insight.get("observerProvider") == observer_provider:
            score += 1
        if observer_provider and observer_model and insight.get("observerProvider") == observer_provider and insight.get("observerModel") == observer_model:
            score += 3
        if hint_tokens:
            score += len(hint_tokens & insight_text_tokens) * 2
            if "missing_expert" in tags:
                score += 1
        if audience == "observer":
            if "ready_to_close" in tags or "reasoned_finish" in tags:
                score += 1
        else:
            if "strong_synthesis" in tags or "productive_conflict" in tags:
                score += 1
        if score <= 1:
            continue
        scored.append((score, -index, insight))

    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [item[2] for item in scored[:max(1, limit)]]


def format_insight_recall(
    insights: list[dict[str, Any]] | None,
    *,
    audience: str = "observer",
    limit: int = 1600,
) -> str:
    blocks: list[str] = []
    for insight in insights or []:
        roster = ", ".join(
            f"{item.get('name') or 'Без имени'} ({item.get('role') or 'participant'} / {item.get('model') or '?'})"
            for item in (insight.get("participantModelPairs") or [])[:4]
        ) or "состав не указан"
        tags = ", ".join((insight.get("tags") or [])[:6]) or "нет"
        lines = [
            f"Тема: {insight.get('topic') or 'без темы'}",
            f"Состав: {roster}",
            f"Теги: {tags}",
            f"Итог: {insight.get('summary') or 'нет'}",
        ]
        if audience == "casting":
            lines.append(f"Паттерн состава: {insight.get('castingOutcome') or 'нет'}")
        blocks.append("\n".join(lines))
    return _merge_blocks(blocks, limit=limit)
