from __future__ import annotations

import asyncio
import hashlib
import json
import re
from typing import Any

import httpx

from agents import ROLE_DESCRIPTIONS
from defaults import DEFAULT_STATS, pick_observer_provider
from meta_memory import query_casting_memory
from providers import PROVIDERS


ROLE_LABELS = {
    "strategist": "Стратег",
    "creative": "Изобретатель",
    "critic": "Критик",
    "synthesizer": "Синтезатор",
    "visionary": "Визионер",
    "analyst": "Аналитик",
    "provocateur": "Провокатор",
    "diplomat": "Дипломат",
    "pragmatist": "Прагматик",
    "skeptic": "Скептик",
    "philosopher": "Философ",
    "mentor": "Наставник",
    "investigator": "Расследователь",
    "optimist": "Оптимист",
    "pessimist": "Пессимист",
    "comedian": "Комик",
    "showman": "Шоумен",
}

SPECIALTY_LABELS = {
    "digital-generalist": "Универсальный эксперт по цифровому бизнесу",
    "marketing-generalist": "Маркетолог-универсал",
    "product-marketing": "Продуктовый маркетолог",
    "seo-strategy": "SEO и органический рост",
    "brand-content": "Бренд, контент и копирайтинг",
    "sales-funnels": "Продажи и воронки",
    "pr-comms": "PR и внешние коммуникации",
    "business-dev": "Бизнес-девелопмент и партнёрства",
    "product-manager": "Продуктовый менеджмент",
    "ux-research": "UX, интерфейсы и исследование пользователей",
    "frontend-engineer": "Фронтенд и клиентский UX",
    "backend-architect": "Бэкенд и архитектура систем",
    "ai-automation": "AI, автоматизация и агентные системы",
    "data-analytics": "Аналитика данных и метрики",
    "cybersecurity": "Кибербезопасность и технические риски",
    "fintech-systems": "Финтех и платёжные системы",
    "economist": "Экономика и макротренды",
    "finance-strategy": "Финансы, unit-экономика и бюджеты",
    "investor": "Инвестиционный анализ",
    "lawyer": "Юридическая экспертиза",
    "compliance-risk": "Комплаенс и регуляторные риски",
    "ops-manager": "Операционный менеджмент",
    "hr-people": "HR, найм и оргдизайн",
    "psychologist": "Психология и поведение людей",
    "coach-facilitator": "Коучинг и фасилитация",
    "customer-success": "Клиентский сервис и удержание",
    "producer": "Продюсирование и запуск проектов",
    "storyteller": "Сторителлинг и сценарное мышление",
    "creator-blogger": "Блогинг и личный бренд",
    "community-smm": "SMM и комьюнити",
    "design-creative": "Креативный директор и дизайн-мышление",
    "philosophy": "Философия и смысловые конструкции",
    "sports-coach": "Спортивный тренер и дисциплина",
    "infobiz": "Инфобизнес и упаковка экспертизы",
    "standup": "Стендап и комедийная подача",
    "mystic": "Гадалка-мистификатор",
}

MASCOT_DEFS = {
    "owl": "🦉",
    "robot": "🤖",
    "cat": "🐱",
    "llama": "🦙",
    "dragon": "🐲",
    "wizard": "🧙",
    "ghost": "👻",
    "crystal": "💎",
    "fox": "🦊",
    "panda": "🐼",
    "wolf": "🐺",
    "tiger": "🐯",
    "frog": "🐸",
    "octopus": "🐙",
    "alien": "👽",
    "bat": "🦇",
    "bee": "🐝",
    "eagle": "🦅",
    "unicorn": "🦄",
    "raccoon": "🦝",
}

FALLBACK_POOL = [
    {"name": "Вектор", "role": "strategist", "specialty": "product-manager", "mascot": "owl"},
    {"name": "Искра", "role": "creative", "specialty": "brand-content", "mascot": "robot"},
    {"name": "Резон", "role": "critic", "specialty": "lawyer", "mascot": "cat"},
    {"name": "Логос", "role": "analyst", "specialty": "data-analytics", "mascot": "fox"},
    {"name": "Мирра", "role": "diplomat", "specialty": "psychologist", "mascot": "crystal"},
    {"name": "Пульс", "role": "pragmatist", "specialty": "ops-manager", "mascot": "panda"},
    {"name": "Гипотеза", "role": "investigator", "specialty": "ux-research", "mascot": "ghost"},
    {"name": "Факел", "role": "showman", "specialty": "creator-blogger", "mascot": "dragon"},
    {"name": "Зефир", "role": "optimist", "specialty": "community-smm", "mascot": "unicorn"},
    {"name": "Омут", "role": "skeptic", "specialty": "cybersecurity", "mascot": "bat"},
    {"name": "Шторм", "role": "provocateur", "specialty": "business-dev", "mascot": "tiger"},
    {"name": "Рой", "role": "synthesizer", "specialty": "ai-automation", "mascot": "bee"},
]

