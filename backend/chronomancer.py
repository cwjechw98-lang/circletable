from __future__ import annotations

import asyncio
import json
import re
from collections import defaultdict
from typing import Any

from meta_memory import query_observer_memory
from providers import get_provider


STAT_LABELS = {
    "insight": "Инсайт",
    "focus": "Фокус",
    "depth": "Глубина",
    "cooperation": "Кооперация",
    "showmanship": "Сценичность",
}

POSITIVE_WORDS = [
    "идея",
    "решение",
    "план",
    "вывод",
    "итог",
    "польза",
    "нужно",
    "стоит",
    "предлага",
    "соглас",
]

HUMOR_WORDS = ["смеш", "шут", "ирон", "ха", "мем"]
RISK_WORDS = ["риск", "опас", "ошиб", "но", "однако", "огранич"]
DECISION_WORDS = ["решение", "итог", "выбор", "фиксир", "резюм", "план", "договор"]
AGREEMENT_WORDS = ["соглас", "сход", "один приоритет", "общий вывод", "берём", "делаем"]
DECISION_STAGES = {"explore", "challenge", "converge", "decide", "stalled"}
NEXT_ACTIONS = {"continue", "ask_user", "add_expert", "bench_participant", "fact_check", "final_round"}
ROSTER_GAP_STATUSES = {"none", "missing", "overcrowded", "conflicted", "resolved"}


