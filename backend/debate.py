from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
import re
from dataclasses import dataclass
from typing import Awaitable, Callable

from agents import Agent, AgentConfig, detect_emotion
from chronomancer import Chronomancer
from knowledge.lightrag_adapter import (
    PROFILE_GRAPH_ROOT,
    create_profile_graph,
    insert_text,
    query_graph,
)
from meta_memory import format_insight_recall, select_relevant_session_insights, store_session_memories
from providers import get_provider
from storage import Repository, utc_now
from token_accounting import record_usage


logger = logging.getLogger(__name__)

# Экономия токенов: сколько свежих сообщений стола видит агент целиком.
# Более старые реплики уже сжаты в хронике сессии (session_chronicle).
AGENT_HISTORY_LIMIT = int(os.getenv("AGENT_HISTORY_LIMIT") or 12)

# Кросс-диалог: реакции-перебивания между репликами.
CROSS_DIALOG_ENABLED = os.getenv("CROSS_DIALOG_ENABLED", "1") not in {"0", "false", "no"}
REACTION_CHANCE = float(os.getenv("REACTION_CHANCE") or 0.25)
REACTION_MAX_WORDS = int(os.getenv("REACTION_MAX_WORDS") or 25)

_MENTION_RE = re.compile(r"@([\w][\w\-]{1,30})")


def parse_mentions(text: str, names: list[str]) -> list[str]:
    """Имена участников, явно упомянутые через @Имя."""
    if not text:
        return []
    found = {match.group(1).lower() for match in _MENTION_RE.finditer(text)}
    return [name for name in names if name.lower() in found]


BroadcastFn = Callable[[dict], Awaitable[None]]


@dataclass
class RoundState:
    round_id: str
    round_number: int
    order: list[dict]
    next_index: int = 0


@dataclass
class PreparedTurn:
    room_id: str
    session_id: str
    round_id: str
    round_number: int
    participant: dict
    participant_id: str
    order_index: int
    context_base: dict
    prepared_rag_context: str
    prepared_memory_context: str
    snapshot_signature: str
    history_anchor_id: str | None
    prepared_at: float
    status: str = "ready"


