from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Awaitable, Callable

from agents import Agent, AgentConfig, detect_emotion
from chronomancer import Chronomancer
from storage import Repository, utc_now


BroadcastFn = Callable[[dict], Awaitable[None]]


@dataclass
class RoundState:
    round_id: str
    round_number: int
    order: list[dict]
    next_index: int = 0


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
                    await self._broadcast({"type": "countdown", "round": round_number, "seconds": 3})
                    await asyncio.sleep(3.1)
                    await self._broadcast({"type": "round_start", "round": round_number})

                while self._round_state and self._round_state.next_index < len(self._round_state.order):
                    if self._pause_requested:
                        await self._enter_paused()
                        if self._stop_requested:
                            break

                    participant = self._round_state.order[self._round_state.next_index]
                    await self._agent_turn(room_id, session_id, self._round_state.round_id, self._round_state.round_number, participant)
                    self._round_state.next_index += 1

                    if self._stop_requested:
                        break

                    if self._round_state.next_index < len(self._round_state.order):
                        await asyncio.sleep(random.uniform(0.5, 0.9))

                if self._stop_requested:
                    break

                if not self._round_state:
                    continue

                review = await self._review_round(room_id, session_id, self._round_state)
                self._round_state = None

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
            await self._broadcast_session_state(final_session)

    async def _enter_paused(self):
        if not self._running_session_id:
            return
        self._state = "paused"
        self.repo.update_session(self._running_session_id, {"status": "paused"})
        self._resume_event.clear()
        await self._broadcast({"type": "paused"})
        await self._broadcast_session_state()
        await self._resume_event.wait()

    async def _agent_turn(self, room_id: str, session_id: str, round_id: str, round_number: int, participant: dict):
        await asyncio.sleep(random.uniform(0.35, 0.85))
        if self._stop_requested:
            return

        await self._broadcast({
            "type": "agent_thinking",
            "agent_id": participant["id"],
        })

        await asyncio.sleep(random.uniform(0.8, 1.4))
        if self._stop_requested:
            return

        agent = Agent(AgentConfig(
            id=participant["id"],
            profile_id=participant["profileId"],
            name=participant["name"],
            role=participant["role"],
            specialty=participant["specialty"],
            provider=participant["provider"],
            model=participant["model"],
            emoji=participant["emoji"],
            mascot=participant["mascot"],
        ))

        context = self._build_agent_context(room_id, session_id, round_number)
        accumulated = ""

        async def on_token(token: str):
            nonlocal accumulated
            accumulated += token
            await self._broadcast({
                "type": "agent_token",
                "agent_id": participant["id"],
                "token": token,
            })

        try:
            await agent.generate(context, on_token=on_token)
        except Exception as exc:
            await self._broadcast({
                "type": "error",
                "agent_id": participant["id"],
                "message": str(exc),
            })
            return

        if not accumulated.strip():
            accumulated = "(без ответа)"

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
            "content": accumulated,
            "emotion": detect_emotion(accumulated),
            "round": round_number,
            "author_type": "agent",
        }
        stored = self.repo.append_message(
            room_id,
            session_id,
            payload,
            round_id=round_id,
            round_number=round_number,
            message_type="agent_message",
            author_type="agent",
            participant_id=participant["id"],
        )
        await self._broadcast(stored)

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
        review = await self.chronomancer.review_round(
            topic=session["topic"],
            observer_provider=room.get("observerProvider"),
            observer_model=room.get("observerModel"),
            observer_mode=session["observerMode"],
            chronicle=session["chronicle"],
            round_number=round_state.round_number,
            round_messages=self.repo.list_round_messages(session_id, round_state.round_number),
            participants=participants,
            room_events=events,
            wrap_requested=session["wrapRequested"],
            final_round_planned=session["finalRoundPlanned"],
            extension_count=session["extensionCount"],
        )

        self.repo.complete_round(round_state.round_id, review)
        self.repo.save_observer_review(room_id, session_id, round_state.round_id, round_state.round_number, review)
        self.repo.apply_stats_delta(review.get("statsDelta", {}), review.get("participantComments", {}))

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
                "summary": review.get("tableComment") or review["roundSummary"],
                "suggestedRoundsLeft": review.get("suggestedRoundsLeft"),
            })

        if should_complete:
            review["recommendation"] = "complete"
        return review

    async def _complete_session(self, status: str, review: dict | None = None):
        if not self._running_session_id or not self._running_room_id:
            return
        self.repo.update_session(
            self._running_session_id,
            {
                "status": status,
                "endedAt": utc_now(),
            },
        )
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

    def _build_agent_context(self, room_id: str, session_id: str, round_number: int) -> dict:
        snapshot = self.repo.get_room_snapshot(room_id)
        session = self.repo.get_session(session_id)
        messages = self.repo.list_session_messages(session_id, limit=48)
        history = []
        for message in messages:
            author_type = message.get("author_type")
            if author_type not in {"agent", "user"}:
                continue
            history.append({
                "author_type": author_type,
                "agent_name": message.get("agent_name") or message.get("name"),
                "role": message.get("role", "participant"),
                "specialty": message.get("specialty", "generalist"),
                "content": message.get("content", ""),
            })

        return {
            "topic": session["topic"] if session else "",
            "room_summary": (snapshot or {}).get("room", {}).get("summary", ""),
            "session_chronicle": session["chronicle"] if session else "",
            "history": history,
            "wrap_signal": bool(session and session["wrapRequested"]),
            "final_signal": bool(session and session["finalRoundPlanned"]),
            "round_number": round_number,
            "active_participants": (snapshot or {}).get("participants", {}).get("active", []),
        }

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