class Chronomancer:
    async def review_round(
        self,
        *,
        topic: str,
        observer_provider: str | None,
        observer_model: str | None,
        observer_mode: str,
        chronicle: str,
        round_number: int,
        round_messages: list[dict],
        participants: list[dict],
        room_events: list[dict],
        wrap_requested: bool,
        final_round_planned: bool,
        extension_count: int,
        curated_recall: str = "",
    ) -> dict:
        try:
            llm_review = await self._try_llm_review(
                topic=topic,
                observer_provider=observer_provider,
                observer_model=observer_model,
                observer_mode=observer_mode,
                chronicle=chronicle,
                round_number=round_number,
                round_messages=round_messages,
                participants=participants,
                room_events=room_events,
                wrap_requested=wrap_requested,
                final_round_planned=final_round_planned,
                extension_count=extension_count,
                curated_recall=curated_recall,
            )
        except Exception:
            llm_review = None
        if llm_review:
            return self._normalize_review(
                review=llm_review,
                chronicle_before=chronicle,
                round_number=round_number,
                participants=participants,
            )

        return self._heuristic_review(
            topic=topic,
            chronicle=chronicle,
            round_number=round_number,
            round_messages=round_messages,
            participants=participants,
            room_events=room_events,
            wrap_requested=wrap_requested,
            final_round_planned=final_round_planned,
            extension_count=extension_count,
            observer_mode=observer_mode,
        )

    async def _try_llm_review(
        self,
        *,
        topic: str,
        observer_provider: str | None,
        observer_model: str | None,
        observer_mode: str,
        chronicle: str,
        round_number: int,
        round_messages: list[dict],
        participants: list[dict],
        room_events: list[dict],
        wrap_requested: bool,
        final_round_planned: bool,
        extension_count: int,
        curated_recall: str = "",
    ) -> dict | None:
        if not observer_provider or not observer_model:
            return None

        provider = get_provider(observer_provider)
        if not provider.is_available():
            return None

        roster = "\n".join(
            f"- {item['name']} | profile_id={item['profileId']} | role={item['role']} | specialty={item['specialty']}"
            for item in participants
        )
        observer_memory = await asyncio.to_thread(
            query_observer_memory,
            topic=topic,
            observer_provider=observer_provider,
            observer_model=observer_model,
            participants=participants,
            chronicle=chronicle,
        )
        dialogue = "\n".join(
            (
                f"- {message.get('name') or message.get('agent_name')}: {message.get('content', '')}"
                + self._format_tool_usage_for_prompt(message)
            )
            for message in round_messages
        )
        events = "\n".join(
            f"- {event['type']}: {json.dumps(event['payload'], ensure_ascii=False)}"
            for event in room_events
        ) or "- нет значимых событий состава"

        schema = {
            "roundSummary": "string",
            "chronicle": "string",
            "tableComment": "string",
            "recommendation": "continue|suggest_final|final_round|complete",
            "suggestedRoundsLeft": "number|null",
            "finalReason": "string",
            "missingExpertHint": "string",
            "progress": {
                "novelty": "number",
                "focus": "number",
                "convergence": "number",
                "decisionProgress": {
                    "stage": "explore|challenge|converge|decide|stalled",
                    "readiness": "number 0..100",
                    "blocker": "string",
                    "nextAction": "continue|ask_user|add_expert|bench_participant|fact_check|final_round",
                    "rationale": "string",
                },
            },
            "decisionProgress": {
                "stage": "explore|challenge|converge|decide|stalled",
                "readiness": "number 0..100",
                "blocker": "string",
                "nextAction": "continue|ask_user|add_expert|bench_participant|fact_check|final_round",
                "rationale": "string",
            },
            "rosterAdvice": {
                "missingExpertHint": "string",
                "excessParticipant": {
                    "participantId": "string|null",
                    "profileId": "string|null",
                    "name": "string|null",
                    "reason": "string",
                    "confidence": "number 0..100",
                },
                "balanceNote": "string",
                "gapStatus": "none|missing|overcrowded|conflicted|resolved",
            },
            "participantComments": {"profile_id": "string"},
            "statsDelta": {
                "profile_id": {
                    "insight": "integer",
                    "focus": "integer",
                    "depth": "integer",
                    "cooperation": "integer",
                    "showmanship": "integer",
                }
            },
            "achievements": [
                {
                    "profileId": "string",
                    "title": "string",
                    "reason": "string",
                }
            ],
        }

        messages = [
            {
                "role": "system",
                "content": (
                    "Ты Хрономант — наблюдатель за круглым столом ИИ. "
                    "Отвечай только чистым JSON без markdown и без пояснений. "
                    "Если данных мало, всё равно верни аккуратную структуру."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Тема: {topic}\n"
                    f"Режим: {observer_mode}\n"
                    f"Номер раунда: {round_number}\n"
                    f"Хроника до раунда:\n{chronicle or 'Пока пусто.'}\n\n"
                    f"Состав:\n{roster}\n\n"
                    f"Куратор памяти уже отметил такие похожие паттерны:\n{curated_recall or '- пока нет отобранных паттернов'}\n\n"
                    f"Твоя память о похожих прошлых сессиях:\n{observer_memory or '- пока нет релевантных воспоминаний'}\n\n"
                    f"События состава:\n{events}\n\n"
                    f"Полный лог текущего раунда:\n{dialogue or '- пусто'}\n\n"
                    f"Сигнал закругляться: {'да' if wrap_requested else 'нет'}\n"
                    f"Финальный раунд уже запланирован: {'да' if final_round_planned else 'нет'}\n"
                    f"Число продлений: {extension_count}\n\n"
                    "Дополнительно оцени управление составом: кто нужен для продвижения решения и кто сейчас мешает фокусу. "
                    "Это не оценка личности участника: excessParticipant заполняй только если участник в текущем раунде уводил от темы, "
                    "повторял старое, конфликтовал без пользы или снижал фокус. "
                    "Если уверенность ниже 55 или причина слабая, верни excessParticipant=null.\n\n"
                    f"Верни JSON по схеме:\n{json.dumps(schema, ensure_ascii=False)}"
                ),
            },
        ]

        try:
            raw = await asyncio.wait_for(
                provider.stream_chat(observer_model, messages, on_token=None),
                timeout=18.0,
            )
        except Exception:
            return None

        if not raw.strip():
            return None

        match = re.search(r"\{.*\}", raw, re.S)
        if not match:
            return None

        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

    def _normalize_review(self, *, review: dict, chronicle_before: str, round_number: int, participants: list[dict]) -> dict:
        profile_ids = {item["profileId"] for item in participants}
        normalized_delta = {}
        for profile_id, values in (review.get("statsDelta") or {}).items():
            if profile_id not in profile_ids or not isinstance(values, dict):
                continue
            normalized_delta[profile_id] = {
                key: int(values.get(key, 0))
                for key in STAT_LABELS
            }

        normalized_comments = {
            profile_id: text
            for profile_id, text in (review.get("participantComments") or {}).items()
            if profile_id in profile_ids and isinstance(text, str)
        }

        achievements = []
        for entry in review.get("achievements") or []:
            if not isinstance(entry, dict):
                continue
            profile_id = entry.get("profileId")
            if profile_id not in profile_ids:
                continue
            achievements.append({
                "profileId": profile_id,
                "title": entry.get("title", "Заметный ход"),
                "reason": entry.get("reason", ""),
            })

        raw_roster_advice = review.get("rosterAdvice") if isinstance(review.get("rosterAdvice"), dict) else {}
        missing_expert_hint = str(
            review.get("missingExpertHint")
            or raw_roster_advice.get("missingExpertHint")
            or ""
        ).strip()
        roster_advice = self._normalize_roster_advice(
            review=review,
            participants=participants,
            missing_expert_hint=missing_expert_hint,
        )
        progress = self._normalize_progress(
            review.get("progress"),
            decision_progress=review.get("decisionProgress"),
            recommendation=review.get("recommendation", "continue"),
            final_reason=review.get("finalReason", ""),
            missing_expert_hint=missing_expert_hint,
            excess_participant=roster_advice.get("excessParticipant"),
        )

        return {
            "chronicleBefore": chronicle_before,
            "chronicle": review.get("chronicle", chronicle_before),
            "roundSummary": review.get("roundSummary", f"Раунд {round_number} завершён."),
            "tableComment": review.get("tableComment", ""),
            "recommendation": review.get("recommendation", "continue"),
            "suggestedRoundsLeft": review.get("suggestedRoundsLeft"),
            "finalReason": review.get("finalReason", ""),
            "missingExpertHint": missing_expert_hint,
            "progress": progress,
            "decisionProgress": progress["decisionProgress"],
            "rosterAdvice": roster_advice,
            "participantComments": normalized_comments,
            "statsDelta": normalized_delta,
            "achievements": achievements,
        }

    def _heuristic_review(
        self,
        *,
        topic: str,
        chronicle: str,
        round_number: int,
        round_messages: list[dict],
        participants: list[dict],
        room_events: list[dict],
        wrap_requested: bool,
        final_round_planned: bool,
        extension_count: int,
        observer_mode: str,
    ) -> dict:
        comments: dict[str, str] = {}
        stats_delta: dict[str, dict[str, int]] = {}
        achievements: list[dict[str, str]] = []
        summaries: list[str] = []

        profile_map = {item["id"]: item["profileId"] for item in participants}
        active_names = {item["id"]: item["name"] for item in participants}

        for message in round_messages:
            participant_id = message.get("participant_id") or message.get("agent_id")
            profile_id = profile_map.get(participant_id)
            if not profile_id:
                continue

            content = (message.get("content") or "").strip()
            lowered = content.lower()
            sentences = re.split(r"(?<=[.!?])\s+", content)
            short_summary = sentences[0][:160] if sentences and sentences[0] else content[:160]
            if short_summary:
                summaries.append(f"{active_names.get(participant_id, 'Участник')}: {short_summary}")

            focus = 3 if any(word in lowered for word in self._topic_keywords(topic)) else 1
            insight = 4 if any(word in lowered for word in POSITIVE_WORDS) else 1
            depth = 3 if len(content) > 140 else 1
            cooperation = 3 if "соглас" in lowered or "вместе" in lowered or "давайте" in lowered else 1
            showmanship = 3 if "!" in content or any(word in lowered for word in HUMOR_WORDS) else 1

            if any(word in lowered for word in RISK_WORDS):
                depth += 1
            if message.get("toolCalls"):
                insight += 1
                depth += 1

            delta = {
                "insight": min(5, insight),
                "focus": min(4, focus),
                "depth": min(5, depth),
                "cooperation": min(4, cooperation),
                "showmanship": min(4, showmanship),
            }
            stats_delta[profile_id] = delta
            best_stat = max(delta, key=delta.get)
            comments[profile_id] = (
                f"{active_names.get(participant_id, 'Участник')} усилил показатель «{STAT_LABELS[best_stat]}»: "
                f"{self._stat_comment(best_stat, lowered)}"
            )
            achievements.append({
                "profileId": profile_id,
                "title": self._achievement_title(best_stat),
                "reason": comments[profile_id],
            })

        event_note = self._compose_event_note(room_events)
        round_summary = " | ".join(summaries[:4]) or f"Раунд {round_number} прошёл без заметных реплик."
        progress = self._score_progress(topic=topic, chronicle=chronicle, round_messages=round_messages, round_summary=round_summary)
        missing_expert_hint = self._suggest_missing_expert(topic=topic, participants=participants, round_messages=round_messages)
        excess_participant = self._suggest_excess_participant(
            topic=topic,
            participants=participants,
            round_messages=round_messages,
            progress=progress,
        )

        chronicle_parts = [part for part in [chronicle.strip(), f"Раунд {round_number}: {round_summary}"] if part]
        chronicle_after = "\n".join(chronicle_parts[-6:])

        recommendation = "continue"
        rounds_left = None
        final_reason = ""
        if final_round_planned:
            recommendation = "complete"
            rounds_left = 0
            final_reason = "Финальный раунд уже был назначен, поэтому стол фиксирует итог."
        elif observer_mode == "auto" and wrap_requested and extension_count >= 2:
            recommendation = "final_round"
            rounds_left = 1
            final_reason = "Стол уже несколько раз подталкивали к выводу, пора завершать следующий круг итогами."
        elif wrap_requested:
            recommendation = "suggest_final"
            rounds_left = 1
            final_reason = "Пользователь уже попросил закругляться, поэтому следующий шаг — мягкая финализация."
        elif observer_mode != "manual" and round_number >= 8 and (
            progress["novelty"] <= 36 or progress["convergence"] >= 64
        ):
            recommendation = "final_round" if observer_mode == "auto" else "suggest_final"
            rounds_left = 1
            final_reason = "Раундов уже много, новизна упала, а стол близок к повторению тезисов."
        elif observer_mode != "manual" and round_number >= 6 and progress["novelty"] <= 34:
            recommendation = "suggest_final"
            rounds_left = 1
            final_reason = "Новых ходов почти не прибавляется, разговор начинает ходить по кругу."
        elif observer_mode != "manual" and round_number >= 5 and progress["convergence"] >= 70:
            recommendation = "suggest_final"
            rounds_left = 1
            final_reason = "Стол уже близок к общему выводу, можно аккуратно подводить итог."
        elif observer_mode != "manual" and round_number >= 4:
            recommendation = "suggest_final"
            rounds_left = 1
            final_reason = "Обсуждение уже разогрелось: Хрономант начинает присматриваться к моменту финала."

        progress = self._normalize_progress(
            progress,
            recommendation=recommendation,
            final_reason=final_reason,
            missing_expert_hint=missing_expert_hint,
            excess_participant=excess_participant,
        )
        roster_advice = {
            "missingExpertHint": missing_expert_hint,
            "excessParticipant": excess_participant,
            "balanceNote": self._compose_roster_balance_note(missing_expert_hint, excess_participant),
            "gapStatus": "missing" if missing_expert_hint else "conflicted" if excess_participant else "none",
        }
        table_comment = event_note or self._compose_progress_note(progress, final_reason, missing_expert_hint)

        return {
            "chronicleBefore": chronicle,
            "chronicle": chronicle_after,
            "roundSummary": round_summary,
            "tableComment": table_comment,
            "recommendation": recommendation,
            "suggestedRoundsLeft": rounds_left,
            "finalReason": final_reason,
            "missingExpertHint": missing_expert_hint,
            "progress": progress,
            "decisionProgress": progress["decisionProgress"],
            "rosterAdvice": roster_advice,
            "participantComments": comments,
            "statsDelta": stats_delta,
            "achievements": achievements[: min(len(achievements), 5)],
        }

    def _topic_keywords(self, topic: str) -> list[str]:
        words = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]{4,}", topic.lower())
        return words[:8]

    def _stat_comment(self, stat_key: str, lowered: str) -> str:
        if stat_key == "insight":
            return "в реплике появилась новая полезная зацепка."
        if stat_key == "focus":
            return "участник держал линию темы и не распылялся."
        if stat_key == "depth":
            return "реплика добавила аргументы и оговорила риски."
        if stat_key == "cooperation":
            return "участник помогал сшивать идеи команды."
        if any(word in lowered for word in HUMOR_WORDS):
            return "подача добавила сценичности и запоминаемости."
        return "реплика заметно оживила обсуждение."

    def _achievement_title(self, stat_key: str) -> str:
        return {
            "insight": "Свежий инсайт",
            "focus": "Держит линию",
            "depth": "Глубокий ход",
            "cooperation": "Командный импульс",
            "showmanship": "Яркая подача",
        }[stat_key]

    def _compose_event_note(self, room_events: list[dict]) -> str:
        recent = []
        for event in room_events:
            payload = event.get("payload") or {}
            if event["type"] == "participant_added":
                recent.append(f"после прихода {payload.get('name', 'нового участника')} стол получил новый угол зрения")
            elif event["type"] == "participant_benched":
                recent.append(f"после ухода {payload.get('name', 'участника')} беседа стала уже и спокойнее")
            elif event["type"] == "participant_restored":
                recent.append(f"возвращение {payload.get('name', 'участника')} снова изменило тон разговора")
        return ". ".join(recent[:2]).strip().capitalize()

    def _normalize_roster_advice(self, *, review: dict, participants: list[dict], missing_expert_hint: str) -> dict:
        raw = review.get("rosterAdvice") if isinstance(review.get("rosterAdvice"), dict) else {}
        missing = (missing_expert_hint or raw.get("missingExpertHint") or "").strip()
        excess = self._normalize_excess_participant(raw.get("excessParticipant"), participants)
        balance_note = self._coerce_text(raw.get("balanceNote")) or self._compose_roster_balance_note(missing, excess)
        gap_status = self._coerce_text(raw.get("gapStatus"))
        if gap_status not in ROSTER_GAP_STATUSES:
            gap_status = "missing" if missing else "conflicted" if excess else "none"
        return {
            "missingExpertHint": missing,
            "excessParticipant": excess,
            "balanceNote": balance_note,
            "gapStatus": gap_status,
        }

    def _normalize_excess_participant(self, raw: Any, participants: list[dict]) -> dict | None:
        if not isinstance(raw, dict):
            return None

        confidence = self._coerce_percent(raw.get("confidence"), default=0)
        if confidence < 55:
            return None

        participants_by_id = {item.get("id"): item for item in participants if item.get("id")}
        participants_by_profile = {item.get("profileId"): item for item in participants if item.get("profileId")}
        participants_by_name = {
            str(item.get("name") or "").strip().lower(): item
            for item in participants
            if item.get("name")
        }

        participant = None
        participant_id = self._coerce_text(raw.get("participantId") or raw.get("participant_id"))
        profile_id = self._coerce_text(raw.get("profileId") or raw.get("profile_id"))
        name = self._coerce_text(raw.get("name"))
        if participant_id:
            participant = participants_by_id.get(participant_id)
        if not participant and profile_id:
            participant = participants_by_profile.get(profile_id)
        if not participant and name:
            participant = participants_by_name.get(name.lower())
        if not participant:
            return None

        return {
            "participantId": participant.get("id"),
            "profileId": participant.get("profileId"),
            "name": participant.get("name") or name,
            "reason": self._coerce_text(raw.get("reason")) or "В этом раунде вклад чаще снижал фокус обсуждения.",
            "confidence": confidence,
        }

    def _normalize_progress(
        self,
        progress: dict | None,
        *,
        decision_progress: dict | None = None,
        recommendation: str = "continue",
        final_reason: str = "",
        missing_expert_hint: str = "",
        excess_participant: dict | None = None,
    ) -> dict:
        progress = progress or {}
        normalized = {
            "novelty": self._coerce_percent(progress.get("novelty"), default=50),
            "focus": self._coerce_percent(progress.get("focus"), default=50),
            "convergence": self._coerce_percent(progress.get("convergence"), default=50),
        }
        raw_decision_progress = decision_progress
        if not isinstance(raw_decision_progress, dict) and isinstance(progress.get("decisionProgress"), dict):
            raw_decision_progress = progress.get("decisionProgress")
        normalized["decisionProgress"] = self._normalize_decision_progress(
            normalized,
            raw_decision_progress,
            recommendation=recommendation,
            final_reason=final_reason,
            missing_expert_hint=missing_expert_hint,
            excess_participant=excess_participant,
        )
        return normalized

    def _normalize_decision_progress(
        self,
        progress: dict,
        raw: dict | None,
        *,
        recommendation: str,
        final_reason: str,
        missing_expert_hint: str,
        excess_participant: dict | None,
    ) -> dict:
        raw = raw if isinstance(raw, dict) else {}
        stage = self._coerce_text(raw.get("stage"))
        if stage not in DECISION_STAGES:
            stage = self._infer_decision_stage(progress, recommendation)

        readiness_raw = raw.get("readiness")
        readiness = self._coerce_percent(readiness_raw, default=self._estimate_readiness(progress, recommendation))
        blocker = self._coerce_text(raw.get("blocker")) or self._infer_decision_blocker(
            progress=progress,
            final_reason=final_reason,
            missing_expert_hint=missing_expert_hint,
            excess_participant=excess_participant,
        )
        next_action = self._coerce_text(raw.get("nextAction"))
        if next_action not in NEXT_ACTIONS:
            next_action = self._infer_next_action(
                progress=progress,
                recommendation=recommendation,
                missing_expert_hint=missing_expert_hint,
                excess_participant=excess_participant,
            )
        rationale = self._coerce_text(raw.get("rationale")) or self._infer_decision_rationale(
            progress=progress,
            stage=stage,
            next_action=next_action,
        )
        return {
            "stage": stage,
            "readiness": readiness,
            "blocker": blocker,
            "nextAction": next_action,
            "rationale": rationale,
        }

    def _infer_decision_stage(self, progress: dict, recommendation: str) -> str:
        if recommendation in {"complete", "final_round"}:
            return "decide"
        if progress["focus"] < 34:
            return "stalled"
        if recommendation == "suggest_final" or progress["convergence"] >= 62:
            return "converge"
        if progress["novelty"] >= 62 and progress["convergence"] < 48:
            return "explore"
        return "challenge"

    def _estimate_readiness(self, progress: dict, recommendation: str) -> int:
        readiness = round(
            progress["convergence"] * 0.55
            + progress["focus"] * 0.30
            + max(0, 100 - progress["novelty"]) * 0.15
        )
        if recommendation == "complete":
            readiness = max(readiness, 92)
        elif recommendation in {"final_round", "suggest_final"}:
            readiness = max(readiness, 72)
        return max(0, min(100, readiness))

    def _infer_decision_blocker(
        self,
        *,
        progress: dict,
        final_reason: str,
        missing_expert_hint: str,
        excess_participant: dict | None,
    ) -> str:
        if missing_expert_hint:
            return f"Не хватает экспертизы: {missing_expert_hint}"
        if excess_participant:
            return f"{excess_participant.get('name', 'Участник')} сейчас снижает фокус обсуждения."
        if progress["focus"] < 42:
            return "Разговор расползается: нужно сузить вопрос или вернуть участников к теме."
        if progress["novelty"] < 36:
            return "Новых ходов мало: стол начал повторять уже сказанное."
        if progress["convergence"] < 40:
            return "Есть идеи, но они ещё не сведены в один вариант решения."
        return final_reason or "Явного блокера нет: можно двигаться к следующему управленческому шагу."

    def _infer_next_action(
        self,
        *,
        progress: dict,
        recommendation: str,
        missing_expert_hint: str,
        excess_participant: dict | None,
    ) -> str:
        if recommendation in {"complete", "final_round", "suggest_final"}:
            return "final_round"
        if missing_expert_hint:
            return "add_expert"
        if excess_participant and progress["focus"] < 50:
            return "bench_participant"
        if progress["focus"] < 42:
            return "ask_user"
        return "continue"

    def _infer_decision_rationale(self, *, progress: dict, stage: str, next_action: str) -> str:
        return (
            f"Стадия {stage}: новизна {progress['novelty']}%, "
            f"фокус {progress['focus']}%, сходимость {progress['convergence']}%; следующий ход — {next_action}."
        )

    def _coerce_percent(self, value: Any, *, default: int) -> int:
        try:
            return max(0, min(100, int(round(float(value)))))
        except (TypeError, ValueError):
            return default

    def _coerce_text(self, value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        if value is None:
            return ""
        return str(value).strip()

    def _compose_roster_balance_note(self, missing_expert_hint: str, excess_participant: dict | None) -> str:
        if missing_expert_hint and excess_participant:
            return "Составу одновременно не хватает нужной оптики и стоит временно разгрузить фокус."
        if missing_expert_hint:
            return "Составу не хватает одной предметной оптики для продвижения решения."
        if excess_participant:
            return "Состав в целом работоспособен, но один голос сейчас снижает фокус раунда."
        return "Состав выглядит сбалансированным для текущего шага."

    def _extract_keywords(self, text: str) -> set[str]:
        return {
            word
            for word in re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]{4,}", (text or "").lower())
            if len(word) >= 4
        }

    def _score_progress(self, *, topic: str, chronicle: str, round_messages: list[dict], round_summary: str) -> dict:
        topic_keywords = self._extract_keywords(topic)
        chronicle_keywords = self._extract_keywords(chronicle)
        round_text = " ".join((message.get("content") or "") for message in round_messages)
        round_keywords = self._extract_keywords(round_text)

        new_keywords = round_keywords - chronicle_keywords
        overlap_ratio = 0
        if round_keywords:
            overlap_ratio = len(round_keywords & chronicle_keywords) / max(len(round_keywords), 1)

        topic_hits = len(round_keywords & topic_keywords)
        novelty = 34 + min(46, len(new_keywords) * 4) - int(overlap_ratio * 28)
        focus = 38 + min(34, topic_hits * 8)
        convergence = 22

        lowered = round_text.lower()
        convergence += sum(8 for word in DECISION_WORDS if word in lowered)
        convergence += sum(6 for word in AGREEMENT_WORDS if word in lowered)
        if "итог" in round_summary.lower() or "план" in round_summary.lower():
            convergence += 10
        if overlap_ratio > 0.62:
            novelty -= 12
        if topic_hits == 0:
            focus -= 14

        return {
            "novelty": max(0, min(100, novelty)),
            "focus": max(0, min(100, focus)),
            "convergence": max(0, min(100, convergence)),
        }

    def _compose_progress_note(self, progress: dict, final_reason: str, missing_expert_hint: str) -> str:
        parts = [
            f"Новизна: {progress['novelty']}%",
            f"Фокус: {progress['focus']}%",
            f"Сходимость: {progress['convergence']}%",
        ]
        if final_reason:
            parts.append(final_reason)
        if missing_expert_hint:
            parts.append(f"Не хватает голоса: {missing_expert_hint}")
        return " · ".join(parts)

    def _format_tool_usage_for_prompt(self, message: dict) -> str:
        tool_calls = message.get("toolCalls") or []
        if not tool_calls:
            return ""
        parts = [
            f"{item.get('tool')}({item.get('query')})"
            for item in tool_calls
            if item.get("tool")
        ]
        return f"\n  Инструменты: {', '.join(parts)}" if parts else ""

    def _suggest_excess_participant(
        self,
        *,
        topic: str,
        participants: list[dict],
        round_messages: list[dict],
        progress: dict,
    ) -> dict | None:
        if len(participants) < 3 or progress.get("focus", 50) >= 60:
            return None

        topic_keywords = self._extract_keywords(topic)
        if not topic_keywords:
            return None

        participants_by_id = {item.get("id"): item for item in participants if item.get("id")}
        messages_by_participant: dict[str, list[str]] = defaultdict(list)
        all_round_keywords: dict[str, int] = defaultdict(int)

        for message in round_messages:
            content = (message.get("content") or "").strip()
            if not content:
                continue
            for keyword in self._extract_keywords(content):
                all_round_keywords[keyword] += 1
            participant_id = message.get("participant_id") or message.get("agent_id")
            if participant_id in participants_by_id:
                messages_by_participant[participant_id].append(content)

        if not messages_by_participant:
            return None

        scored: list[tuple[int, dict, str]] = []
        for participant_id, contents in messages_by_participant.items():
            participant = participants_by_id[participant_id]
            content = "\n".join(contents)
            lowered = content.lower()
            keywords = self._extract_keywords(content)
            topic_overlap = keywords & topic_keywords
            repeated_offtopic = {
                keyword
                for keyword in keywords
                if all_round_keywords[keyword] > 1 and keyword not in topic_keywords
            }

            score = 0
            if not topic_overlap:
                score += 28
            if len(content) < 80:
                score += 8
            if len(keywords) <= 4:
                score += 6
            if repeated_offtopic and not topic_overlap:
                score += min(14, len(repeated_offtopic) * 3)
            if any(word in lowered for word in HUMOR_WORDS) and not topic_overlap:
                score += 8
            if not any(word in lowered for word in POSITIVE_WORDS + RISK_WORDS + DECISION_WORDS):
                score += 6

            reason = "В этом раунде чаще уводил разговор от темы и не добавил нового фокуса."
            if repeated_offtopic:
                reason = "В этом раунде заметно повторял боковые мотивы вместо продвижения темы."
            scored.append((score, participant, reason))

        if not scored:
            return None

        scored.sort(key=lambda item: item[0], reverse=True)
        best_score, participant, reason = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else 0
        if best_score < 50 or best_score - second_score < 16:
            return None

        confidence = min(86, 40 + best_score)
        if confidence < 55:
            return None

        return {
            "participantId": participant.get("id"),
            "profileId": participant.get("profileId"),
            "name": participant.get("name"),
            "reason": reason,
            "confidence": confidence,
        }

    def _suggest_missing_expert(self, *, topic: str, participants: list[dict], round_messages: list[dict]) -> str:
        topic_text = f"{topic}\n" + "\n".join((message.get("content") or "") for message in round_messages[-4:])
        topic_text = topic_text.lower()
        specialties = {item.get("specialty") for item in participants}

        if any(word in topic_text for word in ["бюджет", "деньг", "окуп", "валют", "выруч", "цена"]) and "finance-strategy" not in specialties:
            return "Финансист или экономист, чтобы считать деньги и приоритеты."
        if any(word in topic_text for word in ["риск", "договор", "закон", "регул", "легал"]) and "lawyer" not in specialties and "compliance-risk" not in specialties:
            return "Юрист или комплаенс-специалист, чтобы закрыть правовые риски."
        if any(word in topic_text for word in ["продаж", "клиент", "воронк", "лид", "чек"]) and "sales-funnels" not in specialties:
            return "Практик по продажам и воронкам, чтобы перевести идею в сделки."
        if any(word in topic_text for word in ["интерфейс", "сайт", "продукт", "опыт", "ux"]) and "ux-research" not in specialties and "frontend-engineer" not in specialties:
            return "UX-исследователь или фронтендер, чтобы приземлить опыт пользователя."
        if "ops-manager" not in specialties and len(participants) >= 4:
            return "Операционный менеджер, чтобы превратить идеи в пошаговый план."
        return ""