KEYWORD_POOL = [
    (("маркет", "smm", "контент", "бренд", "продвиж"), [
        {"name": "Охват", "role": "creative", "specialty": "marketing-generalist", "mascot": "robot"},
        {"name": "Клик", "role": "pragmatist", "specialty": "sales-funnels", "mascot": "fox"},
        {"name": "Голос", "role": "showman", "specialty": "brand-content", "mascot": "unicorn"},
    ]),
    (("код", "сайт", "прилож", "интерфейс", "backend", "frontend", "ии", "ai"), [
        {"name": "Контур", "role": "analyst", "specialty": "backend-architect", "mascot": "owl"},
        {"name": "Пиксель", "role": "creative", "specialty": "frontend-engineer", "mascot": "frog"},
        {"name": "Оркестр", "role": "strategist", "specialty": "ai-automation", "mascot": "wizard"},
    ]),
    (("деньги", "финанс", "инвест", "бюджет", "эконом"), [
        {"name": "Маржа", "role": "analyst", "specialty": "finance-strategy", "mascot": "fox"},
        {"name": "Баланс", "role": "skeptic", "specialty": "economist", "mascot": "panda"},
        {"name": "Капитал", "role": "visionary", "specialty": "investor", "mascot": "eagle"},
    ]),
    (("прав", "договор", "риск", "регул", "закон"), [
        {"name": "Пункт", "role": "critic", "specialty": "lawyer", "mascot": "cat"},
        {"name": "Щит", "role": "skeptic", "specialty": "compliance-risk", "mascot": "wolf"},
        {"name": "Медиатор", "role": "diplomat", "specialty": "pr-comms", "mascot": "owl"},
    ]),
]

EMBEDDING_MARKERS = ("embed", "embedding", "nomic-embed", "text-embedding", "bge", "e5")

TEXT_STOPWORDS = {
    "и", "или", "но", "что", "это", "как", "для", "про", "при", "после", "если", "чтобы", "когда",
    "уже", "ещё", "надо", "нужно", "есть", "будет", "быть", "этой", "этот", "того", "такой", "тоже",
    "the", "and", "for", "with", "that", "this", "from", "into", "after", "before", "about",
}

ROLE_HINT_KEYWORDS = {
    "critic": ("критик", "скептик", "оспор", "сомнен", "риск", "разоблач"),
    "strategist": ("стратег", "план", "решен", "roadmap", "маршрут", "собрать"),
    "creative": ("креатив", "идея", "образ", "бренд", "контент", "нестандарт"),
    "analyst": ("аналит", "метрик", "данн", "факт", "структур"),
    "synthesizer": ("синтез", "собрать", "свести", "обобщ", "сшить"),
    "pragmatist": ("практик", "операц", "внедр", "реализ", "выполн"),
    "diplomat": ("медиатор", "договор", "коммуник", "соглас", "мягк"),
    "investigator": ("расслед", "провер", "разобрать", "копнуть"),
}

ROLE_BALANCE_ORDER = (
    "critic",
    "strategist",
    "creative",
    "analyst",
    "synthesizer",
    "pragmatist",
    "diplomat",
    "investigator",
)

ROLE_MODEL_TAGS = {
    "strategist": {"strategy": 3, "business": 2, "synthesis": 1},
    "creative": {"creative": 3, "writing": 2, "story": 2},
    "critic": {"critic": 3, "risk": 2, "analysis": 1},
    "synthesizer": {"synthesis": 3, "writing": 2, "diplomat": 1},
    "visionary": {"creative": 2, "strategy": 2, "story": 1},
    "analyst": {"analysis": 3, "data": 2, "strategy": 1},
    "provocateur": {"critic": 2, "creative": 2, "risk": 1},
    "diplomat": {"diplomat": 3, "synthesis": 2, "writing": 1},
    "pragmatist": {"ops": 2, "business": 2, "strategy": 1},
    "skeptic": {"critic": 3, "analysis": 2, "risk": 2},
    "philosopher": {"synthesis": 2, "writing": 2, "story": 2},
    "mentor": {"diplomat": 2, "writing": 2, "synthesis": 2},
    "investigator": {"analysis": 3, "critic": 2, "risk": 1},
    "optimist": {"creative": 2, "business": 1, "story": 1},
    "pessimist": {"critic": 2, "risk": 3, "analysis": 1},
    "comedian": {"creative": 2, "story": 3, "writing": 1},
    "showman": {"creative": 2, "story": 3, "business": 1},
}

SPECIALTY_MODEL_TAGS = {
    "marketing-generalist": {"creative": 2, "business": 1},
    "product-marketing": {"creative": 2, "business": 2},
    "seo-strategy": {"analysis": 2, "business": 1},
    "brand-content": {"creative": 3, "writing": 2, "story": 2},
    "sales-funnels": {"business": 3, "analysis": 1},
    "pr-comms": {"writing": 2, "diplomat": 2, "creative": 1},
    "business-dev": {"business": 3, "strategy": 2},
    "product-manager": {"strategy": 3, "business": 2, "analysis": 1},
    "ux-research": {"analysis": 2, "creative": 2, "writing": 1},
    "frontend-engineer": {"analysis": 2, "creative": 1, "ops": 1},
    "backend-architect": {"analysis": 3, "ops": 2, "risk": 1},
    "ai-automation": {"analysis": 3, "ops": 2, "strategy": 1},
    "data-analytics": {"analysis": 3, "data": 3},
    "cybersecurity": {"risk": 3, "analysis": 2, "critic": 1},
    "fintech-systems": {"analysis": 2, "business": 2, "risk": 2},
    "economist": {"analysis": 2, "data": 2, "business": 2},
    "finance-strategy": {"analysis": 3, "business": 2, "data": 1},
    "investor": {"business": 3, "strategy": 2, "analysis": 1},
    "lawyer": {"critic": 3, "risk": 2, "writing": 1},
    "compliance-risk": {"risk": 3, "critic": 2, "analysis": 1},
    "ops-manager": {"ops": 3, "business": 2, "analysis": 1},
    "hr-people": {"diplomat": 2, "writing": 1, "analysis": 1},
    "psychologist": {"diplomat": 2, "story": 1, "analysis": 1},
    "coach-facilitator": {"diplomat": 2, "writing": 1, "synthesis": 1},
    "customer-success": {"diplomat": 2, "business": 1, "writing": 1},
    "producer": {"ops": 2, "creative": 1, "business": 1},
    "storyteller": {"story": 3, "writing": 2, "creative": 1},
    "creator-blogger": {"creative": 2, "story": 3, "writing": 1},
    "community-smm": {"creative": 2, "story": 2, "business": 1},
    "design-creative": {"creative": 3, "story": 1},
    "philosophy": {"story": 2, "writing": 2, "synthesis": 1},
    "sports-coach": {"ops": 2, "mentor": 1, "strategy": 1},
    "infobiz": {"business": 3, "creative": 2, "story": 1},
    "standup": {"story": 3, "creative": 2},
    "mystic": {"story": 2, "creative": 2, "writing": 1},
}


