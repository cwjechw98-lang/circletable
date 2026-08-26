from __future__ import annotations

import asyncio
import re
from typing import Awaitable, Callable

from knowledge.lightrag_adapter import query_graph
from storage import Repository, utc_now
from tools import SearchSnippet, search_external_snippets

ProgressFn = Callable[[int], Awaitable[None]]

CLAIM_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
TOKEN_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё%.-]{2,}")
NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?%?")
FACTUAL_MARKERS = (
    "по данным", "according to", "исследован", "study", "paper", "trial",
    "составляет", "равен", "достиг", "показывает", "shows", "reported",
    "подтверждает", "доказ", "clinical", "pubmed", "данные", "статист",
)
HEDGE_MARKERS = (
    "мне кажется", "кажется", "думаю", "возможно", "может быть", "наверное",
    "по-моему", "скорее всего", "i think", "maybe", "perhaps", "likely",
)
STOPWORDS = {
    "это", "этот", "эта", "эти", "что", "как", "для", "или", "если", "только",
    "после", "между", "когда", "where", "which", "with", "from", "that",
    "have", "has", "been", "were", "was", "their", "they", "them", "about",
    "there", "because", "the", "and", "for", "but", "into", "через", "чтобы",
    "который", "которая", "которые", "also", "than", "such", "при", "над",
    "под", "without", "into", "over", "under", "является", "бывает", "быть",
}


def _truncate(text: str, limit: int = 260) -> str:
    clean = re.sub(r"\s+", " ", (text or "")).strip()
    if len(clean) <= limit:
        return clean
    return f"{clean[:limit].rstrip()}…"


def _extract_numbers(text: str) -> set[str]:
    return {item.replace(",", ".") for item in NUMBER_RE.findall(text or "")}


def _tokenize(text: str) -> set[str]:
    tokens = set()
    for token in TOKEN_RE.findall((text or "").lower()):
        normalized = token.strip(".-_%")
        if len(normalized) < 3 or normalized in STOPWORDS:
            continue
        tokens.add(normalized)
    return tokens


def _is_verifiable_sentence(sentence: str) -> bool:
    text = re.sub(r"\s+", " ", (sentence or "")).strip()
    low = text.lower()
    if len(text) < 32 or len(text) > 280 or "?" in text:
        return False
    if any(marker in low for marker in HEDGE_MARKERS):
        return False
    if low.startswith(("давай", "let's", "можно", "стоит", "нужно")):
        return False
    return bool(_extract_numbers(text) or any(marker in low for marker in FACTUAL_MARKERS))


def _extract_claims_from_text(text: str, *, limit: int = 2) -> list[str]:
    claims: list[str] = []
    seen: set[str] = set()
    for raw_part in CLAIM_SPLIT_RE.split(text or ""):
        sentence = re.sub(r"\s+", " ", raw_part).strip(" -•\t")
        key = sentence.lower()
        if not sentence or key in seen:
            continue
        if not _is_verifiable_sentence(sentence):
            continue
        seen.add(key)
        claims.append(sentence)
        if len(claims) >= limit:
            break
    return claims


def _evaluate_evidence(claim: str, evidence_text: str) -> str:
    claim_tokens = _tokenize(claim)
    evidence_tokens = _tokenize(evidence_text)
    if not claim_tokens or not evidence_tokens:
        return "none"

    overlap = len(claim_tokens & evidence_tokens)
    ratio = overlap / max(len(claim_tokens), 1)
    if ratio < 0.18:
        return "none"

    claim_numbers = _extract_numbers(claim)
    evidence_numbers = _extract_numbers(evidence_text)
    if claim_numbers:
        if claim_numbers & evidence_numbers:
            return "support"
        if evidence_numbers and ratio >= 0.22:
            return "contradict"
        return "weak"

    if ratio >= 0.42:
        return "weak"
    return "none"