class DebateEngine:
    def __init__(self, broadcast: BroadcastFn, repository: Repository):
        self._broadcast = broadcast
        self.repo = repository
        self.chronomancer = Chronomancer()

        self._task: asyncio.Task | None = None
        self._resume_event = asyncio.Event()
        self._resume_event.set()

        self._running_room_id: str | None = None
        self._running_session_id: str | None = None
        self._state = "idle"
        self._pause_requested = False
        self._stop_requested = False
        self._round_state: RoundState | None = None
        self._round_rag_cache: dict[str, str] = {}
        self._rag_cache_round_id: str | None = None
        self._prepared_turns: dict[tuple[str, int], PreparedTurn] = {}
        self._prep_tasks: dict[tuple[str, int], asyncio.Task] = {}
        self._last_turn_committed_at: float | None = None
        self._round_started_at: float | None = None

    def _density_profile(self, room_id: str | None) -> dict[str, float]:
        snapshot = self.repo.get_room_snapshot(room_id) if room_id else None
        density = (snapshot or {}).get("room", {}).get("densityMode") or "normal"
        if density == "calm":
            return {
                "countdown": 3.0,
                "pre_turn_min": 0.35,
                "pre_turn_max": 0.75,
                "pre_generation_min": 0.55,
                "pre_generation_max": 1.0,
                "between_turn_min": 0.35,
                "between_turn_max": 0.75,
            }
        if density == "stage":
            return {
                "countdown": 1.4,
                "pre_turn_min": 0.08,
                "pre_turn_max": 0.22,
                "pre_generation_min": 0.12,
                "pre_generation_max": 0.35,
                "between_turn_min": 0.08,
                "between_turn_max": 0.2,
            }
        return {
            "countdown": 2.2,
            "pre_turn_min": 0.15,
            "pre_turn_max": 0.4,
            "pre_generation_min": 0.25,
            "pre_generation_max": 0.65,
            "between_turn_min": 0.18,
            "between_turn_max": 0.4,
        }

    def _make_prep_key(self, round_id: str, order_index: int) -> tuple[str, int]:
        return (round_id, order_index)

    def _clear_prepared_turns(self, round_id: str | None = None):
        keys = [
            key
            for key in set(self._prepared_turns) | set(self._prep_tasks)
            if round_id is None or key[0] == round_id
        ]
        for key in keys:
            task = self._prep_tasks.pop(key, None)
            if task and not task.done():
                task.cancel()
        for key in keys:
            self._prepared_turns.pop(key, None)

    def _reset_turn_timing(self):
        self._last_turn_committed_at = None
        self._round_started_at = None

    def _current_inter_turn_gap(self, now: float) -> float | None:
        anchor = self._last_turn_committed_at
        if anchor is None:
            anchor = self._round_started_at
        if anchor is None:
            return None
        return max(0.0, now - anchor)

    def _last_committed_message_id(self, session_id: str) -> str | None:
        latest = self.repo.list_session_messages(session_id, limit=1)
        if not latest:
            return None
        return latest[-1].get("id")

    def _truncate_context_text(self, text: str, limit: int) -> str:
        value = (text or "").strip()
        if len(value) <= limit:
            return value
        clipped = value[:limit].rstrip()
        sentence_end = max(clipped.rfind("."), clipped.rfind("!"), clipped.rfind("?"))
        if sentence_end >= int(limit * 0.6):
            return clipped[:sentence_end + 1].rstrip()
        line_break = clipped.rfind("\n")
        if line_break >= int(limit * 0.6):
            return clipped[:line_break].rstrip()
        whitespace = clipped.rfind(" ")
        if whitespace >= int(limit * 0.6):
            return clipped[:whitespace].rstrip()
        return clipped

    def _build_agent_history(self, session_id: str) -> list[dict]:
        messages = self.repo.list_session_messages(session_id, limit=AGENT_HISTORY_LIMIT)
        history = []
        for message in messages:
            author_type = message.get("author_type")
            if author_type not in {"agent", "user", "system_event"}:
                continue
            history.append({
                "type": message.get("type"),
                "author_type": author_type,
                "agent_name": message.get("agent_name") or message.get("name"),
                "role": message.get("role", "participant"),
                "specialty": message.get("specialty", "generalist"),
                "specialtyLabel": message.get("specialtyLabel"),
                "content": message.get("content", ""),
            })
        return history

    def _build_agent_context_base(
        self,
        room_id: str,
        session_id: str,
        round_id: str,
        round_number: int,
        participant: dict | None = None,
    ) -> dict:
        snapshot = self.repo.get_room_snapshot(room_id)
        session = self.repo.get_session(session_id)
        room = (snapshot or {}).get("room", {})
        return {
            "topic": session["topic"] if session else "",
            "graph_id": room.get("graphId"),
            "internet_mode": room.get("internetMode") or (room.get("settings") or {}).get("internet_mode") or "auto",
            "memory_graph_id": (
                participant.get("memoryGraphId")
                if participant
                else None
            ) or (
                self.repo.get_profile_memory_graph_id(participant["profileId"])
                if participant and participant.get("profileId")
                else None
            ),
            "round_id": round_id,
            "room_name": room.get("name", ""),
            "room_summary": room.get("summary", ""),
            "session_chronicle": session["chronicle"] if session else "",
            "observer_provider": (session or {}).get("observerProvider") or room.get("observerProvider"),
            "observer_model": (session or {}).get("observerModel") or room.get("observerModel"),
            "density_mode": room.get("densityMode", "normal"),
            "tools": room.get("settings", {}),
            "wrap_signal": bool(session and session["wrapRequested"]),
            "final_signal": bool(session and session["finalRoundPlanned"]),
            "round_number": round_number,
            "active_participants": (snapshot or {}).get("participants", {}).get("active", []),
            "pinned_highlights": (snapshot or {}).get("pinnedMessages", []),
        }

    def _build_profile_memory_query(self, participant: dict, ctx: dict) -> str:
        topic = (ctx.get("topic") or "").strip()
        active_names = [
            item.get("name")
            for item in ctx.get("active_participants", [])
            if item.get("name") and item.get("name") != participant.get("name")
        ][:5]
        recent = " ".join(
            (message.get("content") or "").strip()[:160]
            for message in ctx.get("history", [])[-3:]
            if (message.get("content") or "").strip()
        )
        base = f"Моё мнение: {topic}" if topic else ""
        social = f"Совместные обсуждения с: {', '.join(active_names)}" if active_names else ""
        observer = ""
        if ctx.get("observer_provider") and ctx.get("observer_model"):
            observer = f"Наблюдатель: {ctx['observer_provider']}/{ctx['observer_model']}"
        return ". ".join(part for part in [base, social, observer, recent] if part).strip()

    async def _get_profile_memory_context(self, participant: dict, ctx: dict) -> str:
        memory_graph_id = ctx.get("memory_graph_id")
        if not memory_graph_id:
            return ""
        try:
            memory_query = self._build_profile_memory_query(participant, ctx)
            if not memory_query:
                return ""
            memory_context = await asyncio.to_thread(
                query_graph,
                memory_graph_id,
                memory_query,
                "hybrid",
                10,
                root_dir=PROFILE_GRAPH_ROOT,
            )
        except Exception:
            return ""
        return self._truncate_context_text(memory_context or "", limit=4000)

    def _make_turn_snapshot_signature(
        self,
        room_id: str,
        session_id: str,
        round_id: str,
        round_number: int,
        participant_id: str,
    ) -> str:
        snapshot = self.repo.get_room_snapshot(room_id) or {}
        room = snapshot.get("room") or {}
        session = self.repo.get_session(session_id) or {}
        active = snapshot.get("participants", {}).get("active", [])
        signature_payload = {
            "room_id": room_id,
            "session_id": session_id,
            "round_id": round_id,
            "round_number": round_number,
            "participant_id": participant_id,
            "topic": session.get("topic", ""),
            "wrap": bool(session.get("wrapRequested")),
            "final": bool(session.get("finalRoundPlanned")),
            "graph_id": room.get("graphId"),
            "internet_mode": room.get("internetMode") or (room.get("settings") or {}).get("internet_mode") or "auto",
            "density_mode": room.get("densityMode", "normal"),
            "observer_provider": session.get("observerProvider") or room.get("observerProvider"),
            "observer_model": session.get("observerModel") or room.get("observerModel"),
            "active_participants": [
                {
                    "id": item.get("id"),
                    "profileId": item.get("profileId"),
                    "role": item.get("role"),
                    "specialty": item.get("specialty"),
                    "provider": item.get("provider"),
                    "model": item.get("model"),
                }
                for item in active
            ],
        }
        encoded = json.dumps(signature_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return hashlib.sha1(encoded).hexdigest()

    async def _prepare_turn(
        self,
        room_id: str,
        session_id: str,
        round_state: RoundState,
        order_index: int,
        participant: dict,
    ) -> PreparedTurn:
        participant_snapshot = dict(participant)
        context_base = self._build_agent_context_base(
            room_id,
            session_id,
            round_state.round_id,
            round_state.round_number,
            participant=participant_snapshot,
        )
        history = self._build_agent_history(session_id)
        prep_context = {**context_base, "history": history}
        rag_task = asyncio.create_task(self._get_round_rag_context(round_state.round_id, prep_context))
        memory_task = asyncio.create_task(self._get_profile_memory_context(participant_snapshot, prep_context))
        prepared_rag_context, prepared_memory_context = await asyncio.gather(rag_task, memory_task)
        return PreparedTurn(
            room_id=room_id,
            session_id=session_id,
            round_id=round_state.round_id,
            round_number=round_state.round_number,
            participant=participant_snapshot,
            participant_id=participant_snapshot["id"],
            order_index=order_index,
            context_base=context_base,
            prepared_rag_context=prepared_rag_context or "",
            prepared_memory_context=prepared_memory_context or "",
            snapshot_signature=self._make_turn_snapshot_signature(
                room_id,
                session_id,
                round_state.round_id,
                round_state.round_number,
                participant_snapshot["id"],
            ),
            history_anchor_id=self._last_committed_message_id(session_id),
            prepared_at=asyncio.get_running_loop().time(),
        )

    def _is_prepared_turn_valid(self, prepared: PreparedTurn, round_state: RoundState | None) -> bool:
        if self._stop_requested or self._pause_requested:
            return False
        if not round_state:
            return False
        if round_state.round_id != prepared.round_id or round_state.round_number != prepared.round_number:
            return False
        if prepared.order_index >= len(round_state.order):
            return False
        participant = round_state.order[prepared.order_index]
        if participant["id"] != prepared.participant_id:
            return False
        current_signature = self._make_turn_snapshot_signature(
            prepared.room_id,
            prepared.session_id,
            prepared.round_id,
            prepared.round_number,
            prepared.participant_id,
        )
        return current_signature == prepared.snapshot_signature

    async def _prepare_turn_task(
        self,
        room_id: str,
        session_id: str,
        round_state: RoundState,
        order_index: int,
        participant: dict,
    ):
        key = self._make_prep_key(round_state.round_id, order_index)
        try:
            prepared = await self._prepare_turn(room_id, session_id, round_state, order_index, participant)
        except asyncio.CancelledError:
            raise
        except Exception:
            return
        finally:
            self._prep_tasks.pop(key, None)
        if self._is_prepared_turn_valid(prepared, self._round_state):
            self._prepared_turns[key] = prepared

    def _seed_prepared_turn(self, room_id: str, session_id: str, round_state: RoundState | None, order_index: int):
        if not round_state or order_index >= len(round_state.order):
            return
        key = self._make_prep_key(round_state.round_id, order_index)
        if key in self._prepared_turns or key in self._prep_tasks:
            return
        participant = round_state.order[order_index]
        self._prep_tasks[key] = asyncio.create_task(
            self._prepare_turn_task(room_id, session_id, round_state, order_index, participant)
        )

    async def _ensure_prepared_turn(
        self,
        room_id: str,
        session_id: str,
        round_state: RoundState,
        order_index: int,
    ) -> PreparedTurn:
        key = self._make_prep_key(round_state.round_id, order_index)
        task = self._prep_tasks.get(key)
        if task:
            try:
                await task
            except asyncio.CancelledError:
                pass
        prepared = self._prepared_turns.get(key)
        if prepared and self._is_prepared_turn_valid(prepared, round_state):
            return prepared
        self._prepared_turns.pop(key, None)
        participant = round_state.order[order_index]
        prepared = await self._prepare_turn(room_id, session_id, round_state, order_index, participant)
        self._prepared_turns[key] = prepared
        return prepared

    def _compose_prepared_context(self, prepared: PreparedTurn) -> dict:
        return {
            **prepared.context_base,
            "history": self._build_agent_history(prepared.session_id),
            "rag_context": prepared.prepared_rag_context,
            "memory_context": prepared.prepared_memory_context,
        }

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def state(self) -> str:
        return self._state

    @property
    def current_room_id(self) -> str | None:
        return self._running_room_id or self.repo.get_current_room_id()

    @property
    def current_session_id(self) -> str | None:
        return self._running_session_id

    def _resolve_session_context(self, room_id: str | None = None) -> tuple[str | None, str | None, dict | None]:
        target_room_id = room_id or self._running_room_id or self.repo.get_current_room_id()
        if not target_room_id:
            return None, None, None

        if self._running_session_id:
            return target_room_id, self._running_session_id, self.repo.get_session(self._running_session_id)

        snapshot = self.repo.get_room_snapshot(target_room_id)
        session = snapshot["session"] if snapshot else None
        if not session or session["status"] in {"completed", "stopped"}:
            return target_room_id, None, None
        return target_room_id, session["id"], session

    async def shutdown(self):
        await self.stop_session()

    async def load_room(self, room_id: str | None = None):
        target_room_id = room_id or self.repo.get_current_room_id()
        if not target_room_id:
            return
        if self.running and self._running_room_id and target_room_id != self._running_room_id:
            await self._broadcast({
                "type": "error",
                "message": "Сначала завершите или поставьте на паузу текущую сессию, а потом переключайте комнату.",
            })
            return
        self.repo.set_current_room(target_room_id)
        await self._broadcast_room_loaded(target_room_id)

    async def load_session(self, session_id: str | None = None):
        if not session_id:
            return
        snapshot = self.repo.get_session_snapshot(session_id)
        if not snapshot:
            await self._broadcast({"type": "error", "message": "Сессия не найдена."})
            return
        room_id = snapshot["room"]["id"]
        if self.running and self._running_room_id and room_id != self._running_room_id:
            await self._broadcast({
                "type": "error",
                "message": "Сначала завершите или поставьте на паузу текущую сессию, а потом открывайте другой диалог.",
            })
            return
        snapshot = self.repo.set_current_session(session_id)
        session = snapshot["session"] if snapshot else None
        if not self.running and session:
            self._running_room_id = room_id
            self._running_session_id = None if session["status"] in {"completed", "stopped"} else session["id"]
            self._state = session["status"]
        await self._broadcast({
            "type": "room_loaded",
            "rooms": self.repo.list_rooms(),
            "currentRoomId": room_id,
            **snapshot,
        })
        await self._broadcast_session_state(session)

    async def continue_session(self, session_id: str | None = None):
        if not session_id:
            return
        snapshot = self.repo.get_session_snapshot(session_id)
        if not snapshot:
            await self._broadcast({"type": "error", "message": "Сессия не найдена."})
            return
        room_id = snapshot["room"]["id"]

        if self.running:
            await self.stop_session()

        session = snapshot["session"]
        self.repo.set_current_session(session_id)
        self.repo.update_session(
            session_id,
            {
                "status": "running",
                "wrapRequested": 0,
                "finalRequested": 0,
                "finalRoundPlanned": 0,
                "endedAt": None,
            },
        )
        self.repo.add_room_event(room_id, session_id, "session_continued", {"fromStatus": session["status"]})
        self._running_room_id = room_id
        self._running_session_id = session_id
        self._state = "running"
        self._pause_requested = False
        self._stop_requested = False
        self._round_state = None
        self._resume_event.set()
        await self._append_and_broadcast(
            room_id,
            session_id,
            {
                "type": "status",
                "content": "Сессия продолжена из архива.",
            },
            message_type="status",
        )
        await self._broadcast_room_loaded(room_id)
        await self._broadcast_session_state()
        self._task = asyncio.create_task(self._loop(room_id, session_id))

    async def start_session(self, topic: str | None = None, room_id: str | None = None, observer_mode: str | None = None):
        target_room_id = room_id or self.repo.get_current_room_id()
        if not target_room_id:
            return

        active = self.repo.get_active_participants(target_room_id)
        if len(active) < 2:
            await self._broadcast({
                "type": "error",
                "message": "Для запуска нужны хотя бы два активных участника.",
            })
            return

        if self.running:
            await self.stop_session()

        snapshot = self.repo.get_room_snapshot(target_room_id)
        if not snapshot:
            return

        final_topic = (topic or snapshot["room"]["lastTopic"] or "Новая тема для обсуждения").strip()
        final_observer_mode = observer_mode or snapshot["room"]["observerMode"] or "suggest"
        session = self.repo.create_session(target_room_id, final_topic, final_observer_mode)

        self._running_room_id = target_room_id
        self._running_session_id = session["id"]
        self._state = "running"
        self._pause_requested = False
        self._stop_requested = False
        self._round_state = None
        self._resume_event.set()

        self.repo.add_room_event(target_room_id, session["id"], "session_started", {"topic": final_topic})
        await self._append_and_broadcast(
            target_room_id,
            session["id"],
            {
                "type": "status",
                "content": f"Сессия запущена: {final_topic}",
            },
            message_type="status",
        )
        await self._broadcast_room_loaded(target_room_id)
        await self._broadcast_session_state()
        self._task = asyncio.create_task(self._loop(target_room_id, session["id"]))

    async def pause_session(self):
        if not self.running or self._state in {"paused", "pause_requested"}:
            return

        self._pause_requested = True
        self._state = "pause_requested"
        if self._running_session_id:
            self.repo.update_session(self._running_session_id, {"status": "pause_requested"})
        await self._broadcast({"type": "pause_requested"})
        await self._broadcast_session_state()

    async def resume_session(self, room_id: str | None = None):
        if self._state == "paused":
            self._pause_requested = False
            self._state = "running"
            if self._running_session_id:
                self.repo.update_session(self._running_session_id, {"status": "running"})
            self._resume_event.set()
            await self._broadcast({"type": "resumed"})
            await self._broadcast_session_state()
            return

        if self.running:
            return

        target_room_id = room_id or self.repo.get_current_room_id()
        if not target_room_id:
            return

        snapshot = self.repo.get_room_snapshot(target_room_id)
        session = snapshot["session"] if snapshot else None
        if not session or session["status"] not in {"paused", "pause_requested", "running", "observer_review", "finalizing"}:
            return

        self._running_room_id = target_room_id
        self._running_session_id = session["id"]
        self._state = "running"
        self._pause_requested = False
        self._stop_requested = False
        self._round_state = None
        self._resume_event.set()
        self.repo.update_session(session["id"], {"status": "running"})
        await self._broadcast({"type": "resumed"})
        await self._broadcast_session_state()
        self._task = asyncio.create_task(self._loop(target_room_id, session["id"]))

    async def stop_session(self):
        session = None
        self._stop_requested = True
        self._pause_requested = False
        self._resume_event.set()

        if self._task and not self._task.done():
            await self._task

        if self._running_session_id:
            session = self.repo.get_session(self._running_session_id)
            if session and session["status"] not in {"completed", "stopped"}:
                self.repo.update_session(
                    self._running_session_id,
                    {
                        "status": "stopped",
                        "endedAt": utc_now(),
                    },
                )
                session = self.repo.get_session(self._running_session_id)
            if session:
                self._state = session["status"]
            else:
                self._state = "idle"
        self._task = None
        self._round_state = None
        await self._broadcast_session_state(session)
        if self._running_room_id:
            await self._broadcast_room_loaded(self._running_room_id)

    async def request_wrap(self):
        room_id, session_id, session = self._resolve_session_context()
        if not session_id:
            return
        self.repo.update_session(session_id, {"wrapRequested": 1})
        session = self.repo.get_session(session_id)
        await self._append_and_broadcast(
            room_id,
            session_id,
            {
                "type": "status",
                "content": "Пользователь дал сигнал закругляться.",
            },
            message_type="status",
        )
        await self._broadcast({
            "type": "observer_suggestion",
            "recommendation": "suggest_final",
            "summary": "Столу пора двигаться к общему выводу.",
            "suggestedRoundsLeft": 1,
        })
        if session:
            await self._broadcast_session_state(session=session)

    async def request_final_round(self):
        room_id, session_id, _ = self._resolve_session_context()
        if not session_id:
            return
        next_status = "finalizing" if self._running_session_id else "paused"
        self.repo.update_session(
            session_id,
            {
                "wrapRequested": 1,
                "finalRequested": 1,
                "finalRoundPlanned": 1,
                "status": next_status,
            },
        )
        await self._append_and_broadcast(
            room_id,
            session_id,
            {
                "type": "status",
                "content": "Следующий раунд объявлен финальным.",
            },
            message_type="status",
        )
        await self._broadcast({
            "type": "observer_suggestion",
            "recommendation": "final_round",
            "summary": "Хрономант переводит стол в финальный раунд.",
            "suggestedRoundsLeft": 1,
        })
        await self._broadcast_session_state()

    async def submit_user_question(self, content: str):
        room_id, session_id, session = self._resolve_session_context()
        if not room_id or not session_id:
            return
        effective_paused = self._state == "paused" or (not self._running_session_id and session and session["status"] == "paused")
        if not effective_paused:
            await self._broadcast({"type": "error", "message": "Вопрос в комнату можно добавить во время паузы."})
            return
        text = (content or "").strip()
        if not text:
            return
        round_number = (session["lastRoundNumber"] + 1) if session else 1
        payload = {
            "type": "user_question",
            "name": "Вы",
            "emoji": "📝",
            "content": text,
            "round": round_number,
            "author_type": "user",
            "agent_name": "Пользователь",
            "role": "user",
            "specialty": "prompt",
        }
        stored = self.repo.append_message(
            room_id,
            session_id,
            payload,
            round_number=round_number,
            message_type="user_question",
            author_type="user",
        )
        self.repo.add_room_event(
            room_id,
            session_id,
            "user_question",
            {"content": text},
        )
        await self._broadcast({"type": "user_question_accepted", "message": stored})
        await self._broadcast(stored)

    async def add_participant_from_inventory(self, room_id: str, profile_id: str):
        if self.running and self._state != "paused":
            await self._broadcast({"type": "error", "message": "Менять состав можно только до старта или на паузе."})
            return
        participant_id = self.repo.add_participant_from_profile(room_id, profile_id, status="active")
        if not participant_id:
            return
        participant = self.repo.get_participant(participant_id)
        session_id = self._running_session_id if room_id == self._running_room_id else None
        self.repo.add_room_event(room_id, session_id, "participant_added", participant)
        await self._broadcast_roster_change(room_id, "добавлен", participant)

    async def create_and_add_participant(self, room_id: str, data: dict, save_to_inventory: bool):
        if self.running and self._state != "paused":
            await self._broadcast({"type": "error", "message": "Менять состав можно только до старта или на паузе."})
            return
        participant_id = self.repo.create_and_add_participant(room_id, data, save_to_inventory)
        if not participant_id:
            return
        participant = self.repo.get_participant(participant_id)
        session_id = self._running_session_id if room_id == self._running_room_id else None
        self.repo.add_room_event(room_id, session_id, "participant_added", participant)
        await self._broadcast_roster_change(room_id, "добавлен", participant)

    async def bench_participant(self, participant_id: str):
        if self.running and self._state != "paused":
            await self._broadcast({"type": "error", "message": "Менять состав можно только до старта или на паузе."})
            return
        participant = self.repo.get_participant(participant_id)
        if not participant:
            return
        room_id = self.repo.get_current_room_id()
        self.repo.bench_participant(participant_id)
        self.repo.add_room_event(room_id, self._running_session_id, "participant_benched", participant)
        await self._broadcast_roster_change(room_id, "на скамейке", participant)

    async def restore_participant(self, participant_id: str):
        if self.running and self._state != "paused":
            await self._broadcast({"type": "error", "message": "Менять состав можно только до старта или на паузе."})
            return
        participant = self.repo.get_participant(participant_id)
        if not participant:
            return
        room_id = self.repo.get_current_room_id()
        self.repo.restore_participant(participant_id)
        restored = self.repo.get_participant(participant_id)
        self.repo.add_room_event(room_id, self._running_session_id, "participant_restored", restored)
        await self._broadcast_roster_change(room_id, "возвращён", restored)

    async def set_observer_mode(self, room_id: str, mode: str):
        self.repo.update_room_settings(room_id, observer_mode=mode)
        if self._running_session_id and room_id == self._running_room_id:
            self.repo.update_session(self._running_session_id, {"observerMode": mode})
        await self._broadcast_room_loaded(room_id)
        await self._broadcast_session_state()

    async def reset(self):
        await self.stop_session()
        current_room_id = self.repo.get_current_room_id()
        if current_room_id:
            await self._broadcast_room_loaded(current_room_id)
        await self._broadcast({"type": "reset"})

    def update_agents(self, agents_cfg: list[dict]):
        room_id = self.repo.get_current_room_id()
        if not room_id:
            return

        snapshot = self.repo.get_room_snapshot(room_id)
        active = snapshot["participants"]["active"] if snapshot else []
        active_ids = [item["id"] for item in active]
        for participant_id in active_ids:
            self.repo.bench_participant(participant_id)

        for index, cfg in enumerate(agents_cfg):
            participant_id = self.repo.create_and_add_participant(room_id, cfg, save_to_inventory=False)
            if participant_id:
                self.repo.update_participant(participant_id, {"position": index})

    async def start(self, topic: str, agents_cfg: list[dict]):
        self.update_agents(agents_cfg)
        await self.start_session(topic=topic)

    async def stop(self):
        await self.stop_session()

    async def _loop(self, room_id: str, session_id: str):
        try:
            while not self._stop_requested:
                session = self.repo.get_session(session_id)
                if not session:
                    break

                if self._round_state is None:
                    active = self.repo.get_active_participants(room_id)
                    if len(active) < 2:
                        await self._append_and_broadcast(
                            room_id,
                            session_id,
                            {
                                "type": "status",
                                "content": "Сессия остановлена: за столом осталось меньше двух активных участников.",
                            },
                            message_type="status",
                        )
                        await self._complete_session("stopped")
                        break

                    round_number = session["lastRoundNumber"] + 1
                    round_id = self.repo.create_round(room_id, session_id, round_number)
                    order = active[:]
                    random.shuffle(order)
                    self._round_state = RoundState(round_id=round_id, round_number=round_number, order=order)
                    self._clear_round_rag_cache(round_id)
                    density = self._density_profile(room_id)
                    countdown = density["countdown"]
                    await self._broadcast({"type": "countdown", "round": round_number, "seconds": round(countdown)})
                    await asyncio.sleep(countdown)
                    await self._broadcast({"type": "round_start", "round": round_number})
                    await self._inject_planned_events(room_id, session_id, round_id, round_number)
                    self._last_turn_committed_at = None
                    self._round_started_at = asyncio.get_running_loop().time()
                    self._seed_prepared_turn(room_id, session_id, self._round_state, 0)

                while self._round_state and self._round_state.next_index < len(self._round_state.order):
                    if self._pause_requested:
                        await self._enter_paused()
                        if self._stop_requested:
                            break

                    current_index = self._round_state.next_index
                    prepared = await self._ensure_prepared_turn(
                        room_id,
                        session_id,
                        self._round_state,
                        current_index,
                    )
                    self._prepared_turns.pop(self._make_prep_key(prepared.round_id, prepared.order_index), None)
                    self._seed_prepared_turn(room_id, session_id, self._round_state, current_index + 1)
                    await self._execute_prepared_turn(prepared)
                    self._round_state.next_index += 1

                    if self._stop_requested:
                        break

                    if self._round_state.next_index < len(self._round_state.order):
                        await self._maybe_reaction(room_id, session_id, self._round_state, prepared.participant)
                        density = self._density_profile(room_id)
                        await asyncio.sleep(random.uniform(density["between_turn_min"], density["between_turn_max"]))

                if self._stop_requested:
                    break

                if not self._round_state:
                    continue

                review = await self._review_round(room_id, session_id, self._round_state)
                self._round_state = None
                self._clear_prepared_turns()
                self._reset_turn_timing()

                if review["recommendation"] == "complete":
                    await self._complete_session("completed", review)
                    break

                if self._pause_requested:
                    await self._enter_paused()
                    if self._stop_requested:
                        break

            if self._stop_requested and self._running_session_id:
                await self._complete_session("stopped")
        except asyncio.CancelledError:
            raise
        finally:
            final_session = self.repo.get_session(self._running_session_id) if self._running_session_id else None
            self._task = None
            if final_session and final_session["status"] in {"completed", "stopped"}:
                self._state = final_session["status"]
            else:
                self._state = "idle"
            self._pause_requested = False
            self._stop_requested = False
            self._resume_event.set()
            self._round_state = None
            self._clear_prepared_turns()
            self._reset_turn_timing()
            await self._broadcast_session_state(final_session)

    async def _enter_paused(self):
        if not self._running_session_id:
            return
        self._clear_prepared_turns()
        self._reset_turn_timing()
        self._state = "paused"
        self.repo.update_session(self._running_session_id, {"status": "paused"})
        self._resume_event.clear()
        await self._broadcast({"type": "paused"})
        await self._broadcast_session_state()
        await self._resume_event.wait()
        if self._round_state and not self._stop_requested:
            self._round_started_at = asyncio.get_running_loop().time()

    async def _execute_prepared_turn(self, prepared: PreparedTurn):
        loop = asyncio.get_running_loop()
        density = self._density_profile(prepared.room_id)
        await asyncio.sleep(random.uniform(density["pre_turn_min"], density["pre_turn_max"]))
        if self._stop_requested:
            return

        thinking_started_at = loop.time()
        inter_turn_gap_seconds = self._current_inter_turn_gap(thinking_started_at)
        await self._broadcast({
            "type": "agent_thinking",
            "agent_id": prepared.participant_id,
        })

        await asyncio.sleep(random.uniform(density["pre_generation_min"], density["pre_generation_max"]))
        if self._stop_requested:
            return

        if not self._is_prepared_turn_valid(prepared, self._round_state):
            refreshed = await self._ensure_prepared_turn(
                prepared.room_id,
                prepared.session_id,
                self._round_state,
                prepared.order_index,
            )
            self._prepared_turns.pop(self._make_prep_key(refreshed.round_id, refreshed.order_index), None)
            prepared = refreshed

        participant = prepared.participant
        agent = Agent(AgentConfig(
            id=participant["id"],
            profile_id=participant["profileId"],
            name=participant["name"],
            role=participant["role"],
            specialty=participant["specialty"],
            specialty_label=participant.get("specialtyLabel") or "",
            provider=participant["provider"],
            model=participant["model"],
            emoji=participant["emoji"],
            mascot=participant["mascot"],
        ))

        context = self._compose_prepared_context(prepared)
        accumulated = ""

        async def on_token(token: str):
            nonlocal accumulated
            accumulated += token
            await self._broadcast({
                "type": "agent_token",
                "agent_id": prepared.participant_id,
                "token": token,
            })

        response_started_at = loop.time()
        try:
            await agent.generate(context, on_token=on_token)
        except Exception as exc:
            await self._broadcast({
                "type": "error",
                "agent_id": prepared.participant_id,
                "message": str(exc),
            })
            return

        if not accumulated.strip():
            accumulated = "(без ответа)"
        response_seconds = max(0.1, loop.time() - response_started_at)
        await self._commit_turn_result(
            prepared,
            agent,
            context,
            accumulated,
            response_seconds,
            inter_turn_gap_seconds,
        )

    async def _commit_turn_result(
        self,
        prepared: PreparedTurn,
        agent: Agent,
        context: dict,
        accumulated: str,
        response_seconds: float,
        inter_turn_gap_seconds: float | None,
    ):
        participant = prepared.participant
        mentions = parse_mentions(
            accumulated,
            [item.get("name") or "" for item in self._round_state.order]
            if self._round_state else [],
        )
        payload = {
            "type": "agent_message",
            "agent_id": participant["id"],
            "participant_id": participant["id"],
            "profile_id": participant["profileId"],
            "agent_name": participant["name"],
            "name": participant["name"],
            "agent_emoji": participant["emoji"],
            "emoji": participant["emoji"],
            "mascot": participant["mascot"],
            "role": participant["role"],
            "specialty": participant["specialty"],
            "specialtyLabel": participant.get("specialtyLabel"),
            "provider": participant.get("provider"),
            "model": participant.get("model"),
            "content": accumulated,
            "emotion": detect_emotion(accumulated),
            "responseSeconds": round(response_seconds, 1),
            "round": prepared.round_number,
            "author_type": "agent",
        }
        if mentions:
            payload["mentions"] = mentions
        if inter_turn_gap_seconds is not None:
            payload["interTurnGapSeconds"] = round(inter_turn_gap_seconds, 1)
        if agent.last_tool_call:
            payload["toolCalls"] = [agent.last_tool_call]
        stored = self.repo.append_message(
            prepared.room_id,
            prepared.session_id,
            payload,
            round_id=prepared.round_id,
            round_number=prepared.round_number,
            message_type="agent_message",
            author_type="agent",
            participant_id=participant["id"],
        )
        if agent.last_tool_call:
            self.repo.add_room_event(
                prepared.room_id,
                prepared.session_id,
                "tool_used",
                {
                    "participantId": participant["id"],
                    "profileId": participant["profileId"],
                    "tool": agent.last_tool_call.get("tool"),
                    "query": agent.last_tool_call.get("query"),
                    "ok": agent.last_tool_call.get("ok", True),
                },
            )
        timing_payload = {
            "participantId": participant["id"],
            "profileId": participant["profileId"],
            "round": prepared.round_number,
            "responseSeconds": round(response_seconds, 1),
        }
        if inter_turn_gap_seconds is not None:
            timing_payload["interTurnGapSeconds"] = round(inter_turn_gap_seconds, 1)
        self.repo.add_room_event(
            prepared.room_id,
            prepared.session_id,
            "turn_timing",
            timing_payload,
        )
        await self._broadcast(stored)
        if mentions and self._round_state and self._round_state.round_id == prepared.round_id:
            self._apply_mention_priority(self._round_state, mentions)
        self._last_message_for_reaction = {
            "speaker": participant,
            "content": accumulated,
            "mentions": mentions,
        }
        record_usage(
            self.repo,
            session_id=prepared.session_id,
            room_id=prepared.room_id,
            round_number=prepared.round_number,
            kind="agent_message",
            provider=participant.get("provider"),
            model=participant.get("model"),
            prompt_text="\n".join(
                str(item.get("content") or "")
                for item in (context.get("history") or [])
            ) + (context.get("session_chronicle") or ""),
            completion_text=accumulated,
        )
        self._last_turn_committed_at = asyncio.get_running_loop().time()
        self._round_started_at = None

    def _apply_mention_priority(self, round_state: RoundState, mentions: list[str]):
        """Адресованный в @упоминании получает слово следующим (обмен позициями)."""
        start = round_state.next_index
        if start >= len(round_state.order) - 0 or start >= len(round_state.order):
            return
        current = round_state.order[start]
        if (current.get("name") or "").lower() in {m.lower() for m in mentions}:
            return
        for idx in range(start + 1, len(round_state.order)):
            candidate = round_state.order[idx]
            if (candidate.get("name") or "").lower() in {m.lower() for m in mentions}:
                round_state.order[start], round_state.order[idx] = candidate, current
                break

    async def _maybe_reaction(self, room_id, session_id, round_state: RoundState, speaker_participant: dict):
        """Короткая реакция-перебивание от другого агента между репликами."""
        if not CROSS_DIALOG_ENABLED:
            return None
        enabled = self.repo.get_setting("cross_dialog_enabled")
        if enabled is not None and str(enabled).strip() != "" and str(enabled).strip().lower() in {"0", "false", "no"}:
            return None
        chance = REACTION_CHANCE
        raw_chance = self.repo.get_setting("reaction_chance")
        if raw_chance not in (None, ""):
            try:
                chance = max(0.0, min(float(raw_chance), 1.0))
            except (TypeError, ValueError):
                pass
        last = getattr(self, "_last_message_for_reaction", None)
        if not last or random.random() > chance:
            return None

        candidates = [
            item for item in round_state.order
            if (item.get("name") or "") != (speaker_participant.get("name") or "")
        ]
        if not candidates:
            return None
        next_idx = min(round_state.next_index, len(round_state.order) - 1)
        next_scheduled_id = round_state.order[next_idx].get("id")
        mention_names = {(item or "").lower() for item in last.get("mentions") or []}
        weights = []
        for item in candidates:
            weight = 3.0 if (item.get("name") or "").lower() in mention_names else 1.0
            if item.get("id") == next_scheduled_id:
                weight *= 0.15
            weights.append(weight)
        reactor = random.choices(candidates, weights=weights, k=1)[0]

        prompt = (
            f"Ты {reactor.get('name')}. Только что выступил {speaker_participant.get('name')}:\n"
            f"«{(last.get('content') or '')[:400]}»\n\n"
            f"Ответь ОДНОЙ короткой фразой (до {REACTION_MAX_WORDS} слов): живое согласие, "
            f"возражение или острая деталь по сути. Без приветствий и представлений."
        )
        try:
            provider = get_provider(reactor.get("provider") or "ollama")
            raw_text = await asyncio.wait_for(
                provider.stream_chat(reactor.get("model") or "", [{"role": "user", "content": prompt}], None),
                timeout=45,
            )
        except Exception:
            logger.warning("Реакция %s не удалась", reactor.get("name"), exc_info=True)
            return None
        text = (raw_text or "").strip().splitlines()[0].strip().strip('"«»')
        if not text:
            return None
        words = text.split()
        if len(words) > REACTION_MAX_WORDS:
            text = " ".join(words[:REACTION_MAX_WORDS]) + "…"

        payload = {
            "type": "agent_reaction",
            "agent_id": reactor["id"],
            "participant_id": reactor["id"],
            "profile_id": reactor.get("profileId"),
            "agent_name": reactor.get("name"),
            "name": reactor.get("name"),
            "agent_emoji": reactor.get("emoji"),
            "emoji": reactor.get("emoji"),
            "mascot": reactor.get("mascot"),
            "role": reactor.get("role"),
            "specialty": reactor.get("specialty"),
            "specialtyLabel": reactor.get("specialtyLabel"),
            "provider": reactor.get("provider"),
            "model": reactor.get("model"),
            "content": text,
            "replyTo": speaker_participant.get("name"),
            "emotion": detect_emotion(text),
            "round": round_state.round_number,
            "author_type": "agent",
        }
        stored = self.repo.append_message(
            room_id,
            session_id,
            payload,
            round_id=round_state.round_id,
            round_number=round_state.round_number,
            message_type="agent_reaction",
            author_type="agent",
            participant_id=reactor["id"],
        )
        record_usage(
            self.repo,
            session_id=session_id,
            room_id=room_id,
            round_number=round_state.round_number,
            kind="agent_reaction",
            provider=reactor.get("provider"),
            model=reactor.get("model"),
            prompt_text=prompt,
            completion_text=text,
        )
        await self._broadcast(stored)
        return stored
        await self._store_profile_memory(prepared.room_id, prepared.round_number, participant, context, accumulated)

    async def _inject_planned_events(self, room_id: str, session_id: str, round_id: str, round_number: int):
        events = self.repo.get_pending_events(room_id, session_id, round_number)
        for event in events:
            payload = {
                "type": "system_event",
                "agent_id": "system_event",
                "participant_id": "system_event",
                "profile_id": "system_event",
                "agent_name": "⚡ Событие",
                "name": "⚡ Событие",
                "agent_emoji": "⚡",
                "emoji": "⚡",
                "mascot": None,
                "role": "system",
                "specialty": "",
                "content": event["description"],
                "round": round_number,
                "eventId": event["id"],
                "author_type": "system_event",
            }
            stored = self.repo.append_message(
                room_id,
                session_id,
                payload,
                round_id=round_id,
                round_number=round_number,
                message_type="system_event",
                author_type="system_event",
            )
            fired_event = self.repo.mark_event_fired(event["id"]) or event
            self.repo.add_room_event(
                room_id,
                session_id,
                "event_injected",
                {"plannedEventId": event["id"], "round": round_number, "description": event["description"]},
            )
            await self._broadcast(stored)
            await self._broadcast({
                "type": "event_injected",
                "round": round_number,
                "description": event["description"],
                "event": fired_event,
                "message": stored,
                "plannedEvents": self.repo.list_planned_events(room_id, session_id),
            })

    async def _review_round(self, room_id: str, session_id: str, round_state: RoundState) -> dict:
        self._state = "observer_review"
        self.repo.update_session(session_id, {"status": "observer_review"})
        await self._broadcast_session_state()
        await self._broadcast({"type": "observer_review_started", "round": round_state.round_number})

        session = self.repo.get_session(session_id)
        snapshot = self.repo.get_room_snapshot(room_id)
        room = snapshot["room"] if snapshot else {}
        events = self.repo.list_recent_room_events(room_id, session_id, limit=8)
        participants = round_state.order
        observer_provider = session.get("observerProvider") or room.get("observerProvider")
        observer_model = session.get("observerModel") or room.get("observerModel")
        curated_recall = ""
        try:
            recent_insights = self.repo.list_session_insights(
                observer_provider=observer_provider,
                observer_model=observer_model,
                limit=48,
            )
            relevant_insights = select_relevant_session_insights(
                recent_insights,
                topic=session["topic"],
                participants=participants,
                observer_provider=observer_provider,
                observer_model=observer_model,
                audience="observer",
                limit=3,
            )
            curated_recall = format_insight_recall(
                relevant_insights,
                audience="observer",
                limit=1200,
            )
        except Exception:
            curated_recall = ""
        review = await self.chronomancer.review_round(
            topic=session["topic"],
            observer_provider=observer_provider,
            observer_model=observer_model,
            observer_mode=session["observerMode"],
            chronicle=session["chronicle"],
            round_number=round_state.round_number,
            round_messages=self.repo.list_round_messages(session_id, round_state.round_number),
            participants=participants,
            room_events=events,
            wrap_requested=session["wrapRequested"],
            final_round_planned=session["finalRoundPlanned"],
            extension_count=session["extensionCount"],
            curated_recall=curated_recall,
        )

        self.repo.complete_round(round_state.round_id, review)
        self.repo.save_observer_review(room_id, session_id, round_state.round_id, round_state.round_number, review)
        self.repo.apply_stats_delta(review.get("statsDelta", {}), review.get("participantComments", {}))
        record_usage(
            self.repo,
            session_id=session_id,
            room_id=room_id,
            round_number=round_state.round_number,
            kind="observer_review",
            provider=observer_provider,
            model=observer_model,
            prompt_text=(session["chronicle"] or "") + "\n".join(
                str(msg.get("content") or "")
                for msg in self.repo.list_round_messages(session_id, round_state.round_number)
            ),
            completion_text=json.dumps(review.get("summary") or "", ensure_ascii=False)
            + (review.get("chronicle") or ""),
        )

        next_fields = {
            "chronicle": review["chronicle"],
            "lastRoundNumber": round_state.round_number,
            "status": "running",
        }

        recommendation = review.get("recommendation", "continue")
        observer_mode = session["observerMode"]
        should_complete = bool(session["finalRoundPlanned"])

        if session["finalRoundPlanned"]:
            should_complete = True
            recommendation = "complete"
        elif observer_mode == "auto":
            if recommendation == "final_round":
                next_fields["finalRoundPlanned"] = 1
                next_fields["status"] = "finalizing"
                next_fields["extensionCount"] = min(session["extensionCount"] + 1, 3)
            elif recommendation == "suggest_final":
                if session["extensionCount"] >= 2:
                    next_fields["finalRoundPlanned"] = 1
                    next_fields["status"] = "finalizing"
                else:
                    next_fields["wrapRequested"] = 1
                    next_fields["extensionCount"] = session["extensionCount"] + 1
            elif recommendation == "complete":
                should_complete = True

        self.repo.update_session(session_id, next_fields)
        self.repo.update_room_settings(room_id, summary=review["chronicle"], last_topic=session["topic"])
        self._state = next_fields["status"]
        await self._broadcast_session_state(self.repo.get_session(session_id))

        if review.get("tableComment"):
            observer_payload = {
                "type": "observer_note",
                "name": "Хрономант",
                "emoji": "⏳",
                "content": review["tableComment"],
                "round": round_state.round_number,
                "recommendation": recommendation,
                "suggestedRoundsLeft": review.get("suggestedRoundsLeft"),
                "author_type": "observer",
                "agent_name": "Хрономант",
                "role": "observer",
                "specialty": "chronomancer",
            }
            stored = self.repo.append_message(
                room_id,
                session_id,
                observer_payload,
                round_id=round_state.round_id,
                round_number=round_state.round_number,
                message_type="observer_note",
                author_type="observer",
            )
            await self._broadcast(stored)

        await self._broadcast({
            "type": "round_completed",
            "round": round_state.round_number,
            "summary": review["roundSummary"],
            "progress": review.get("progress", {}),
            "finalReason": review.get("finalReason", ""),
        })
        await self._broadcast({
            "type": "observer_review_completed",
            "round": round_state.round_number,
            "review": review,
        })
        await self._broadcast({
            "type": "participant_stats_updated",
            "inventory": self.repo.list_saved_profiles(),
            "participants": self.repo.get_room_snapshot(room_id)["participants"],
        })

        if observer_mode != "manual" and recommendation in {"suggest_final", "final_round"}:
            await self._broadcast({
                "type": "observer_suggestion",
                "recommendation": recommendation,
                "summary": review.get("finalReason") or review.get("tableComment") or review["roundSummary"],
                "suggestedRoundsLeft": review.get("suggestedRoundsLeft"),
                "progress": review.get("progress", {}),
                "missingExpertHint": review.get("missingExpertHint", ""),
            })

        if should_complete:
            review["recommendation"] = "complete"
        return review

    async def _complete_session(self, status: str, review: dict | None = None):
        if not self._running_session_id or not self._running_room_id:
            return
        self._clear_round_rag_cache()
        self._clear_prepared_turns()
        self.repo.update_session(
            self._running_session_id,
            {
                "status": status,
                "endedAt": utc_now(),
            },
        )
        session = self.repo.get_session(self._running_session_id)
        snapshot = self.repo.get_room_snapshot(self._running_room_id) or {}
        room = snapshot.get("room") or {}
        participants_block = snapshot.get("participants") or {}
        participants = [
            *(participants_block.get("active") or []),
            *(participants_block.get("benched") or []),
        ]
        observer_reviews = self.repo.get_observer_reviews(self._running_session_id)
        try:
            session_insight = await asyncio.to_thread(
                store_session_memories,
                room=room,
                session=session,
                participants=participants,
                review=review,
                observer_reviews=observer_reviews,
            )
            if session_insight:
                self.repo.save_session_insight(session_insight)
        except Exception:
            pass
        final_summary = (review or {}).get("chronicle") or (review or {}).get("roundSummary") or "Сессия завершена."
        await self._broadcast({
            "type": "session_completed",
            "status": status,
            "summary": final_summary,
        })
        await self._broadcast({
            "type": "session_final_summary",
            "summary": final_summary,
            "review": review or {},
        })
        await self._broadcast_room_loaded(self._running_room_id)

    def _build_agent_context(
        self,
        room_id: str,
        session_id: str,
        round_id: str,
        round_number: int,
        participant: dict | None = None,
    ) -> dict:
        base = self._build_agent_context_base(
            room_id,
            session_id,
            round_id,
            round_number,
            participant=participant,
        )
        return {
            **base,
            "history": self._build_agent_history(session_id),
        }

    def _clear_round_rag_cache(self, round_id: str | None = None):
        self._round_rag_cache.clear()
        self._rag_cache_round_id = round_id

    def _make_round_rag_cache_key(self, round_id: str, topic: str) -> str:
        topic_hash = hashlib.sha1(topic.encode("utf-8")).hexdigest()[:12]
        return f"{round_id}:{topic_hash}"

    def _build_rag_query(self, ctx: dict) -> str:
        topic = (ctx.get("topic") or "").strip()
        recent = " ".join(
            (message.get("content") or "").strip()[:200]
            for message in ctx.get("history", [])[-3:]
            if (message.get("content") or "").strip()
        )
        return ". ".join(part for part in [topic, recent] if part).strip()

    async def _get_round_rag_context(self, round_id: str, ctx: dict) -> str:
        graph_id = ctx.get("graph_id")
        if not graph_id:
            return ""

        if self._rag_cache_round_id != round_id:
            self._clear_round_rag_cache(round_id)

        cache_key = self._make_round_rag_cache_key(round_id, ctx.get("topic") or "")
        cached = self._round_rag_cache.get(cache_key)
        if cached is not None:
            return cached

        rag_query = self._build_rag_query(ctx)
        if not rag_query:
            self._round_rag_cache[cache_key] = ""
            return ""

        try:
            rag_context = await asyncio.to_thread(
                query_graph,
                graph_id,
                rag_query,
                "hybrid",
                20,
            )
        except Exception:
            rag_context = ""

        self._round_rag_cache[cache_key] = rag_context or ""
        return self._round_rag_cache[cache_key]

    def _build_profile_memory_text(
        self,
        *,
        round_number: int,
        participant: dict,
        ctx: dict,
        response_text: str,
    ) -> str:
        recent_messages = [
            (message.get("agent_name") or "Участник", (message.get("content") or "").strip())
            for message in ctx.get("history", [])[-3:]
            if (message.get("content") or "").strip()
        ]
        last_3_messages_summary = " | ".join(
            f"{author}: {content[:220]}"
            for author, content in recent_messages
        ) or "Нет релевантных сообщений перед этой репликой."
        room_name = (ctx.get("room_name") or "").strip() or "Без названия"
        topic = (ctx.get("topic") or "").strip() or "Без темы"
        observer_provider = (ctx.get("observer_provider") or "").strip() or "unknown"
        observer_model = (ctx.get("observer_model") or "").strip() or "unknown"
        roster = ", ".join(
            f"{item.get('name') or 'Без имени'} ({item.get('role') or 'participant'}/{item.get('specialtyLabel') or item.get('specialty') or 'generalist'})"
            for item in ctx.get("active_participants", [])
            if item.get("name")
        ) or "Состав не указан."
        return (
            f"Тема: {topic}\n"
            f"Раунд {round_number}, комната '{room_name}'.\n"
            f"Наблюдатель сессии: {observer_provider}/{observer_model}.\n"
            f"Персонаж: {participant['name']} ({participant['role']} / {participant.get('specialtyLabel') or participant['specialty']}).\n"
            f"Текущий состав: {roster}\n"
            f"Моя позиция: {(response_text or '').strip()[:500]}\n"
            f"Ключевые аргументы собеседников: {last_3_messages_summary}"
        )

    async def _store_profile_memory(
        self,
        room_id: str,
        round_number: int,
        participant: dict,
        ctx: dict,
        response_text: str,
    ):
        profile_id = participant.get("profileId")
        if not profile_id:
            return

        try:
            memory_graph_id = participant.get("memoryGraphId") or self.repo.get_profile_memory_graph_id(profile_id)
            created_graph = False
            if not memory_graph_id:
                memory_graph_id = create_profile_graph(profile_id)
                self.repo.set_profile_memory_graph_id(profile_id, memory_graph_id)
                participant["memoryGraphId"] = memory_graph_id
                participant["hasMemory"] = True
                created_graph = True

            memory_text = self._build_profile_memory_text(
                round_number=round_number,
                participant=participant,
                ctx=ctx,
                response_text=response_text,
            )
            await asyncio.to_thread(
                insert_text,
                memory_graph_id,
                [memory_text],
                root_dir=PROFILE_GRAPH_ROOT,
            )
        except Exception:
            logger.warning(
                "Не удалось сохранить память персонажа %s (граф %s)",
                participant.get("name"),
                memory_graph_id,
                exc_info=True,
            )
            return

        if created_graph:
            snapshot = self.repo.get_room_snapshot(room_id)
            await self._broadcast({
                "type": "participant_stats_updated",
                "participants": snapshot["participants"] if snapshot else None,
                "inventory": snapshot["inventory"] if snapshot else self.repo.list_saved_profiles(),
            })

    async def _append_and_broadcast(self, room_id: str | None, session_id: str | None, payload: dict, *, round_id: str | None = None, round_number: int | None = None, message_type: str = "status", author_type: str = "system", participant_id: str | None = None):
        if not room_id or not session_id:
            await self._broadcast(payload)
            return payload

        enriched = {**payload, "author_type": author_type}
        stored = self.repo.append_message(
            room_id,
            session_id,
            enriched,
            round_id=round_id,
            round_number=round_number,
            message_type=message_type,
            author_type=author_type,
            participant_id=participant_id,
        )
        await self._broadcast(stored)
        return stored

    async def _broadcast_room_loaded(self, room_id: str):
        snapshot = self.repo.get_room_snapshot(room_id)
        if not snapshot:
            return
        await self._broadcast({
            "type": "room_loaded",
            "rooms": self.repo.list_rooms(),
            "currentRoomId": room_id,
            **snapshot,
        })

    async def _broadcast_session_state(self, session: dict | None = None):
        payload_session = session
        if not payload_session and self._running_session_id:
            payload_session = self.repo.get_session(self._running_session_id)

        await self._broadcast({
            "type": "session_state",
            "roomId": self._running_room_id or self.repo.get_current_room_id(),
            "state": self._state,
            "session": payload_session,
        })

    async def _broadcast_roster_change(self, room_id: str | None, verb: str, participant: dict):
        if not room_id:
            room_id = self.repo.get_current_room_id()
        if not room_id:
            return
        await self._broadcast({
            "type": "participant_roster_changed",
            "action": verb,
            "participant": participant,
            "participants": self.repo.get_room_snapshot(room_id)["participants"],
            "inventory": self.repo.list_saved_profiles(),
        })
        await self._broadcast_room_loaded(room_id)