def _clamp_count(value: Any) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        count = 4
    return max(1, min(count, 8))


def _catalog_text(labels: dict[str, str]) -> str:
    return "\n".join(f"- {key}: {label}" for key, label in labels.items())


def _build_specialty_catalog(custom_specialties: list[dict[str, Any]] | None = None) -> tuple[dict[str, str], set[str]]:
    labels = dict(SPECIALTY_LABELS)
    for item in custom_specialties or []:
        value = str(item.get("value") or "").strip()
        label = str(item.get("label") or "").strip()
        if value and label:
            labels[value] = label
    return labels, set(labels.keys())


def _trim_text(value: Any, limit: int = 900) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}…"


def _is_embedding_model(model_name: str) -> bool:
    lowered = (model_name or "").lower()
    return any(marker in lowered for marker in EMBEDDING_MARKERS)


def _list_candidate_models(providers_payload: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for provider_name, config in (providers_payload or {}).items():
        if not config.get("available"):
            continue
        for order, model_name in enumerate(config.get("models") or []):
            if not model_name or _is_embedding_model(model_name):
                continue
            candidates.append({
                "provider": provider_name,
                "model": model_name,
                "order": order,
            })
    return candidates


def _topic_seed(topic: str) -> int:
    digest = hashlib.sha1((topic or "").encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _tokenize_text(value: Any) -> list[str]:
    tokens = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9-]{3,}", str(value or "").lower())
    return [token for token in tokens if token not in TEXT_STOPWORDS]


def _compress_context_text(value: Any, focus_tokens: set[str], *, limit: int, max_chunks: int = 3) -> str:
    text = str(value or "").strip()
    if not text or limit <= 0:
        return ""
    if len(text) <= limit:
        return text

    chunks = [
        re.sub(r"\s+", " ", chunk).strip()
        for chunk in re.split(r"[\n\r]+|(?<=[\.\!\?;])\s+", text)
        if re.sub(r"\s+", " ", chunk).strip()
    ]
    if not chunks:
        return _trim_text(text, limit)

    scored: list[tuple[int, int, str]] = []
    for index, chunk in enumerate(chunks):
        chunk_tokens = set(_tokenize_text(chunk))
        overlap = len(chunk_tokens & focus_tokens) if focus_tokens else 0
        richness = sum(1 for token in chunk_tokens if len(token) >= 7)
        score = overlap * 6 + richness * 2 - index
        scored.append((score, -index, chunk))

    scored.sort(reverse=True)
    selected: list[str] = []
    total_length = 0
    for _, _, chunk in scored:
        if chunk in selected:
            continue
        projected = total_length + len(chunk) + (2 if selected else 0)
        if projected > limit and selected:
            continue
        selected.append(chunk)
        total_length = projected
        if len(selected) >= max_chunks or total_length >= limit:
            break

    if not selected:
        return _trim_text(text, limit)
    return _trim_text(" ".join(selected), limit)


def _build_character_preferences(character: dict[str, Any]) -> dict[str, int]:
    weights = {"general": 1}
    for source in (
        ROLE_MODEL_TAGS.get(character.get("role"), {}),
        SPECIALTY_MODEL_TAGS.get(character.get("specialty"), {}),
    ):
        for tag, weight in source.items():
            weights[tag] = weights.get(tag, 0) + weight
    return weights


def _build_model_profile(provider_name: str, model_name: str) -> dict[str, int]:
    lowered = f"{provider_name}:{model_name}".lower()
    profile = {"general": 1}

    def add(**scores: int):
        for tag, value in scores.items():
            profile[tag] = profile.get(tag, 0) + value

    if provider_name == "anthropic":
        add(writing=3, synthesis=2, diplomat=2, strategy=2, critic=1)
    elif provider_name == "openai":
        add(strategy=2, analysis=2, writing=2, diplomat=1, business=1)
    elif provider_name == "ollama":
        add(general=1)

    if any(marker in lowered for marker in ("claude", "sonnet", "haiku")):
        add(writing=3, synthesis=2, diplomat=2, critic=1)
    if any(marker in lowered for marker in ("gpt", "o4-mini", "4o")):
        add(strategy=2, analysis=2, writing=2, business=1)
    if "gemini" in lowered or "flash" in lowered:
        add(creative=3, story=2, writing=1)
    if "gemma" in lowered:
        add(synthesis=2, diplomat=2, strategy=1, writing=1)
    if "qwen" in lowered:
        add(analysis=2, critic=1, writing=1, strategy=1)
    if "glm" in lowered:
        add(strategy=2, analysis=2, business=1)
    if "minimax" in lowered:
        add(creative=2, business=2, story=1)
    if "deepseek" in lowered or lowered.endswith(":r1") or "r1" in lowered:
        add(analysis=3, critic=2, risk=2, ops=1)
    if "nemotron" in lowered:
        add(ops=2, analysis=2, strategy=1)
    if "coder" in lowered or "code" in lowered:
        add(analysis=2, ops=2, risk=1)
    if any(marker in lowered for marker in ("reason", "thinking")):
        add(analysis=2, critic=1, strategy=1)

    return profile


def _assign_character_models(
    characters: list[dict[str, Any]],
    providers_payload: dict[str, dict[str, Any]],
    *,
    helper_provider: str | None,
    helper_model: str | None,
    topic: str,
) -> list[dict[str, Any]]:
    candidates = _list_candidate_models(providers_payload)
    if not candidates:
        if helper_provider and helper_model:
            for character in characters:
                character["provider"] = helper_provider
                character["model"] = helper_model
        return characters

    helper_pair = (helper_provider or "", helper_model or "")
    seed = _topic_seed(topic)
    used_pairs: dict[tuple[str, str], int] = {}
    assigned: list[dict[str, Any]] = []

    for index, character in enumerate(characters):
        preferences = _build_character_preferences(character)
        scored: list[tuple[float, tuple[str, str, int], dict[str, Any]]] = []

        for candidate in candidates:
            pair = (candidate["provider"], candidate["model"])
            profile = _build_model_profile(candidate["provider"], candidate["model"])
            score = sum(profile.get(tag, 0) * weight for tag, weight in preferences.items())
            if pair == helper_pair and len(candidates) > 1:
                score -= 1.25
            score -= used_pairs.get(pair, 0) * 4.0
            score += 0.25 if used_pairs.get(pair, 0) == 0 else 0
            rotation = (seed + index + candidate["order"]) % max(len(candidates), 1)
            scored.append((
                score,
                (-rotation, pair[0], pair[1], -candidate["order"]),
                candidate,
            ))

        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        chosen = scored[0][2]
        pair = (chosen["provider"], chosen["model"])
        used_pairs[pair] = used_pairs.get(pair, 0) + 1
        assigned.append({
            **character,
            "provider": chosen["provider"],
            "model": chosen["model"],
        })

    return assigned


def _format_roster(active_participants: list[dict[str, Any]] | None, specialty_labels: dict[str, str]) -> str:
    if not active_participants:
        return ""

    lines = []
    for participant in active_participants[:10]:
        role = ROLE_LABELS.get(participant.get("role", ""), participant.get("role") or "Участник")
        specialty = (
            participant.get("specialtyLabel")
            or specialty_labels.get(participant.get("specialty", ""))
            or participant.get("specialty")
            or "Без профиля"
        )
        name = participant.get("name") or "Безымянный"
        lines.append(f"{name}: {role}, {specialty}")
    return "; ".join(lines)


def _build_focus_tokens(
    topic: str,
    *,
    missing_expert_hint: str | None,
    latest_round_summary: str | None,
    active_participants: list[dict[str, Any]] | None,
    curated_recall: str | None,
    historical_memory: str | None,
) -> set[str]:
    ordered_tokens: list[str] = []
    for source in (topic, missing_expert_hint, latest_round_summary, curated_recall, historical_memory):
        ordered_tokens.extend(_tokenize_text(source))
    for participant in active_participants or []:
        ordered_tokens.extend(_tokenize_text(participant.get("role") or ""))
        ordered_tokens.extend(_tokenize_text(participant.get("specialtyLabel") or participant.get("specialty") or ""))

    unique_tokens: list[str] = []
    seen: set[str] = set()
    for token in ordered_tokens:
        if token in seen:
            continue
        seen.add(token)
        unique_tokens.append(token)
        if len(unique_tokens) >= 40:
            break
    return set(unique_tokens)


def _infer_desired_roles(
    *,
    active_participants: list[dict[str, Any]] | None,
    missing_expert_hint: str | None,
    mode: str,
) -> list[str]:
    active_roles = {
        str(participant.get("role") or "").strip()
        for participant in active_participants or []
        if participant.get("role")
    }
    desired_roles: list[str] = []
    hint_lower = str(missing_expert_hint or "").lower()
    for role, keywords in ROLE_HINT_KEYWORDS.items():
        if any(keyword in hint_lower for keyword in keywords) and role not in desired_roles:
            desired_roles.append(role)
    if mode == "gap_fill":
        for role in ROLE_BALANCE_ORDER:
            if role in active_roles or role in desired_roles:
                continue
            desired_roles.append(role)
            if len(desired_roles) >= 4:
                break
    return desired_roles[:4]


def _build_role_gap_text(
    *,
    active_participants: list[dict[str, Any]] | None,
    missing_expert_hint: str | None,
    mode: str,
) -> str:
    desired_roles = _infer_desired_roles(
        active_participants=active_participants,
        missing_expert_hint=missing_expert_hint,
        mode=mode,
    )
    if not desired_roles:
        return ""
    return ", ".join(ROLE_LABELS.get(role, role) for role in desired_roles)


def _extract_json(text: str) -> dict | None:
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return None
    return None


def _normalize_character(
    item: dict,
    index: int,
    specialty_labels: dict[str, str],
    allowed_specialties: set[str],
) -> dict:
    fallback = FALLBACK_POOL[index % len(FALLBACK_POOL)]
    role = item.get("role") if item.get("role") in ROLE_DESCRIPTIONS else fallback["role"]
    specialty = item.get("specialty") if item.get("specialty") in allowed_specialties else fallback["specialty"]
    mascot = item.get("mascot") if item.get("mascot") in MASCOT_DEFS else fallback["mascot"]
    name = str(item.get("name") or fallback["name"]).strip()[:32]
    summary = str(item.get("summary") or "").strip()[:240]
    specialty_label = specialty_labels.get(specialty, specialty)

    return {
        "name": name or fallback["name"],
        "role": role,
        "specialty": specialty,
        "specialtyLabel": specialty_label if specialty not in SPECIALTY_LABELS else None,
        "provider": str(item.get("provider") or "").strip(),
        "model": str(item.get("model") or "").strip(),
        "mascot": mascot,
        "emoji": MASCOT_DEFS[mascot],
        "summary": summary or f"{ROLE_LABELS[role]} с фокусом: {specialty_label}.",
        "stats": dict(DEFAULT_STATS),
        "strengths": [],
        "weaknesses": [],
        "lastNote": "Предложен кастинг-помощником под текущую задачу.",
    }


def _pick_memory_hint(*texts: str, limit: int = 180) -> str:
    for text in texts:
        for raw_line in str(text or "").splitlines():
            line = re.sub(r"^[\-\*\d\.\)\s]+", "", raw_line).strip()
            if not line:
                continue
            line = re.sub(r"\s+", " ", line)
            if len(line) > limit:
                line = f"{line[:limit].rstrip()}…"
            return line
    return ""


def _attach_character_explanations(
    characters: list[dict[str, Any]],
    *,
    helper_provider: str | None,
    helper_model: str | None,
    mode: str,
    missing_expert_hint: str | None,
    curated_recall: str | None,
    historical_memory: str | None,
) -> list[dict[str, Any]]:
    roster_memory_hint = _pick_memory_hint(curated_recall or "", historical_memory or "")
    helper_pair = (helper_provider or "", helper_model or "")
    explained: list[dict[str, Any]] = []
    for item in characters:
        role_label = ROLE_LABELS.get(item.get("role", ""), item.get("role") or "герой")
        specialty_label = SPECIALTY_LABELS.get(item.get("specialty", ""), item.get("specialtyLabel") or item.get("specialty") or "общий профиль")
        provider = item.get("provider") or "—"
        model = item.get("model") or "—"
        why_role = (
            f"{role_label} с профилем «{specialty_label}» закрывает практический пробел по теме."
            if mode == "gap_fill"
            else f"{role_label} с профилем «{specialty_label}» даёт отдельный полезный угол на тему."
        )
        why_model = (
            f"Для него разведена отдельная модель {provider}/{model}, чтобы состав не говорил одним голосом."
            if (provider, model) != helper_pair and helper_pair != ("", "")
            else f"Для роли оставлена модель {provider}/{model} как надёжная базовая опора."
        )
        memory_hint = ""
        if mode == "gap_fill" and missing_expert_hint:
            memory_hint = f"Хрономант просил добрать: {missing_expert_hint}"
        elif roster_memory_hint:
            memory_hint = roster_memory_hint
        explained.append({
            **item,
            "whyRole": why_role,
            "whyModel": why_model,
            "memoryHint": memory_hint,
        })
    return explained


def _score_fallback_candidate(
    item: dict[str, Any],
    *,
    source_bonus: int,
    focus_tokens: set[str],
    desired_roles: list[str],
    active_roles: set[str],
    active_specialties: set[str],
    chosen_roles: set[str],
    chosen_specialties: set[str],
    mode: str,
    specialty_labels: dict[str, str],
) -> int:
    role = item.get("role") or ""
    specialty = item.get("specialty") or ""
    candidate_text = " ".join([
        str(item.get("name") or ""),
        role,
        ROLE_LABELS.get(role, role),
        specialty,
        specialty_labels.get(specialty, specialty),
    ])
    candidate_tokens = set(_tokenize_text(candidate_text))
    score = source_bonus + len(candidate_tokens & focus_tokens) * 4

    if role in desired_roles:
        score += 14 - desired_roles.index(role) * 2
    if role not in active_roles and role not in chosen_roles:
        score += 6
    elif mode == "gap_fill":
        score -= 5

    if specialty not in active_specialties and specialty not in chosen_specialties:
        score += 5
    elif mode == "gap_fill":
        score -= 4

    if role in {"critic", "strategist", "creative", "analyst", "synthesizer"} and role not in active_roles:
        score += 2
    return score


def _fallback_characters(
    topic: str,
    count: int,
    specialty_labels: dict[str, str],
    allowed_specialties: set[str],
    *,
    mode: str,
    active_participants: list[dict[str, Any]] | None,
    missing_expert_hint: str | None,
    latest_round_summary: str | None,
    curated_recall: str | None,
    historical_memory: str | None,
) -> list[dict]:
    topic_lower = topic.lower()
    focus_tokens = _build_focus_tokens(
        topic,
        missing_expert_hint=missing_expert_hint,
        latest_round_summary=latest_round_summary,
        active_participants=active_participants,
        curated_recall=curated_recall,
        historical_memory=historical_memory,
    )
    desired_roles = _infer_desired_roles(
        active_participants=active_participants,
        missing_expert_hint=missing_expert_hint,
        mode=mode,
    )
    active_roles = {
        str(participant.get("role") or "").strip()
        for participant in active_participants or []
        if participant.get("role")
    }
    active_specialties = {
        str(participant.get("specialty") or "").strip()
        for participant in active_participants or []
        if participant.get("specialty")
    }

    pool: list[tuple[dict[str, Any], int]] = []
    for keywords, suggestions in KEYWORD_POOL:
        if any(keyword in topic_lower for keyword in keywords):
            pool.extend((suggestion, 8) for suggestion in suggestions)
    pool.extend((item, 0) for item in FALLBACK_POOL)

    unique: list[tuple[dict[str, Any], int]] = []
    seen = set()
    for item, source_bonus in pool:
        key = (item["role"], item["specialty"], item["name"])
        if key in seen:
            continue
        seen.add(key)
        unique.append((item, source_bonus))

    chosen: list[dict[str, Any]] = []
    chosen_roles: set[str] = set()
    chosen_specialties: set[str] = set()
    while len(chosen) < count and unique:
        scored: list[tuple[int, int, dict[str, Any]]] = []
        for index, (item, source_bonus) in enumerate(unique):
            scored.append((
                _score_fallback_candidate(
                    item,
                    source_bonus=source_bonus,
                    focus_tokens=focus_tokens,
                    desired_roles=desired_roles,
                    active_roles=active_roles,
                    active_specialties=active_specialties,
                    chosen_roles=chosen_roles,
                    chosen_specialties=chosen_specialties,
                    mode=mode,
                    specialty_labels=specialty_labels,
                ),
                -index,
                item,
            ))
        scored.sort(reverse=True)
        _, _, best = scored[0]
        chosen.append(best)
        chosen_roles.add(best["role"])
        chosen_specialties.add(best["specialty"])
        unique = [(item, bonus) for item, bonus in unique if item != best]

    return [
        _normalize_character(item, index, specialty_labels, allowed_specialties)
        for index, item in enumerate(chosen[:count])
    ]


def _select_provider(
    providers_payload: dict[str, dict[str, Any]],
    provider_name: str | None,
    model: str | None,
) -> tuple[str | None, str | None]:
    if provider_name and provider_name in PROVIDERS:
        config = providers_payload.get(provider_name, {})
        if config.get("available"):
            models = config.get("models", [])
            if model and (not models or model in models):
                return provider_name, model
            if models:
                return provider_name, models[0]

    return pick_observer_provider(providers_payload)


def _build_casting_context(
    *,
    topic: str,
    latest_round_summary: str | None,
    session_chronicle: str | None,
    room_summary: str | None,
    roster_text: str,
    missing_expert_hint: str | None,
    active_participants: list[dict[str, Any]] | None,
    curated_recall: str | None,
    historical_memory: str | None,
    mode: str,
    include_roster: bool = True,
    include_latest_round: bool = True,
    include_session_chronicle: bool = True,
    include_room_summary: bool = True,
    include_curated_recall: bool = True,
    include_historical_memory: bool = True,
    latest_round_limit: int = 420,
    session_chronicle_limit: int = 320,
    room_summary_limit: int = 220,
    curated_recall_limit: int = 220,
    historical_memory_limit: int = 180,
) -> str:
    focus_tokens = _build_focus_tokens(
        topic,
        missing_expert_hint=missing_expert_hint,
        latest_round_summary=latest_round_summary,
        active_participants=active_participants,
        curated_recall=curated_recall,
        historical_memory=historical_memory,
    )
    context_blocks: list[str] = []
    if missing_expert_hint:
        context_blocks.append(f"Подсказка Хрономанта:\n{_trim_text(missing_expert_hint, 220)}")
    role_gap_text = _build_role_gap_text(
        active_participants=active_participants,
        missing_expert_hint=missing_expert_hint,
        mode=mode,
    )
    if role_gap_text:
        context_blocks.append(f"Приоритетные недостающие голоса:\n{role_gap_text}")
    if include_roster and roster_text:
        context_blocks.append(f"Кто уже сидит за столом:\n{_trim_text(roster_text, 420)}")
    if include_latest_round and latest_round_summary and latest_round_summary.strip():
        compressed = _compress_context_text(latest_round_summary, focus_tokens, limit=latest_round_limit, max_chunks=3)
        if compressed:
            context_blocks.append(f"Сводка последнего раунда:\n{compressed}")
    if include_session_chronicle and session_chronicle and session_chronicle.strip():
        compressed = _compress_context_text(session_chronicle, focus_tokens, limit=session_chronicle_limit, max_chunks=2)
        if compressed:
            context_blocks.append(f"Хроника этой сессии:\n{compressed}")
    if include_room_summary and room_summary and room_summary.strip():
        compressed = _compress_context_text(room_summary, focus_tokens, limit=room_summary_limit, max_chunks=2)
        if compressed:
            context_blocks.append(f"Память комнаты:\n{compressed}")
    if include_curated_recall and curated_recall and curated_recall.strip():
        compressed = _compress_context_text(curated_recall, focus_tokens, limit=curated_recall_limit, max_chunks=2)
        if compressed:
            context_blocks.append(f"Куратор памяти о прошлых удачных и неудачных составах:\n{compressed}")
    if include_historical_memory and historical_memory and historical_memory.strip():
        compressed = _compress_context_text(historical_memory, focus_tokens, limit=historical_memory_limit, max_chunks=2)
        if compressed:
            context_blocks.append(f"Память помощника о похожих прошлых сессиях и составах:\n{compressed}")
    return "\n\n".join(context_blocks)


def _build_casting_prompt(
    *,
    topic: str,
    safe_count: int,
    specialty_labels: dict[str, str],
    mode: str,
    custom_specialties: list[dict[str, Any]] | None,
    missing_expert_hint: str | None,
    context_text: str,
) -> str:
    prompt = (
        "Ты кастинг-помощник для игры-дискуссии «Круглый стол ИИ».\n"
        "Нужно подобрать персонажей под тему пользователя и по возможности усилить уже идущую беседу.\n"
        "Верни только JSON без markdown и пояснений.\n\n"
        f"Тема: {topic}\n"
        f"Количество персонажей: {safe_count}\n\n"
        "Доступные роли, используй только эти ключи:\n"
        f"{_catalog_text(ROLE_LABELS)}\n\n"
        "Доступные профессиональные профили, используй только эти ключи:\n"
        f"{_catalog_text(specialty_labels)}\n\n"
        "Доступные образы, используй только эти ключи: "
        f"{', '.join(MASCOT_DEFS.keys())}.\n\n"
        "Формат:\n"
        '{"characters":[{"name":"имя на русском","role":"analyst","specialty":"data-analytics","mascot":"fox","summary":"зачем этот персонаж нужен в обсуждении"}]}\n'
        "Состав должен быть разнообразным: минимум один критик/скептик, один практик/стратег и один креативный или синтезирующий голос, если количество позволяет.\n"
        "Если контекст беседы уже есть, подбирай не дубликаты, а недостающие и полезные голоса, которые закроют пробелы в текущем составе."
    )

    if custom_specialties:
        prompt += (
            "\nПользовательские профили в этом списке созданы специально для этой игры. "
            "Если подсказка Хрономанта совпадает с таким профилем, используй его ключ."
        )

    if mode == "gap_fill":
        prompt += (
            "\n\nРежим: определить, кого сейчас не хватает за столом.\n"
            "Подбирай только действительно недостающих и полезных героев. "
            "Не дублируй уже имеющиеся роли и профессиональные профили без сильной причины."
        )
        if missing_expert_hint:
            prompt += f"\nПодсказка Хрономанта: {missing_expert_hint}"

    if context_text:
        prompt += f"\n\nКомпактный бриф ситуации:\n{context_text}"
    return prompt


def _build_priority_casting_prompts(
    *,
    topic: str,
    safe_count: int,
    specialty_labels: dict[str, str],
    mode: str,
    custom_specialties: list[dict[str, Any]] | None,
    missing_expert_hint: str | None,
    latest_round_summary: str | None,
    session_chronicle: str | None,
    room_summary: str | None,
    roster_text: str,
    curated_recall: str | None,
    historical_memory: str | None,
    active_participants: list[dict[str, Any]] | None,
) -> list[str]:
    # Compression order is priority-based, not arbitrary:
    # 1) keep the freshest round context and current roster as long as possible;
    # 2) drop long-term memory helpers first;
    # 3) only then trim room/session history;
    # 4) touch the fresh round summary and roster last.
    stages = [
        {
            "include_latest_round": True,
            "include_session_chronicle": True,
            "include_room_summary": True,
            "include_roster": True,
            "include_curated_recall": True,
            "include_historical_memory": True,
            "latest_round_limit": 420,
            "session_chronicle_limit": 320,
            "room_summary_limit": 220,
            "curated_recall_limit": 220,
            "historical_memory_limit": 180,
        },
        {
            "include_latest_round": True,
            "include_session_chronicle": True,
            "include_room_summary": True,
            "include_roster": True,
            "include_curated_recall": True,
            "include_historical_memory": False,
            "latest_round_limit": 420,
            "session_chronicle_limit": 320,
            "room_summary_limit": 220,
            "curated_recall_limit": 220,
            "historical_memory_limit": 0,
        },
        {
            "include_latest_round": True,
            "include_session_chronicle": True,
            "include_room_summary": True,
            "include_roster": True,
            "include_curated_recall": False,
            "include_historical_memory": False,
            "latest_round_limit": 420,
            "session_chronicle_limit": 320,
            "room_summary_limit": 220,
            "curated_recall_limit": 0,
            "historical_memory_limit": 0,
        },
        {
            "include_latest_round": True,
            "include_session_chronicle": True,
            "include_room_summary": False,
            "include_roster": True,
            "include_curated_recall": False,
            "include_historical_memory": False,
            "latest_round_limit": 420,
            "session_chronicle_limit": 320,
            "room_summary_limit": 0,
            "curated_recall_limit": 0,
            "historical_memory_limit": 0,
        },
        {
            "include_latest_round": True,
            "include_session_chronicle": False,
            "include_room_summary": False,
            "include_roster": True,
            "include_curated_recall": False,
            "include_historical_memory": False,
            "latest_round_limit": 360,
            "session_chronicle_limit": 0,
            "room_summary_limit": 0,
            "curated_recall_limit": 0,
            "historical_memory_limit": 0,
        },
        {
            "include_latest_round": True,
            "include_session_chronicle": False,
            "include_room_summary": False,
            "include_roster": False,
            "include_curated_recall": False,
            "include_historical_memory": False,
            "latest_round_limit": 360,
            "session_chronicle_limit": 0,
            "room_summary_limit": 0,
            "curated_recall_limit": 0,
            "historical_memory_limit": 0,
        },
        {
            "include_latest_round": False,
            "include_session_chronicle": False,
            "include_room_summary": False,
            "include_roster": False,
            "include_curated_recall": False,
            "include_historical_memory": False,
            "latest_round_limit": 0,
            "session_chronicle_limit": 0,
            "room_summary_limit": 0,
            "curated_recall_limit": 0,
            "historical_memory_limit": 0,
        },
    ]
    prompts: list[str] = []
    seen: set[str] = set()
    for stage in stages:
        context_text = _build_casting_context(
            topic=topic,
            latest_round_summary=latest_round_summary,
            session_chronicle=session_chronicle,
            room_summary=room_summary,
            roster_text=roster_text,
            missing_expert_hint=missing_expert_hint,
            active_participants=active_participants,
            curated_recall=curated_recall,
            historical_memory=historical_memory,
            mode=mode,
            include_roster=stage["include_roster"],
            include_latest_round=stage["include_latest_round"],
            include_session_chronicle=stage["include_session_chronicle"],
            include_room_summary=stage["include_room_summary"],
            include_curated_recall=stage["include_curated_recall"],
            include_historical_memory=stage["include_historical_memory"],
            latest_round_limit=stage["latest_round_limit"],
            session_chronicle_limit=stage["session_chronicle_limit"],
            room_summary_limit=stage["room_summary_limit"],
            curated_recall_limit=stage["curated_recall_limit"],
            historical_memory_limit=stage["historical_memory_limit"],
        )
        prompt = _build_casting_prompt(
            topic=topic,
            safe_count=safe_count,
            specialty_labels=specialty_labels,
            mode=mode,
            custom_specialties=custom_specialties,
            missing_expert_hint=missing_expert_hint,
            context_text=context_text,
        )
        if prompt in seen:
            continue
        seen.add(prompt)
        prompts.append(prompt)
    return prompts


async def _run_casting_provider(provider: Any, model: str, prompt: str) -> str:
    messages = [
        {"role": "system", "content": "Отвечай строго валидным JSON. Видимый текст внутри JSON пиши на русском."},
        {"role": "user", "content": prompt},
    ]
    return await asyncio.wait_for(provider.stream_chat(model, messages, None), timeout=45)


def _should_retry_with_compact_context(exc: Exception) -> bool:
    if not isinstance(exc, httpx.HTTPStatusError):
        return False
    status_code = exc.response.status_code if exc.response is not None else None
    return status_code not in {401, 403, 404}


async def suggest_characters(
    *,
    topic: str,
    count: Any,
    providers_payload: dict[str, dict[str, Any]],
    mode: str = "full",
    provider_name: str | None = None,
    model: str | None = None,
    room_summary: str | None = None,
    session_chronicle: str | None = None,
    latest_round_summary: str | None = None,
    active_participants: list[dict[str, Any]] | None = None,
    missing_expert_hint: str | None = None,
    custom_specialties: list[dict[str, Any]] | None = None,
    curated_recall: str | None = None,
) -> dict:
    safe_count = _clamp_count(count)
    selected_provider, selected_model = _select_provider(providers_payload, provider_name, model)
    specialty_labels, allowed_specialties = _build_specialty_catalog(custom_specialties)
    roster_text = _format_roster(active_participants, specialty_labels)
    historical_memory = ""
    if selected_provider or provider_name:
        historical_memory = await asyncio.to_thread(
            query_casting_memory,
            topic=topic,
            helper_provider=selected_provider or provider_name,
            helper_model=selected_model or model,
            active_participants=active_participants,
            mode=mode,
            missing_expert_hint=missing_expert_hint,
        )
    fallback = _fallback_characters(
        topic,
        safe_count,
        specialty_labels,
        allowed_specialties,
        mode=mode,
        active_participants=active_participants,
        missing_expert_hint=missing_expert_hint,
        latest_round_summary=latest_round_summary,
        curated_recall=curated_recall,
        historical_memory=historical_memory,
    )
    context_text = _build_casting_context(
        topic=topic,
        latest_round_summary=latest_round_summary,
        session_chronicle=session_chronicle,
        room_summary=room_summary,
        roster_text=roster_text,
        missing_expert_hint=missing_expert_hint,
        active_participants=active_participants,
        curated_recall=curated_recall,
        historical_memory=historical_memory,
        mode=mode,
    )

    if not selected_provider or not selected_model:
        fallback = _assign_character_models(
            fallback,
            providers_payload,
            helper_provider=provider_name,
            helper_model=model,
            topic=topic,
        )
        return {
            "source": "fallback",
            "provider": None,
            "model": None,
            "mode": mode,
            "characters": fallback,
            "message": "Провайдер помощника недоступен, поэтому создан локальный черновик состава.",
        }

    provider = PROVIDERS[selected_provider]()
    prompts = _build_priority_casting_prompts(
        topic=topic,
        safe_count=safe_count,
        specialty_labels=specialty_labels,
        mode=mode,
        custom_specialties=custom_specialties,
        missing_expert_hint=missing_expert_hint,
        latest_round_summary=latest_round_summary,
        session_chronicle=session_chronicle,
        room_summary=room_summary,
        roster_text=roster_text,
        curated_recall=curated_recall,
        historical_memory=historical_memory,
        active_participants=active_participants,
    )

    try:
        raw = ""
        for prompt_index, prompt in enumerate(prompts):
            try:
                raw = await _run_casting_provider(provider, selected_model, prompt)
                break
            except Exception as exc:
                has_more_attempts = prompt_index < len(prompts) - 1
                if not has_more_attempts or not _should_retry_with_compact_context(exc):
                    raise
        parsed = _extract_json(raw)
        items = parsed.get("characters", []) if isinstance(parsed, dict) else []
        normalized = [
            _normalize_character(item, index, specialty_labels, allowed_specialties)
            for index, item in enumerate(items)
            if isinstance(item, dict)
        ][:safe_count]
        if len(normalized) < safe_count:
            normalized.extend(fallback[len(normalized):safe_count])
        normalized = _assign_character_models(
            normalized[:safe_count],
            providers_payload,
            helper_provider=selected_provider,
            helper_model=selected_model,
            topic=topic,
        )
        normalized = _attach_character_explanations(
            normalized[:safe_count],
            helper_provider=selected_provider,
            helper_model=selected_model,
            mode=mode,
            missing_expert_hint=missing_expert_hint,
            curated_recall=curated_recall,
            historical_memory=historical_memory,
        )
        return {
            "source": "model",
            "provider": selected_provider,
            "model": selected_model,
            "mode": mode,
            "characters": normalized[:safe_count],
            "message": (
                "Помощник собрал черновик состава с учётом темы и свежего контекста беседы."
                if context_text and mode != "gap_fill"
                else "Помощник подсветил недостающих героев для текущего состава."
                if mode == "gap_fill"
                else "Помощник собрал черновик состава под текущую задачу."
            ),
        }
    except Exception as exc:
        fallback = _assign_character_models(
            fallback,
            providers_payload,
            helper_provider=selected_provider,
            helper_model=selected_model,
            topic=topic,
        )
        fallback = _attach_character_explanations(
            fallback,
            helper_provider=selected_provider,
            helper_model=selected_model,
            mode=mode,
            missing_expert_hint=missing_expert_hint,
            curated_recall=curated_recall,
            historical_memory=historical_memory,
        )
        return {
            "source": "fallback",
            "provider": selected_provider,
            "model": selected_model,
            "mode": mode,
            "characters": fallback,
            "message": "Помощник собрал локальный черновик состава.",
        }