class FactCheckService:
    def __init__(self, repository: Repository):
        self.repository = repository

    async def run(self, run_id: str, *, progress_callback: ProgressFn | None = None) -> dict:
        run = self.repository.get_fact_check_run(run_id)
        if not run:
            raise ValueError("Fact-check run not found")

        snapshot = self.repository.get_session_snapshot(run["sessionId"], make_current=False)
        if not snapshot or not snapshot.get("session"):
            raise ValueError("Session not found")

        room = snapshot["room"]
        session = snapshot["session"]
        internet_mode = run.get("internetMode") or room.get("internetMode") or "auto"
        self.repository.update_fact_check_run(
            run_id,
            status="running",
            progress=5,
            internet_mode=internet_mode,
            provider=session.get("observerProvider") or room.get("observerProvider"),
            model=session.get("observerModel") or room.get("observerModel"),
            error="",
        )
        await self._emit_progress(progress_callback, 5)

        messages = self._select_messages(snapshot, run["scope"], run.get("targetRound"))
        claims = self._extract_claim_entries(snapshot, messages)
        if not claims:
            self.repository.replace_fact_check_claims(run_id, [])
            self.repository.update_fact_check_run(
                run_id,
                status="completed",
                progress=100,
                summary=self._build_summary(
                    counts={
                        "confirmed": 0,
                        "unverified": 0,
                        "contradicted": 0,
                        "disputed": 0,
                        "insufficient_evidence": 0,
                    },
                    scope=run["scope"],
                    target_round=run.get("targetRound"),
                    internet_mode=internet_mode,
                    external_sources_used=False,
                ),
                counts={
                    "confirmed": 0,
                    "unverified": 0,
                    "contradicted": 0,
                    "disputed": 0,
                    "insufficient_evidence": 0,
                },
                model_deltas=[],
                external_sources_used=False,
                completed_at=utc_now(),
            )
            await self._emit_progress(progress_callback, 100)
            return self.repository.get_fact_check_run(run_id, include_claims=True)

        external_sources_used = False
        total = len(claims)
        evaluated: list[dict] = []
        for index, claim in enumerate(claims, start=1):
            result = await self._check_single_claim(snapshot, claim, internet_mode)
            if result["sourceType"] in {"web", "science", "mixed"}:
                external_sources_used = True
            evaluated.append(result)
            progress = min(95, 10 + int((index / max(total, 1)) * 80))
            self.repository.update_fact_check_run(run_id, status="running", progress=progress)
            await self._emit_progress(progress_callback, progress)

        stored_claims = self.repository.replace_fact_check_claims(run_id, evaluated)
        counts = self._count_verdicts(stored_claims)
        model_deltas = self.repository.apply_model_reliability_rollup(stored_claims)
        self.repository.update_fact_check_run(
            run_id,
            status="completed",
            progress=100,
            summary=self._build_summary(
                counts=counts,
                scope=run["scope"],
                target_round=run.get("targetRound"),
                internet_mode=internet_mode,
                external_sources_used=external_sources_used,
            ),
            counts=counts,
            model_deltas=model_deltas,
            external_sources_used=external_sources_used,
            completed_at=utc_now(),
        )
        await self._emit_progress(progress_callback, 100)
        return self.repository.get_fact_check_run(run_id, include_claims=True)

    async def fail(self, run_id: str, error: Exception | str) -> dict | None:
        return self.repository.update_fact_check_run(
            run_id,
            status="failed",
            progress=100,
            error=str(error),
            completed_at=utc_now(),
        )

    async def _emit_progress(self, callback: ProgressFn | None, progress: int):
        if callback is not None:
            await callback(max(0, min(100, int(progress))))

    def _select_messages(self, snapshot: dict, scope: str, target_round: int | None) -> list[dict]:
        messages = snapshot.get("messages") or []
        selected = [
            message for message in messages
            if message.get("author_type") == "agent"
        ]
        if scope == "round" and target_round:
            selected = [message for message in selected if int(message.get("round") or 0) == int(target_round)]
        return selected

    def _extract_claim_entries(self, snapshot: dict, messages: list[dict]) -> list[dict]:
        roster = [
            *(snapshot.get("participants", {}).get("active") or []),
            *(snapshot.get("participants", {}).get("benched") or []),
        ]
        by_participant = {item.get("id"): item for item in roster if item.get("id")}
        by_profile = {item.get("profileId"): item for item in roster if item.get("profileId")}
        by_name = {item.get("name"): item for item in roster if item.get("name")}
        claims: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for message in messages:
            participant = (
                by_participant.get(message.get("participant_id") or message.get("participantId"))
                or by_profile.get(message.get("profile_id") or message.get("profileId"))
                or by_name.get(message.get("name") or message.get("agent_name"))
                or {}
            )
            for claim_text in _extract_claims_from_text(message.get("content") or ""):
                dedupe_key = ((message.get("id") or ""), claim_text.lower())
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                claims.append({
                    "messageId": message.get("id"),
                    "roundNumber": message.get("round"),
                    "participantId": message.get("participant_id") or message.get("participantId") or participant.get("id"),
                    "profileId": message.get("profile_id") or message.get("profileId") or participant.get("profileId"),
                    "agentName": message.get("name") or message.get("agent_name") or participant.get("name"),
                    "provider": message.get("provider") or participant.get("provider"),
                    "model": message.get("model") or participant.get("model"),
                    "claimText": claim_text,
                })
        return claims[:18]

    async def _check_single_claim(self, snapshot: dict, claim: dict, internet_mode: str) -> dict:
        room = snapshot["room"]
        graph_id = room.get("graphId")
        graph_text = ""
        if graph_id:
            try:
                graph_text = await asyncio.to_thread(query_graph, graph_id, claim["claimText"], "hybrid", 8)
            except Exception:
                graph_text = ""

        support_sources: list[tuple[str, str, str]] = []
        contradiction_sources: list[tuple[str, str, str]] = []
        weak_sources: list[tuple[str, str, str]] = []

        if graph_text:
            relation = _evaluate_evidence(claim["claimText"], graph_text)
            evidence = _truncate(graph_text, 320)
            if relation == "support":
                support_sources.append(("knowledge", "Документы комнаты", evidence))
            elif relation == "contradict":
                contradiction_sources.append(("knowledge", "Документы комнаты", evidence))
            elif relation == "weak":
                weak_sources.append(("knowledge", "Документы комнаты", evidence))

        external_snippets: list[SearchSnippet] = []
        if internet_mode != "off":
            try:
                external_snippets, _ = await search_external_snippets(
                    claim["claimText"],
                    {"topic": snapshot["session"]["topic"], "internet_mode": internet_mode},
                )
            except Exception:
                external_snippets = []

        for snippet in external_snippets[:4]:
            evidence_text = f"{snippet.title}. {snippet.snippet}".strip()
            relation = _evaluate_evidence(claim["claimText"], evidence_text)
            evidence = _truncate(snippet.as_line(), 320)
            if relation == "support":
                support_sources.append((snippet.source_type, snippet.source_label, evidence))
            elif relation == "contradict":
                contradiction_sources.append((snippet.source_type, snippet.source_label, evidence))
            elif relation == "weak":
                weak_sources.append((snippet.source_type, snippet.source_label, evidence))

        verdict = "insufficient_evidence"
        source_type = ""
        source_label = ""
        evidence = ""
        if support_sources and contradiction_sources:
            verdict = "disputed"
            support = support_sources[0]
            contradict = contradiction_sources[0]
            source_type = "mixed"
            source_label = f"{support[1]} + {contradict[1]}"
            evidence = f"Подтверждение: {support[2]}\nПротиворечие: {contradict[2]}"
        elif support_sources:
            source_type, source_label, evidence = support_sources[0]
            verdict = "confirmed"
        elif contradiction_sources:
            source_type, source_label, evidence = contradiction_sources[0]
            verdict = "contradicted"
        elif weak_sources:
            source_type, source_label, evidence = weak_sources[0]
            verdict = "unverified"
        elif internet_mode == "off" and not graph_text:
            verdict = "insufficient_evidence"
            source_type = "offline"
            source_label = "Офлайн режим"
            evidence = "Внешние источники не использовались, а в документах комнаты подходящих фактов не найдено."

        return {
            **claim,
            "verdict": verdict,
            "evidence": evidence,
            "sourceType": source_type,
            "sourceLabel": source_label,
        }

    def _count_verdicts(self, claims: list[dict]) -> dict[str, int]:
        counts = {
            "confirmed": 0,
            "unverified": 0,
            "contradicted": 0,
            "disputed": 0,
            "insufficient_evidence": 0,
        }
        for claim in claims:
            verdict = str(claim.get("verdict") or "unverified")
            if verdict not in counts:
                verdict = "unverified"
            counts[verdict] += 1
        return counts

    def _build_summary(
        self,
        *,
        counts: dict[str, int],
        scope: str,
        target_round: int | None,
        internet_mode: str,
        external_sources_used: bool,
    ) -> str:
        scope_label = f"раунда {target_round}" if scope == "round" and target_round else "всей сессии"
        suffix = " Внешние источники не использовались." if internet_mode == "off" or not external_sources_used else ""
        return (
            f"Фактчекинг {scope_label}: подтверждено {counts['confirmed']}, "
            f"не подтверждено {counts['unverified']}, опровергнуто {counts['contradicted']}, "
            f"спорно {counts['disputed']}, недостаточно данных {counts['insufficient_evidence']}."
            f"{suffix}"
        )
