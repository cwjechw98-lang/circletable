from __future__ import annotations

import asyncio
import math
import os
import re
from typing import Awaitable, Callable

import httpx

from knowledge.lightrag_adapter import query_graph
from providers import PROVIDERS, get_provider
from storage import Repository

ProgressFn = Callable[[int], Awaitable[None]]

SECTION_SPECS = [
    ("summary", "1. Резюме"),
    ("decisions", "2. Ключевые решения"),
    ("participants", "3. Анализ по участникам"),
    ("timeline", "4. Хронология"),
    ("recommendations", "5. Рекомендации"),
]

OLLAMA_URL = "http://localhost:11434/api/chat"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


class ReportGenerator:
    def __init__(self, repository: Repository):
        self.repository = repository

    async def generate(
        self,
        session_id: str,
        provider_name: str = None,
        model: str = None,
        *,
        progress_callback: ProgressFn | None = None,
    ) -> dict:
        snapshot = self.repository.get_session_snapshot(session_id, make_current=False)
        if not snapshot or not snapshot["session"]:
            raise ValueError("Сессия не найдена")

        session = snapshot["session"]
        room = snapshot["room"]
        messages = self.repository.list_session_messages(session_id, limit=None)
        reviews = self.repository.get_observer_reviews(session_id)
        participants = self._build_participant_entries(snapshot, messages)
        graph_context = await self._load_graph_context(room.get("graphId"), session["topic"])

        await self._emit_progress(progress_callback, 10)

        chosen_provider, chosen_model = await self._resolve_provider_and_model(
            snapshot,
            provider_name,
            model,
        )
        report_input = self._build_report_input(snapshot, messages, reviews, participants, graph_context)
        use_single_pass = self._estimate_tokens(report_input["fullContext"]) < 12000

        sections: list[dict]
        actual_provider = chosen_provider
        actual_model = chosen_model

        try:
            if chosen_provider and chosen_model:
                if use_single_pass:
                    await self._emit_progress(progress_callback, 35)
                    markdown = await self._generate_single_pass(chosen_provider, chosen_model, report_input)
                    sections = self._coerce_sections(markdown)
                else:
                    await self._emit_progress(progress_callback, 20)
                    outline = await self._generate_outline(chosen_provider, chosen_model, report_input)
                    sections = []
                    for index, (section_id, title) in enumerate(SECTION_SPECS, start=1):
                        evidence = self._build_section_evidence(section_id, snapshot, messages, reviews, participants, graph_context)
                        body = await self._generate_section(
                            chosen_provider,
                            chosen_model,
                            session["topic"],
                            title,
                            outline,
                            evidence,
                        )
                        sections.append({
                            "id": section_id,
                            "title": title,
                            "markdown": body.strip(),
                        })
                        await self._emit_progress(
                            progress_callback,
                            20 + math.floor((index / len(SECTION_SPECS)) * 70),
                        )
            else:
                actual_provider = "heuristic"
                actual_model = "local-fallback"
                sections = []

            sections = self._ensure_complete_sections(sections, snapshot, messages, reviews, participants, graph_context)
        except Exception:
            actual_provider = "heuristic"
            actual_model = "local-fallback"
            sections = self._heuristic_sections(snapshot, messages, reviews, participants, graph_context)

        if not sections:
            actual_provider = "heuristic"
            actual_model = "local-fallback"
            sections = self._heuristic_sections(snapshot, messages, reviews, participants, graph_context)

        markdown = self._compose_markdown(snapshot, sections)
        saved = self.repository.save_report(
            session_id,
            room.get("id"),
            markdown,
            sections,
            actual_provider,
            actual_model,
        )
        await self._emit_progress(progress_callback, 100)
        return saved

    async def _emit_progress(self, callback: ProgressFn | None, progress: int):
        if callback is not None:
            await callback(max(0, min(100, int(progress))))

    async def _resolve_provider_and_model(self, snapshot: dict, provider_name: str | None, model: str | None) -> tuple[str | None, str | None]:
        room = snapshot.get("room") or {}
        provider_name = provider_name or room.get("observerProvider")
        model = model or room.get("observerModel")

        if provider_name:
            try:
                provider = get_provider(provider_name)
            except ValueError:
                return None, None
            if not provider.is_available():
                return None, None
            if model:
                return provider_name, model
            models = await provider.list_models()
            return provider_name, models[0] if models else None

        for candidate in ("ollama", "openai", "anthropic"):
            if candidate not in PROVIDERS:
                continue
            provider = get_provider(candidate)
            if not provider.is_available():
                continue
            models = await provider.list_models()
            if models:
                return candidate, models[0]
        return None, None

    def _build_participant_entries(self, snapshot: dict, messages: list[dict]) -> list[dict]:
        roster = (snapshot.get("participants", {}) or {}).get("active", []) + (snapshot.get("participants", {}) or {}).get("benched", [])
        by_name: dict[str, list[str]] = {}
        for message in messages:
            if message.get("author_type") != "agent":
                continue
            name = (message.get("name") or message.get("agent_name") or "").strip()
            content = (message.get("content") or "").strip()
            if not name or not content:
                continue
            by_name.setdefault(name, []).append(content)

        entries = []
        seen: set[str] = set()
        for participant in roster:
            name = participant.get("name") or ""
            if not name or name in seen:
                continue
            seen.add(name)
            utterances = by_name.get(name, [])
            excerpts = utterances[:1] + utterances[-2:] if len(utterances) > 2 else utterances
            stats = participant.get("stats") or {}
            entries.append({
                "name": name,
                "role": participant.get("role") or "",
                "specialty": participant.get("specialty") or "",
                "stats": stats,
                "summary": participant.get("summary") or "",
                "lastNote": participant.get("lastNote") or "",
                "excerpts": excerpts,
            })
        return entries

    async def _load_graph_context(self, graph_id: str | None, topic: str) -> str:
        if not graph_id:
            return ""
        try:
            raw = await asyncio.to_thread(
                query_graph,
                graph_id,
                f"{topic}. Ключевые факты, определения, ограничения и выводы для итогового отчёта.",
                "hybrid",
                12,
            )
        except Exception:
            return ""
        return self._truncate(raw or "", 2600)

    def _build_report_input(self, snapshot: dict, messages: list[dict], reviews: list[dict], participants: list[dict], graph_context: str) -> dict:
        session = snapshot["session"]
        room = snapshot["room"]
        pinned = snapshot.get("pinnedMessages") or []

        metadata_lines = [
            f"Комната: {room.get('name') or '—'}",
            f"Тема: {session.get('topic') or '—'}",
            f"Статус: {session.get('status') or '—'}",
            f"Раундов: {session.get('lastRoundNumber') or 0}",
            f"Старт: {session.get('startedAt') or session.get('createdAt') or '—'}",
            f"Финал: {session.get('endedAt') or '—'}",
        ]
        chronicle = (session.get("chronicle") or "").strip()
        participant_lines = []
        for participant in participants:
            stats = participant["stats"]
            stat_line = ", ".join(
                f"{key}: {value}"
                for key, value in stats.items()
            ) or "нет числовых статов"
            excerpt_text = "\n".join(f"- {self._truncate(item, 220)}" for item in participant["excerpts"]) or "- нет реплик"
            participant_lines.append(
                "\n".join([
                    f"{participant['name']} ({participant['role']} · {participant['specialty']})",
                    f"Статы: {stat_line}",
                    f"Профиль: {participant['summary'] or '—'}",
                    f"Последняя заметка: {participant['lastNote'] or '—'}",
                    "Фрагменты реплик:",
                    excerpt_text,
                ])
            )

        review_lines = []
        for review in reviews:
            comments = review.get("comments") or {}
            comments_text = "; ".join(
                f"{name}: {self._truncate(text, 160)}"
                for name, text in comments.items()
            ) or "нет адресных комментариев"
            review_lines.append(
                "\n".join([
                    f"Раунд {review['roundNumber']}: {review.get('summary') or '—'}",
                    f"Рекомендация: {review.get('recommendation') or '—'}",
                    f"Причина финала: {review.get('finalReason') or '—'}",
                    f"Динамика решения: {self._format_decision_progress(review)}",
                    f"Состав: {self._format_roster_advice(review)}",
                    f"Комментарии: {comments_text}",
                ])
            )

        transcript_lines = []
        for message in messages:
            content = (message.get("content") or "").strip()
            if not content:
                continue
            if message.get("type") == "round":
                transcript_lines.append(f"[Раунд {message.get('round')}]")
                continue
            speaker = message.get("name") or message.get("agent_name") or "Система"
            prefix = f"Раунд {message.get('round')}: " if message.get("round") else ""
            transcript_lines.append(f"{prefix}{speaker}: {self._truncate(content, 520)}")

        pinned_lines = [
            f"- {(item.get('name') or item.get('agent_name') or 'Участник')}: {self._truncate(item.get('content') or '', 200)}"
            for item in pinned
        ]

        full_context = "\n\n".join([
            "=== МЕТАДАННЫЕ ===",
            "\n".join(metadata_lines),
            "=== ХРОНИКА ===",
            chronicle or "Хроника не заполнена.",
            "=== УЧАСТНИКИ ===",
            "\n\n".join(participant_lines) or "Нет данных по участникам.",
            "=== ОБЗОРЫ ХРОНОМАНТА ===",
            "\n\n".join(review_lines) or "Нет обзоров.",
            "=== ЗАЦЕПКИ ===",
            "\n".join(pinned_lines) or "Нет закреплённых мыслей.",
            "=== ФАКТЫ ИЗ ГРАФА ЗНАНИЙ ===",
            graph_context or "Граф знаний не подключён.",
            "=== ПОЛНАЯ ЛЕНТА СООБЩЕНИЙ ===",
            "\n".join(transcript_lines) or "Нет сообщений.",
        ])

        compact_context = "\n\n".join([
            "=== МЕТАДАННЫЕ ===",
            "\n".join(metadata_lines),
            "=== ХРОНИКА ===",
            chronicle or "Хроника не заполнена.",
            "=== ОБЗОРЫ ХРОНОМАНТА ===",
            "\n\n".join(review_lines[-6:]) or "Нет обзоров.",
            "=== ЗАЦЕПКИ ===",
            "\n".join(pinned_lines[:8]) or "Нет закреплённых мыслей.",
            "=== ФАКТЫ ИЗ ГРАФА ЗНАНИЙ ===",
            graph_context or "Граф знаний не подключён.",
        ])

        return {
            "metadata": metadata_lines,
            "chronicle": chronicle,
            "participants": participant_lines,
            "reviews": review_lines,
            "transcript": transcript_lines,
            "compactContext": compact_context,
            "fullContext": full_context,
        }

    def _estimate_tokens(self, text: str) -> int:
        return math.ceil(len(text) / 4)

    async def _generate_single_pass(self, provider_name: str, model: str, report_input: dict) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "Ты аналитик CircleTable. Подготовь структурированный итоговый отчёт по завершённой AI-дискуссии. "
                    "Пиши по-русски, опирайся только на переданные данные, не выдумывай факты. "
                    "Верни только Markdown с пятью разделами и ровно такими заголовками:\n"
                    "## 1. Резюме\n"
                    "## 2. Ключевые решения\n"
                    "## 3. Анализ по участникам\n"
                    "## 4. Хронология\n"
                    "## 5. Рекомендации"
                ),
            },
            {
                "role": "user",
                "content": report_input["fullContext"],
            },
        ]
        return (await self._chat(provider_name, model, messages, max_tokens=2200)).strip()

    async def _generate_outline(self, provider_name: str, model: str, report_input: dict) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "Ты аналитик CircleTable. Составь компактный план аналитического отчёта. "
                    "Верни только Markdown с пятью секциями под заголовками ## 1. Резюме ... ## 5. Рекомендации. "
                    "В каждой секции дай по 2-4 коротких bullet points, на что нужно сделать акцент."
                ),
            },
            {
                "role": "user",
                "content": report_input["compactContext"],
            },
        ]
        return (await self._chat(provider_name, model, messages, max_tokens=1200)).strip()

    async def _generate_section(
        self,
        provider_name: str,
        model: str,
        topic: str,
        title: str,
        outline: str,
        evidence: str,
    ) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "Ты аналитик CircleTable. Напиши только содержимое одного раздела отчёта в Markdown без заголовка раздела. "
                    "Пиши по-русски, держи академичный, но читаемый тон. Не добавляй вводные и не повторяй заголовок."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Тема: {topic}\n"
                    f"Раздел: {title}\n\n"
                    f"План отчёта:\n{outline}\n\n"
                    f"Доказательная база для раздела:\n{evidence}"
                ),
            },
        ]
        return (await self._chat(provider_name, model, messages, max_tokens=1200)).strip()

    async def _chat(self, provider_name: str, model: str, messages: list[dict], max_tokens: int) -> str:
        if provider_name == "ollama":
            async with httpx.AsyncClient(timeout=240.0) as client:
                response = await client.post(
                    OLLAMA_URL,
                    json={
                        "model": model,
                        "messages": messages,
                        "stream": False,
                        "options": {
                            "temperature": 0.25,
                            "num_predict": max_tokens,
                        },
                    },
                )
                response.raise_for_status()
                payload = response.json()
                return payload.get("message", {}).get("content", "")

        if provider_name == "openai":
            api_key = os.getenv("OPENAI_API_KEY", "")
            if not api_key:
                raise RuntimeError("OPENAI_API_KEY not set")
            async with httpx.AsyncClient(timeout=240.0) as client:
                response = await client.post(
                    OPENAI_URL,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": 0.25,
                        "max_tokens": max_tokens,
                    },
                )
                response.raise_for_status()
                payload = response.json()
                choices = payload.get("choices") or []
                return choices[0].get("message", {}).get("content", "") if choices else ""

        if provider_name == "anthropic":
            api_key = os.getenv("ANTHROPIC_API_KEY", "")
            if not api_key:
                raise RuntimeError("ANTHROPIC_API_KEY not set")
            system_lines = []
            chat_messages = []
            for message in messages:
                if message["role"] == "system":
                    system_lines.append(message["content"])
                else:
                    chat_messages.append({"role": message["role"], "content": message["content"]})
            async with httpx.AsyncClient(timeout=240.0) as client:
                response = await client.post(
                    ANTHROPIC_URL,
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": model,
                        "system": "\n".join(system_lines).strip(),
                        "messages": chat_messages,
                        "max_tokens": max_tokens,
                    },
                )
                response.raise_for_status()
                payload = response.json()
                content = payload.get("content") or []
                return "".join(item.get("text", "") for item in content if item.get("type") == "text")

        raise RuntimeError(f"Unknown provider: {provider_name}")

    def _build_section_evidence(
        self,
        section_id: str,
        snapshot: dict,
        messages: list[dict],
        reviews: list[dict],
        participants: list[dict],
        graph_context: str,
    ) -> str:
        session = snapshot["session"]
        pinned = snapshot.get("pinnedMessages") or []
        review_snippets = "\n".join(
            f"- Раунд {review['roundNumber']}: {review.get('summary') or '—'}; {self._format_decision_progress(review)}"
            for review in reviews
        ) or "- Нет обзоров"

        if section_id == "summary":
            return "\n\n".join([
                f"Тема: {session['topic']}",
                f"Хроника: {session.get('chronicle') or '—'}",
                "Участники:\n" + "\n".join(f"- {item['name']} ({item['role']} · {item['specialty']})" for item in participants),
                "Обзоры:\n" + review_snippets,
                f"Факты графа:\n{graph_context or 'Нет внешних фактов.'}",
            ])

        if section_id == "decisions":
            highlights = "\n".join(
                f"- {(item.get('name') or item.get('agent_name') or 'Участник')}: {self._truncate(item.get('content') or '', 220)}"
                for item in pinned[:8]
            ) or "- Нет закреплённых мыслей."
            return "\n\n".join([
                "Обзоры Хрономанта:\n" + review_snippets,
                "Закреплённые мысли:\n" + highlights,
                f"Финальная хроника:\n{session.get('chronicle') or '—'}",
            ])

        if section_id == "participants":
            return "\n\n".join(
                "\n".join([
                    f"{participant['name']} ({participant['role']} · {participant['specialty']})",
                    f"Статы: {', '.join(f'{key}: {value}' for key, value in participant['stats'].items()) or 'нет'}",
                    f"Профиль: {participant['summary'] or '—'}",
                    "Реплики:",
                    "\n".join(f"- {self._truncate(line, 260)}" for line in participant["excerpts"]) or "- нет реплик",
                ])
                for participant in participants
            ) or "Нет данных по участникам."

        if section_id == "timeline":
            transcript = []
            for message in messages:
                content = (message.get("content") or "").strip()
                if not content or message.get("type") == "round":
                    continue
                speaker = message.get("name") or message.get("agent_name") or "Система"
                transcript.append(f"- Раунд {message.get('round') or '—'} · {speaker}: {self._truncate(content, 220)}")
            return "\n\n".join([
                "Обзоры по раундам:\n" + review_snippets,
                "Опорные реплики:\n" + "\n".join(transcript[:18] + transcript[-12:]),
            ])

        return "\n\n".join([
            f"Финальная хроника:\n{session.get('chronicle') or '—'}",
            "Финальные замечания Хрономанта:\n" + review_snippets,
            f"Подсказка по пробелам в экспертизе: {(reviews[-1].get('missingExpertHint') if reviews else '') or 'нет'}",
            "Динамика решения и состава:\n" + "\n".join(self._decision_dynamics_lines(reviews) or ["- Недостаточно данных по динамике решения."]),
            f"Факты графа:\n{graph_context or 'Нет внешних фактов.'}",
        ])

    def _coerce_sections(self, markdown: str) -> list[dict]:
        if not markdown.strip():
            return []

        sections: list[dict] = []
        current_title: str | None = None
        current_lines: list[str] = []

        def flush():
            nonlocal current_title, current_lines
            if not current_title:
                return
            section_id = self._match_section_id(current_title)
            if not section_id:
                return
            sections.append({
                "id": section_id,
                "title": self._section_title(section_id),
                "markdown": "\n".join(current_lines).strip(),
            })
            current_title = None
            current_lines = []

        for raw_line in markdown.replace("\r\n", "\n").split("\n"):
            line = raw_line.rstrip()
            if line.startswith("## "):
                flush()
                current_title = line[3:].strip()
            else:
                current_lines.append(line)
        flush()
        return sections

    def _match_section_id(self, title: str) -> str | None:
        normalized = re.sub(r"^[0-9]+\.\s*", "", title).strip().lower()
        for section_id, section_title in SECTION_SPECS:
            target = re.sub(r"^[0-9]+\.\s*", "", section_title).strip().lower()
            if normalized == target or normalized in target or target in normalized:
                return section_id
        return None

    def _section_title(self, section_id: str) -> str:
        for current_id, title in SECTION_SPECS:
            if current_id == section_id:
                return title
        return section_id

    def _ensure_complete_sections(
        self,
        sections: list[dict],
        snapshot: dict,
        messages: list[dict],
        reviews: list[dict],
        participants: list[dict],
        graph_context: str,
    ) -> list[dict]:
        fallback = self._heuristic_sections(snapshot, messages, reviews, participants, graph_context)
        fallback_lookup = {section["id"]: section for section in fallback}
        normalized = []
        for section_id, title in SECTION_SPECS:
            section = next((item for item in sections if item["id"] == section_id and item.get("markdown")), None)
            normalized.append(section or fallback_lookup[section_id] or {"id": section_id, "title": title, "markdown": "Недостаточно данных."})
        return normalized

    def _heuristic_sections(
        self,
        snapshot: dict,
        messages: list[dict],
        reviews: list[dict],
        participants: list[dict],
        graph_context: str,
    ) -> list[dict]:
        session = snapshot["session"]
        room = snapshot["room"]
        last_review = reviews[-1] if reviews else {}
        participant_overview = "\n".join(
            f"- **{item['name']}** ({item['role']} · {item['specialty']}): {item['summary'] or 'держал позицию по теме'}, "
            f"последняя заметка — {item['lastNote'] or 'нет'}."
            for item in participants
        ) or "- Данных по участникам нет."
        review_overview = "\n".join(
            f"- Раунд {review['roundNumber']}: {review.get('summary') or 'без резюме'}; {self._format_decision_progress(review)}"
            for review in reviews
        ) or "- Хрономант не оставил обзоров."
        questions = [
            f"- {self._truncate(message.get('content') or '', 220)}"
            for message in messages
            if message.get("type") == "user_question" and (message.get("content") or "").strip()
        ]
        pinned = [
            f"- {(item.get('name') or item.get('agent_name') or 'Участник')}: {self._truncate(item.get('content') or '', 180)}"
            for item in snapshot.get("pinnedMessages") or []
        ]

        return [
            {
                "id": "summary",
                "title": "1. Резюме",
                "markdown": "\n".join([
                    f"Тема сессии: **{session['topic']}**.",
                    f"Комната: **{room['name']}**. Завершение: **{session.get('status') or '—'}**, раундов: **{session.get('lastRoundNumber') or 0}**.",
                    session.get("chronicle") or last_review.get("summary") or "Общая хроника пока не была зафиксирована отдельным текстом.",
                ]),
            },
            {
                "id": "decisions",
                "title": "2. Ключевые решения",
                "markdown": "\n".join([
                    "Поддержанные или заметные идеи:",
                    "\n".join(pinned or ["- Закреплённые мысли не выделялись."]),
                    "",
                    "Спорные точки по обзорам:",
                    review_overview,
                ]),
            },
            {
                "id": "participants",
                "title": "3. Анализ по участникам",
                "markdown": participant_overview,
            },
            {
                "id": "timeline",
                "title": "4. Хронология",
                "markdown": "\n".join([
                    "Ключевые повороты по раундам:",
                    review_overview,
                ]),
            },
            {
                "id": "recommendations",
                "title": "5. Рекомендации",
                "markdown": "\n".join([
                    last_review.get("finalReason") or "Финальная рекомендация не была явно сформулирована, поэтому стоит зафиксировать отдельным итогом, что именно принято и что осталось открытым.",
                    "",
                    "Незакрытые вопросы пользователя:",
                    "\n".join(questions or ["- Отдельных незакрытых вопросов в истории не найдено."]),
                    "",
                    "Динамика решения:",
                    "\n".join(self._decision_dynamics_lines(reviews) or ["- Недостаточно данных по динамике решения."]),
                    "",
                    "Дополнительный предметный контекст:",
                    graph_context or "Граф знаний не подключался или не дал дополнительных фактов.",
                ]),
            },
        ]

    def _compose_markdown(self, snapshot: dict, sections: list[dict]) -> str:
        session = snapshot["session"]
        room = snapshot["room"]
        title = session.get("title") or session.get("topic") or "Аналитический отчёт"
        lines = [
            f"# Аналитический отчёт: {title}",
            "",
            f"- Комната: {room.get('name') or '—'}",
            f"- Тема: {session.get('topic') or '—'}",
            f"- Статус: {session.get('status') or '—'}",
            f"- Раундов: {session.get('lastRoundNumber') or 0}",
            f"- Старт: {session.get('startedAt') or session.get('createdAt') or '—'}",
            f"- Финал: {session.get('endedAt') or '—'}",
            "",
        ]
        dynamics = self._decision_dynamics_lines(snapshot.get("observerReviews") or [])
        if dynamics:
            lines.extend([
                "## Динамика решения",
                "",
                *dynamics,
                "",
            ])
        for section in sections:
            lines.extend([
                f"## {section['title']}",
                "",
                (section.get("markdown") or "Недостаточно данных.").strip(),
                "",
            ])
        return "\n".join(lines).strip() + "\n"

    def _format_decision_progress(self, review: dict) -> str:
        progress = review.get("progress") or {}
        decision = progress.get("decisionProgress") or review.get("decisionProgress") or {}
        if not isinstance(decision, dict) or not decision:
            return "стадия не зафиксирована"
        stage = decision.get("stage") or "—"
        readiness = decision.get("readiness")
        readiness_text = f"{readiness}%" if readiness is not None else "—"
        blocker = decision.get("blocker") or "блокер не указан"
        next_action = decision.get("nextAction") or "continue"
        return f"стадия {stage}, готовность {readiness_text}, следующий ход {next_action}, блокер: {blocker}"

    def _format_roster_advice(self, review: dict) -> str:
        advice = review.get("rosterAdvice") or {}
        missing = advice.get("missingExpertHint") or review.get("missingExpertHint") or ""
        excess = advice.get("excessParticipant") if isinstance(advice.get("excessParticipant"), dict) else None
        parts = []
        if missing:
            parts.append(f"не хватает: {missing}")
        if excess:
            name = excess.get("name") or "участник"
            reason = excess.get("reason") or "снижает фокус"
            confidence = excess.get("confidence")
            confidence_text = f", confidence {confidence}%" if confidence is not None else ""
            parts.append(f"мешает фокусу сейчас: {name} ({reason}{confidence_text})")
        if not parts:
            parts.append("состав без явных рекомендаций")
        parts.append("применение: только вручную, автоматической скамейки нет")
        return "; ".join(parts)

    def _decision_dynamics_lines(self, reviews: list[dict]) -> list[str]:
        lines = []
        ordered = sorted(reviews or [], key=lambda item: item.get("roundNumber") or 0)
        for review in ordered:
            line = f"- Раунд {review.get('roundNumber') or '—'}: {self._format_decision_progress(review)}"
            roster_line = self._format_roster_advice(review)
            if roster_line:
                line = f"{line}; {roster_line}."
            lines.append(line)
        return lines

    def _truncate(self, text: str, limit: int) -> str:
        value = (text or "").strip()
        if len(value) <= limit:
            return value
        truncated = value[:limit].rsplit(" ", 1)[0].rstrip(" ,.;:-")
        return f"{truncated or value[:limit].rstrip()}…"
