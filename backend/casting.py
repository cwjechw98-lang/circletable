from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from agents import ROLE_DESCRIPTIONS, SPECIALTY_DESCRIPTIONS
from defaults import DEFAULT_STATS, pick_observer_provider
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


def _clamp_count(value: Any) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        count = 4
    return max(2, min(count, 8))


def _catalog_text(labels: dict[str, str]) -> str:
    return "\n".join(f"- {key}: {label}" for key, label in labels.items())


def _trim_text(value: Any, limit: int = 900) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}…"


def _format_roster(active_participants: list[dict[str, Any]] | None) -> str:
    if not active_participants:
        return ""

    lines = []
    for participant in active_participants[:10]:
        role = ROLE_LABELS.get(participant.get("role", ""), participant.get("role") or "Участник")
        specialty = SPECIALTY_LABELS.get(
            participant.get("specialty", ""),
            participant.get("specialty") or "Без профиля",
        )
        provider = participant.get("provider") or "—"
        model = participant.get("model") or "—"
        name = participant.get("name") or "Безымянный"
        lines.append(f"- {name}: {role}, {specialty}, {provider}/{model}")
    return "\n".join(lines)


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


def _normalize_character(item: dict, index: int) -> dict:
    fallback = FALLBACK_POOL[index % len(FALLBACK_POOL)]
    role = item.get("role") if item.get("role") in ROLE_DESCRIPTIONS else fallback["role"]
    specialty = item.get("specialty") if item.get("specialty") in SPECIALTY_DESCRIPTIONS else fallback["specialty"]
    mascot = item.get("mascot") if item.get("mascot") in MASCOT_DEFS else fallback["mascot"]
    name = str(item.get("name") or fallback["name"]).strip()[:32]
    summary = str(item.get("summary") or "").strip()[:240]

    return {
        "name": name or fallback["name"],
        "role": role,
        "specialty": specialty,
        "mascot": mascot,
        "emoji": MASCOT_DEFS[mascot],
        "summary": summary or f"{ROLE_LABELS[role]} с фокусом: {SPECIALTY_LABELS[specialty]}.",
        "stats": dict(DEFAULT_STATS),
        "strengths": [],
        "weaknesses": [],
        "lastNote": "Предложен кастинг-помощником под текущую задачу.",
    }


def _fallback_characters(topic: str, count: int) -> list[dict]:
    topic_lower = topic.lower()
    pool: list[dict] = []
    for keywords, suggestions in KEYWORD_POOL:
        if any(keyword in topic_lower for keyword in keywords):
            pool.extend(suggestions)
    pool.extend(FALLBACK_POOL)

    unique: list[dict] = []
    seen = set()
    for item in pool:
        key = (item["role"], item["specialty"], item["name"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
        if len(unique) >= count:
            break

    return [_normalize_character(item, index) for index, item in enumerate(unique[:count])]


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
) -> dict:
    safe_count = _clamp_count(count)
    selected_provider, selected_model = _select_provider(providers_payload, provider_name, model)
    fallback = _fallback_characters(topic, safe_count)
    context_blocks: list[str] = []
    roster_text = _format_roster(active_participants)

    if latest_round_summary and latest_round_summary.strip():
        context_blocks.append(f"Сводка последнего раунда:\n{_trim_text(latest_round_summary, 700)}")
    if session_chronicle and session_chronicle.strip():
        context_blocks.append(f"Хроника этой сессии:\n{_trim_text(session_chronicle, 1000)}")
    if room_summary and room_summary.strip():
        context_blocks.append(f"Память комнаты:\n{_trim_text(room_summary, 700)}")
    if roster_text:
        context_blocks.append(f"Кто уже сидит за столом:\n{roster_text}")

    context_text = "\n\n".join(context_blocks)

    if not selected_provider or not selected_model:
        return {
            "source": "fallback",
            "provider": None,
            "model": None,
            "mode": mode,
            "characters": fallback,
            "message": "Провайдер помощника недоступен, поэтому создан локальный черновик состава.",
        }

    provider = PROVIDERS[selected_provider]()
    prompt = (
        "Ты кастинг-помощник для игры-дискуссии «Круглый стол ИИ».\n"
        "Нужно подобрать персонажей под тему пользователя и по возможности усилить уже идущую беседу.\n"
        "Верни только JSON без markdown и пояснений.\n\n"
        f"Тема: {topic}\n"
        f"Количество персонажей: {safe_count}\n\n"
        "Доступные роли, используй только эти ключи:\n"
        f"{_catalog_text(ROLE_LABELS)}\n\n"
        "Доступные профессиональные профили, используй только эти ключи:\n"
        f"{_catalog_text(SPECIALTY_LABELS)}\n\n"
        "Доступные образы, используй только эти ключи: "
        f"{', '.join(MASCOT_DEFS.keys())}.\n\n"
        "Формат:\n"
        '{"characters":[{"name":"имя на русском","role":"analyst","specialty":"data-analytics","mascot":"fox","summary":"зачем этот персонаж нужен в обсуждении"}]}\n'
        "Состав должен быть разнообразным: минимум один критик/скептик, один практик/стратег и один креативный или синтезирующий голос, если количество позволяет.\n"
        "Если контекст беседы уже есть, подбирай не дубликаты, а недостающие и полезные голоса, которые закроют пробелы в текущем составе."
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
        prompt += f"\n\nКонтекст комнаты и текущего обсуждения:\n{context_text}"

    messages = [
        {"role": "system", "content": "Отвечай строго валидным JSON. Видимый текст внутри JSON пиши на русском."},
        {"role": "user", "content": prompt},
    ]

    try:
        raw = await asyncio.wait_for(provider.stream_chat(selected_model, messages, None), timeout=45)
        parsed = _extract_json(raw)
        items = parsed.get("characters", []) if isinstance(parsed, dict) else []
        normalized = [
            _normalize_character(item, index)
            for index, item in enumerate(items)
            if isinstance(item, dict)
        ][:safe_count]
        if len(normalized) < safe_count:
            normalized.extend(fallback[len(normalized):safe_count])
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
        return {
            "source": "fallback",
            "provider": selected_provider,
            "model": selected_model,
            "mode": mode,
            "characters": fallback,
            "message": f"Помощник не успел ответить, поэтому создан локальный черновик: {type(exc).__name__}.",
        }
