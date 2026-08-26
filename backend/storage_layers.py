from __future__ import annotations

import sqlite3
from typing import Any, Callable


CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS app_state (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS character_profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    specialty TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    emoji TEXT NOT NULL,
    mascot TEXT NOT NULL,
    stats_json TEXT NOT NULL,
    strengths_json TEXT NOT NULL,
    weaknesses_json TEXT NOT NULL,
    summary TEXT NOT NULL,
    last_note TEXT NOT NULL,
    memory_graph_id TEXT,
    is_saved INTEGER NOT NULL DEFAULT 0,
    system_provided INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rooms (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    observer_mode TEXT NOT NULL DEFAULT 'suggest',
    density_mode TEXT NOT NULL DEFAULT 'normal',
    graph_id TEXT,
    observer_provider TEXT,
    observer_model TEXT,
    settings_json TEXT NOT NULL DEFAULT '{}',
    current_session_id TEXT,
    summary TEXT NOT NULL DEFAULT '',
    last_topic TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS room_participants (
    id TEXT PRIMARY KEY,
    room_id TEXT NOT NULL,
    profile_id TEXT NOT NULL,
    status TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    specialty TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    emoji TEXT NOT NULL,
    mascot TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    room_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    topic TEXT NOT NULL,
    status TEXT NOT NULL,
    observer_mode TEXT NOT NULL,
    observer_provider TEXT,
    observer_model TEXT,
    chronicle TEXT NOT NULL DEFAULT '',
    wrap_requested INTEGER NOT NULL DEFAULT 0,
    final_requested INTEGER NOT NULL DEFAULT 0,
    final_round_planned INTEGER NOT NULL DEFAULT 0,
    extension_count INTEGER NOT NULL DEFAULT 0,
    last_round_number INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    ended_at TEXT
);

CREATE TABLE IF NOT EXISTS rounds (
    id TEXT PRIMARY KEY,
    room_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    round_number INTEGER NOT NULL,
    status TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    chronicle_after TEXT NOT NULL DEFAULT '',
    recommendation TEXT NOT NULL DEFAULT 'continue',
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    room_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    round_id TEXT,
    round_number INTEGER,
    message_type TEXT NOT NULL,
    author_type TEXT NOT NULL,
    participant_id TEXT,
    created_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS room_events (
    id TEXT PRIMARY KEY,
    room_id TEXT NOT NULL,
    session_id TEXT,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS planned_events (
    id TEXT PRIMARY KEY,
    room_id TEXT NOT NULL,
    session_id TEXT,
    target_round INTEGER NOT NULL,
    description TEXT NOT NULL,
    created_at TEXT NOT NULL,
    fired_at TEXT,
    FOREIGN KEY (room_id) REFERENCES rooms(id)
);

CREATE TABLE IF NOT EXISTS observer_reviews (
    id TEXT PRIMARY KEY,
    room_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    round_id TEXT NOT NULL,
    round_number INTEGER NOT NULL,
    summary TEXT NOT NULL,
    chronicle_before TEXT NOT NULL,
    chronicle_after TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    suggested_rounds_left INTEGER,
    comments_json TEXT NOT NULL,
    achievements_json TEXT NOT NULL,
    stats_delta_json TEXT NOT NULL,
    progress_json TEXT NOT NULL DEFAULT '{}',
    final_reason TEXT NOT NULL DEFAULT '',
    missing_expert_hint TEXT NOT NULL DEFAULT '',
    roster_advice_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pinned_messages (
    id TEXT PRIMARY KEY,
    room_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(session_id, message_id)
);

CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    room_id TEXT,
    markdown TEXT NOT NULL,
    sections_json TEXT,
    generated_at TEXT NOT NULL,
    provider TEXT,
    model TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS session_insights (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL UNIQUE,
    room_id TEXT NOT NULL,
    topic TEXT NOT NULL DEFAULT '',
    observer_provider TEXT,
    observer_model TEXT,
    roster_hash TEXT NOT NULL DEFAULT '',
    participant_profile_ids_json TEXT NOT NULL DEFAULT '[]',
    participant_model_pairs_json TEXT NOT NULL DEFAULT '[]',
    tags_json TEXT NOT NULL DEFAULT '[]',
    summary TEXT NOT NULL DEFAULT '',
    casting_outcome TEXT NOT NULL DEFAULT '',
    curated_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fact_check_runs (
    id TEXT PRIMARY KEY,
    room_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    scope TEXT NOT NULL,
    target_round INTEGER,
    status TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    summary TEXT NOT NULL DEFAULT '',
    counts_json TEXT NOT NULL DEFAULT '{}',
    model_deltas_json TEXT NOT NULL DEFAULT '[]',
    internet_mode TEXT NOT NULL DEFAULT 'auto',
    external_sources_used INTEGER NOT NULL DEFAULT 0,
    provider TEXT,
    model TEXT,
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS fact_check_claims (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    room_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    round_number INTEGER,
    message_id TEXT,
    participant_id TEXT,
    profile_id TEXT,
    agent_name TEXT,
    provider TEXT,
    model TEXT,
    claim_text TEXT NOT NULL,
    verdict TEXT NOT NULL,
    evidence TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL DEFAULT '',
    source_label TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES fact_check_runs(id)
);

CREATE TABLE IF NOT EXISTS model_reliability_rollups (
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    confirmed_count INTEGER NOT NULL DEFAULT 0,
    unverified_count INTEGER NOT NULL DEFAULT 0,
    contradicted_count INTEGER NOT NULL DEFAULT 0,
    disputed_count INTEGER NOT NULL DEFAULT 0,
    insufficient_evidence_count INTEGER NOT NULL DEFAULT 0,
    checked_claim_count INTEGER NOT NULL DEFAULT 0,
    reliability_score REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (provider, model)
);

CREATE TABLE IF NOT EXISTS team_presets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    participants_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS custom_specialties (
    id TEXT PRIMARY KEY,
    value TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    group_label TEXT NOT NULL DEFAULT 'Кастомные оптики',
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS custom_providers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    base_url TEXT NOT NULL,
    api_key TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS token_usage (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    room_id TEXT,
    round_number INTEGER,
    kind TEXT NOT NULL,
    provider TEXT,
    model TEXT,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_token_usage_session ON token_usage(session_id);

CREATE INDEX IF NOT EXISTS idx_profiles_saved_updated
    ON character_profiles(is_saved, updated_at, name);
CREATE INDEX IF NOT EXISTS idx_room_participants_room_status_position
    ON room_participants(room_id, status, position, created_at);
CREATE INDEX IF NOT EXISTS idx_sessions_room_updated
    ON sessions(room_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_rounds_session_round
    ON rounds(session_id, round_number);
CREATE INDEX IF NOT EXISTS idx_messages_session_created
    ON messages(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_session_round_author
    ON messages(session_id, round_number, author_type, created_at);
CREATE INDEX IF NOT EXISTS idx_room_events_room_session_created
    ON room_events(room_id, session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_planned_events_room_session_round
    ON planned_events(room_id, session_id, target_round, fired_at);
CREATE INDEX IF NOT EXISTS idx_observer_reviews_session_round
    ON observer_reviews(session_id, round_number);
CREATE INDEX IF NOT EXISTS idx_reports_session_generated
    ON reports(session_id, generated_at);
CREATE INDEX IF NOT EXISTS idx_session_insights_room_curated
    ON session_insights(room_id, curated_at);
CREATE INDEX IF NOT EXISTS idx_session_insights_observer_curated
    ON session_insights(observer_provider, observer_model, curated_at);
CREATE INDEX IF NOT EXISTS idx_fact_check_runs_session_created
    ON fact_check_runs(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_fact_check_claims_run_created
    ON fact_check_claims(run_id, created_at);
"""


class SchemaManager:
    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        normalize_room_settings: Callable[[dict | None], dict],
        loads_json: Callable[[Any, Any], Any],
        dumps_json: Callable[[Any], str],
        utc_now: Callable[[], str],
    ):
        self.conn = conn
        self._normalize_room_settings = normalize_room_settings
        self._loads_json = loads_json
        self._dumps_json = dumps_json
        self._utc_now = utc_now

    def create_tables(self):
        self.conn.executescript(CREATE_TABLES_SQL)
        self.conn.commit()

    def migrate_schema(self):
        self._ensure_column("character_profiles", "memory_graph_id", "ALTER TABLE character_profiles ADD COLUMN memory_graph_id TEXT")
        self._ensure_column("sessions", "title", "ALTER TABLE sessions ADD COLUMN title TEXT NOT NULL DEFAULT ''", commit=False)
        self._ensure_column("sessions", "observer_provider", "ALTER TABLE sessions ADD COLUMN observer_provider TEXT", commit=False)
        self._ensure_column("sessions", "observer_model", "ALTER TABLE sessions ADD COLUMN observer_model TEXT")

        self._ensure_column("rooms", "density_mode", "ALTER TABLE rooms ADD COLUMN density_mode TEXT NOT NULL DEFAULT 'normal'")
        self._ensure_column("rooms", "graph_id", "ALTER TABLE rooms ADD COLUMN graph_id TEXT")
        self._ensure_column("rooms", "settings_json", "ALTER TABLE rooms ADD COLUMN settings_json TEXT NOT NULL DEFAULT '{}'")
        self._backfill_room_settings()

        self._ensure_column("observer_reviews", "progress_json", "ALTER TABLE observer_reviews ADD COLUMN progress_json TEXT NOT NULL DEFAULT '{}'")
        self._ensure_column("observer_reviews", "final_reason", "ALTER TABLE observer_reviews ADD COLUMN final_reason TEXT NOT NULL DEFAULT ''")
        self._ensure_column("observer_reviews", "missing_expert_hint", "ALTER TABLE observer_reviews ADD COLUMN missing_expert_hint TEXT NOT NULL DEFAULT ''")
        self._ensure_column("observer_reviews", "roster_advice_json", "ALTER TABLE observer_reviews ADD COLUMN roster_advice_json TEXT NOT NULL DEFAULT '{}'")
        self._ensure_column("token_usage", "cost", "ALTER TABLE token_usage ADD COLUMN cost REAL")

    def _columns(self, table: str) -> set[str]:
        return {row["name"] for row in self.conn.execute(f"PRAGMA table_info({table})").fetchall()}

    def _ensure_column(self, table: str, column: str, ddl: str, *, commit: bool = True):
        if column in self._columns(table):
            return
        self.conn.execute(ddl)
        if commit:
            self.conn.commit()

    def _backfill_room_settings(self):
        rows = self.conn.execute("SELECT id, settings_json FROM rooms").fetchall()
        updates: list[tuple[str, str, str]] = []
        now = self._utc_now()
        for row in rows:
            current = self._loads_json(row["settings_json"], {})
            normalized = self._normalize_room_settings(current)
            if (
                current.get("internet_mode") != normalized["internet_mode"]
                or current.get("tools_enabled") != normalized["tools_enabled"]
                or current.get("available_tools") != normalized["available_tools"]
            ):
                updates.append((self._dumps_json({**current, **normalized}), now, row["id"]))
        if updates:
            self.conn.executemany(
                "UPDATE rooms SET settings_json = ?, updated_at = ? WHERE id = ?",
                updates,
            )
            self.conn.commit()


class PayloadBuilder:
    def __init__(
        self,
        repository: Any,
        *,
        loads_json: Callable[[Any, Any], Any],
        normalize_room_settings: Callable[[dict | None], dict],
    ):
        self.repository = repository
        self.conn = repository.conn
        self._loads_json = loads_json
        self._normalize_room_settings = normalize_room_settings

    def profile(self, row: sqlite3.Row | None) -> dict | None:
        if not row:
            return None
        return {
            "id": row["id"],
            "name": row["name"],
            "role": row["role"],
            "specialty": row["specialty"],
            "specialtyLabel": self.repository.get_custom_specialty_label(row["specialty"]),
            "provider": row["provider"],
            "model": row["model"],
            "emoji": row["emoji"],
            "mascot": row["mascot"],
            "stats": self._loads_json(row["stats_json"], {}),
            "strengths": self._loads_json(row["strengths_json"], []),
            "weaknesses": self._loads_json(row["weaknesses_json"], []),
            "summary": row["summary"],
            "lastNote": row["last_note"],
            "memoryGraphId": row["memory_graph_id"],
            "hasMemory": bool(row["memory_graph_id"]),
            "isSaved": bool(row["is_saved"]),
            "systemProvided": bool(row["system_provided"]),
        }

    def session(self, row: sqlite3.Row | None) -> dict | None:
        if not row:
            return None
        return {
            "id": row["id"],
            "title": row["title"],
            "topic": row["topic"],
            "status": row["status"],
            "observerMode": row["observer_mode"],
            "observerProvider": row["observer_provider"],
            "observerModel": row["observer_model"],
            "chronicle": row["chronicle"],
            "wrapRequested": bool(row["wrap_requested"]),
            "finalRequested": bool(row["final_requested"]),
            "finalRoundPlanned": bool(row["final_round_planned"]),
            "extensionCount": row["extension_count"],
            "lastRoundNumber": row["last_round_number"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "startedAt": row["started_at"],
            "endedAt": row["ended_at"],
        }

    def participant(self, row: sqlite3.Row | None) -> dict | None:
        if not row:
            return None
        profile = self.conn.execute(
            "SELECT * FROM character_profiles WHERE id = ?",
            (row["profile_id"],),
        ).fetchone()
        return {
            "id": row["id"],
            "profileId": row["profile_id"],
            "status": row["status"],
            "position": row["position"],
            "name": row["name"],
            "role": row["role"],
            "specialty": row["specialty"],
            "specialtyLabel": self.repository.get_custom_specialty_label(row["specialty"]),
            "provider": row["provider"],
            "model": row["model"],
            "emoji": row["emoji"],
            "mascot": row["mascot"],
            "stats": self._loads_json(profile["stats_json"], {}) if profile else {},
            "strengths": self._loads_json(profile["strengths_json"], []) if profile else [],
            "weaknesses": self._loads_json(profile["weaknesses_json"], []) if profile else [],
            "summary": profile["summary"] if profile else "",
            "lastNote": profile["last_note"] if profile else "",
            "memoryGraphId": profile["memory_graph_id"] if profile else None,
            "hasMemory": bool(profile["memory_graph_id"]) if profile else False,
            "isSavedProfile": bool(profile["is_saved"]) if profile else False,
            "systemProvided": bool(profile["system_provided"]) if profile else False,
        }

    def observer_review(self, row: sqlite3.Row | None) -> dict | None:
        if not row:
            return None
        return {
            "id": row["id"],
            "roundNumber": row["round_number"],
            "summary": row["summary"],
            "chronicleBefore": row["chronicle_before"],
            "chronicleAfter": row["chronicle_after"],
            "recommendation": row["recommendation"],
            "suggestedRoundsLeft": row["suggested_rounds_left"],
            "comments": self._loads_json(row["comments_json"], {}),
            "participantComments": self._loads_json(row["comments_json"], {}),
            "achievements": self._loads_json(row["achievements_json"], []),
            "statsDelta": self._loads_json(row["stats_delta_json"], {}),
            "progress": self._loads_json(row["progress_json"], {}),
            "finalReason": row["final_reason"],
            "missingExpertHint": row["missing_expert_hint"],
            "rosterAdvice": self._loads_json(row["roster_advice_json"], {}),
            "createdAt": row["created_at"],
        }

    def report(self, row: sqlite3.Row | None) -> dict | None:
        if not row:
            return None
        return {
            "id": row["id"],
            "sessionId": row["session_id"],
            "roomId": row["room_id"],
            "markdown": row["markdown"],
            "sections": self._loads_json(row["sections_json"], []),
            "generatedAt": row["generated_at"],
            "provider": row["provider"],
            "model": row["model"],
        }

    def fact_check_claim(self, row: sqlite3.Row | None) -> dict | None:
        if not row:
            return None
        return {
            "id": row["id"],
            "runId": row["run_id"],
            "roomId": row["room_id"],
            "sessionId": row["session_id"],
            "roundNumber": row["round_number"],
            "messageId": row["message_id"],
            "participantId": row["participant_id"],
            "profileId": row["profile_id"],
            "agentName": row["agent_name"],
            "provider": row["provider"],
            "model": row["model"],
            "claimText": row["claim_text"],
            "verdict": row["verdict"],
            "evidence": row["evidence"],
            "sourceType": row["source_type"],
            "sourceLabel": row["source_label"],
            "createdAt": row["created_at"],
        }

    def fact_check_run(self, row: sqlite3.Row | None, *, claims: list[dict] | None = None) -> dict | None:
        if not row:
            return None
        payload = {
            "id": row["id"],
            "roomId": row["room_id"],
            "sessionId": row["session_id"],
            "scope": row["scope"],
            "targetRound": row["target_round"],
            "status": row["status"],
            "progress": row["progress"],
            "summary": row["summary"],
            "counts": self._loads_json(row["counts_json"], {}),
            "modelDeltas": self._loads_json(row["model_deltas_json"], []),
            "internetMode": row["internet_mode"],
            "externalSourcesUsed": bool(row["external_sources_used"]),
            "provider": row["provider"],
            "model": row["model"],
            "error": row["error"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "completedAt": row["completed_at"],
        }
        if claims is not None:
            payload["claims"] = claims
        return payload

    def model_reliability(self, row: sqlite3.Row | None) -> dict | None:
        if not row:
            return None
        counts = {
            "confirmed": row["confirmed_count"],
            "unverified": row["unverified_count"],
            "contradicted": row["contradicted_count"],
            "disputed": row["disputed_count"],
            "insufficient_evidence": row["insufficient_evidence_count"],
        }
        return {
            "provider": row["provider"],
            "model": row["model"],
            "counts": counts,
            "checkedClaims": row["checked_claim_count"],
            "reliabilityScore": row["reliability_score"],
            "updatedAt": row["updated_at"],
        }

    def session_insight(self, row: sqlite3.Row | None) -> dict | None:
        if not row:
            return None
        return {
            "id": row["id"],
            "sessionId": row["session_id"],
            "roomId": row["room_id"],
            "topic": row["topic"],
            "observerProvider": row["observer_provider"],
            "observerModel": row["observer_model"],
            "rosterHash": row["roster_hash"],
            "participantProfileIds": self._loads_json(row["participant_profile_ids_json"], []),
            "participantModelPairs": self._loads_json(row["participant_model_pairs_json"], []),
            "tags": self._loads_json(row["tags_json"], []),
            "summary": row["summary"],
            "castingOutcome": row["casting_outcome"],
            "curatedAt": row["curated_at"],
            "createdAt": row["created_at"],
        }

    def planned_event(self, row: sqlite3.Row | None) -> dict | None:
        if not row:
            return None
        return {
            "id": row["id"],
            "roomId": row["room_id"],
            "sessionId": row["session_id"],
            "targetRound": row["target_round"],
            "description": row["description"],
            "createdAt": row["created_at"],
            "firedAt": row["fired_at"],
            "fired": bool(row["fired_at"]),
        }

    def custom_specialty(self, row: sqlite3.Row | None) -> dict | None:
        if not row:
            return None
        return {
            "id": row["id"],
            "value": row["value"],
            "label": row["label"],
            "groupLabel": row["group_label"],
            "description": row["description"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def room_settings(self, row: sqlite3.Row) -> dict:
        return self._normalize_room_settings(self._loads_json(row["settings_json"], {}))

    def room(self, row: sqlite3.Row | None) -> dict | None:
        if not row:
            return None
        settings = self.room_settings(row)
        return {
            "id": row["id"],
            "name": row["name"],
            "observerMode": row["observer_mode"],
            "densityMode": row["density_mode"],
            "graphId": row["graph_id"],
            "observerProvider": row["observer_provider"],
            "observerModel": row["observer_model"],
            "summary": row["summary"],
            "lastTopic": row["last_topic"],
            "settings": settings,
            "internetMode": settings["internet_mode"],
            "toolsEnabled": settings["tools_enabled"],
            "availableTools": settings["available_tools"],
        }


class BusinessAggregates:
    def __init__(
        self,
        repository: Any,
        *,
        payloads: PayloadBuilder,
        loads_json: Callable[[Any, Any], Any],
        dumps_json: Callable[[Any], str],
        utc_now: Callable[[], str],
        make_id: Callable[[str], str],
    ):
        self.repository = repository
        self.conn = repository.conn
        self.payloads = payloads
        self._loads_json = loads_json
        self._dumps_json = dumps_json
        self._utc_now = utc_now
        self._make_id = make_id

    def build_room_snapshot(self, room_id: str) -> dict | None:
        room = self.conn.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
        if not room:
            return None

        self.repository.set_current_room(room_id)
        active_rows, benched_rows = self._load_room_participants(room_id)
        current_session = self._load_current_room_session(room_id, room["current_session_id"])
        session_bundle = self._load_session_bundle(
            current_session["id"] if current_session else None,
            message_limit=300,
            review_limit=12,
        )
        return self._compose_snapshot(
            room=room,
            session=current_session,
            active_rows=active_rows,
            benched_rows=benched_rows,
            session_bundle=session_bundle,
            planned_events=self.repository.list_planned_events(
                room_id,
                current_session["id"] if current_session else None,
            ),
        )

    def build_session_snapshot(self, session_id: str, *, make_current: bool = False) -> dict | None:
        session = self.conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not session:
            return None
        room_id = session["room_id"]
        room = self.conn.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
        if not room:
            return None
        if make_current:
            self.repository.set_current_room(room_id)
            self.repository.update_room_settings(room_id, current_session_id=session_id, last_topic=session["topic"])

        active_rows, benched_rows = self._load_room_participants(room_id)
        session_bundle = self._load_session_bundle(session_id, message_limit=800, review_limit=24)
        return self._compose_snapshot(
            room=room,
            session=session,
            active_rows=active_rows,
            benched_rows=benched_rows,
            session_bundle=session_bundle,
            planned_events=self.repository.list_planned_events(room_id, session_id),
        )

    def export_session_markdown(self, session_id: str) -> str | None:
        snapshot = self.build_session_snapshot(session_id, make_current=False)
        if not snapshot or not snapshot["session"]:
            return None

        def format_decision_progress(review: dict) -> str:
            progress = review.get("progress") or {}
            decision = progress.get("decisionProgress") or review.get("decisionProgress") or {}
            if not isinstance(decision, dict) or not decision:
                return "стадия не зафиксирована"
            readiness = decision.get("readiness")
            readiness_text = f"{readiness}%" if readiness is not None else "—"
            return (
                f"стадия {decision.get('stage') or '—'}, готовность {readiness_text}, "
                f"следующий ход {decision.get('nextAction') or 'continue'}, "
                f"блокер: {decision.get('blocker') or 'не указан'}"
            )

        def format_roster_advice(review: dict) -> str:
            advice = review.get("rosterAdvice") or {}
            missing = advice.get("missingExpertHint") or review.get("missingExpertHint") or ""
            excess = advice.get("excessParticipant") if isinstance(advice.get("excessParticipant"), dict) else None
            parts = []
            if missing:
                parts.append(f"не хватает: {missing}")
            if excess:
                confidence = excess.get("confidence")
                confidence_text = f", confidence {confidence}%" if confidence is not None else ""
                parts.append(
                    f"мешает фокусу сейчас: {excess.get('name') or 'участник'} "
                    f"({excess.get('reason') or 'снижает фокус'}{confidence_text})"
                )
            if not parts:
                parts.append("состав без явных рекомендаций")
            parts.append("применение: только вручную, автоматической скамейки нет")
            return "; ".join(parts)

        session = snapshot["session"]
        room = snapshot["room"]
        title = session.get("title") or session["topic"] or "Сессия"
        lines = [
            f"# {title}",
            "",
            f"- Комната: {room['name']}",
            f"- Статус: {session['status']}",
            f"- Хрономант: {(session.get('observerProvider') or '?')}/{(session.get('observerModel') or '?')}",
            f"- Раундов: {session['lastRoundNumber']}",
            f"- Старт: {session.get('startedAt') or session.get('createdAt') or ''}",
            f"- Финал: {session.get('endedAt') or 'не завершена'}",
            "",
            "## Тема",
            "",
            session["topic"],
            "",
        ]
        if session.get("chronicle"):
            lines.extend(["## Хроника", "", session["chronicle"], ""])
        if snapshot.get("pinnedMessages"):
            lines.extend(["## Зацепки", ""])
            for item in snapshot["pinnedMessages"]:
                name = item.get("name") or item.get("agent_name") or "Участник"
                lines.extend([f"- **{name}:** {item.get('content', '').strip()}"])
            lines.append("")
        if snapshot["observerReviews"]:
            lines.extend(["## Динамика решения", ""])
            for review in sorted(snapshot["observerReviews"], key=lambda item: item.get("roundNumber") or 0):
                lines.extend([
                    f"- Раунд {review['roundNumber']}: {format_decision_progress(review)}; {format_roster_advice(review)}."
                ])
            lines.append("")
        lines.extend(["## Ход беседы", ""])

        current_round = None
        for message in snapshot["messages"]:
            round_number = message.get("round")
            if round_number and round_number != current_round:
                current_round = round_number
                lines.extend([f"### Раунд {current_round}", ""])
            if message.get("type") == "round":
                continue
            name = message.get("name") or message.get("agent_name") or "Система"
            role = message.get("role")
            specialty = message.get("specialty")
            meta = f" ({role} · {specialty})" if role and specialty else ""
            content = (message.get("content") or "").strip()
            if content:
                lines.extend([f"**{name}{meta}:**", "", content, ""])

        if snapshot["observerReviews"]:
            lines.extend(["## Заметки Хрономанта", ""])
            for review in reversed(snapshot["observerReviews"]):
                lines.extend([
                    f"### Раунд {review['roundNumber']}",
                    "",
                    review.get("summary") or "",
                    "",
                ])
                if review.get("finalReason"):
                    lines.extend([f"_Причина финала:_ {review['finalReason']}", ""])
        return "\n".join(lines).strip() + "\n"

    def save_session_insight(self, insight: dict) -> dict | None:
        session_id = str(insight.get("sessionId") or "").strip()
        room_id = str(insight.get("roomId") or "").strip()
        if not session_id or not room_id:
            return None

        insight_id = self._make_id("insight")
        created_at = self._utc_now()
        curated_at = insight.get("curatedAt") or created_at
        self.conn.execute(
            """
            INSERT OR REPLACE INTO session_insights (
                id, session_id, room_id, topic, observer_provider, observer_model,
                roster_hash, participant_profile_ids_json, participant_model_pairs_json,
                tags_json, summary, casting_outcome, curated_at, created_at
            ) VALUES (
                COALESCE((SELECT id FROM session_insights WHERE session_id = ?), ?),
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                session_id,
                insight_id,
                session_id,
                room_id,
                insight.get("topic") or "",
                insight.get("observerProvider"),
                insight.get("observerModel"),
                insight.get("rosterHash") or "",
                self._dumps_json(insight.get("participantProfileIds") or []),
                self._dumps_json(insight.get("participantModelPairs") or []),
                self._dumps_json(insight.get("tags") or []),
                insight.get("summary") or "",
                insight.get("castingOutcome") or "",
                curated_at,
                created_at,
            ),
        )
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM session_insights WHERE session_id = ?", (session_id,)).fetchone()
        return self.payloads.session_insight(row)

    def list_session_insights(
        self,
        *,
        room_id: str | None = None,
        observer_provider: str | None = None,
        observer_model: str | None = None,
        limit: int = 80,
    ) -> list[dict]:
        where: list[str] = []
        values: list[object] = []
        if room_id:
            where.append("room_id = ?")
            values.append(room_id)
        if observer_provider:
            where.append("observer_provider = ?")
            values.append(observer_provider)
        if observer_model:
            where.append("observer_model = ?")
            values.append(observer_model)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        values.append(max(1, min(int(limit or 80), 200)))
        rows = self.conn.execute(
            f"""
            SELECT *
            FROM session_insights
            {clause}
            ORDER BY curated_at DESC, created_at DESC
            LIMIT ?
            """,
            values,
        ).fetchall()
        return [self.payloads.session_insight(row) for row in rows]

    def get_fact_check_run(self, run_id: str, *, include_claims: bool = True) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM fact_check_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        if not row:
            return None
        claims = self._load_fact_check_claims(run_id) if include_claims else None
        return self.payloads.fact_check_run(row, claims=claims)

    def get_latest_fact_check_run(self, session_id: str, *, include_claims: bool = True) -> dict | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM fact_check_runs
            WHERE session_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()
        if not row:
            return None
        return self.get_fact_check_run(row["id"], include_claims=include_claims)

    def find_reusable_fact_check_run(self, session_id: str, scope: str, target_round: int | None) -> dict | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM fact_check_runs
            WHERE session_id = ?
              AND scope = ?
              AND (target_round IS ? OR target_round = ?)
              AND status IN ('queued', 'running', 'completed')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (session_id, scope, target_round, target_round),
        ).fetchone()
        return self.get_fact_check_run(row["id"]) if row else None

    def create_fact_check_run(
        self,
        *,
        room_id: str,
        session_id: str,
        scope: str,
        target_round: int | None,
        internet_mode: str,
        provider: str | None,
        model: str | None,
    ) -> dict:
        run_id = self._make_id("fcheck")
        now = self._utc_now()
        self.conn.execute(
            """
            INSERT INTO fact_check_runs (
                id, room_id, session_id, scope, target_round, status, progress,
                summary, counts_json, model_deltas_json, internet_mode, external_sources_used,
                provider, model, error, created_at, updated_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, 'queued', 0, '', '{}', '[]', ?, 0, ?, ?, '', ?, ?, NULL)
            """,
            (
                run_id,
                room_id,
                session_id,
                scope,
                target_round,
                internet_mode,
                provider,
                model,
                now,
                now,
            ),
        )
        self.conn.commit()
        return self.get_fact_check_run(run_id)

    def update_fact_check_run(self, run_id: str, **fields) -> dict | None:
        mapping = {
            "status": "status",
            "progress": "progress",
            "summary": "summary",
            "internet_mode": "internet_mode",
            "external_sources_used": "external_sources_used",
            "provider": "provider",
            "model": "model",
            "error": "error",
            "completed_at": "completed_at",
        }
        updates: list[str] = []
        values: list[object] = []
        for key, column in mapping.items():
            if key in fields:
                updates.append(f"{column} = ?")
                values.append(fields[key])
        if "counts" in fields:
            updates.append("counts_json = ?")
            values.append(self._dumps_json(fields["counts"]))
        if "model_deltas" in fields:
            updates.append("model_deltas_json = ?")
            values.append(self._dumps_json(fields["model_deltas"]))
        if not updates:
            return self.get_fact_check_run(run_id)
        updates.append("updated_at = ?")
        values.append(self._utc_now())
        values.append(run_id)
        self.conn.execute(
            f"UPDATE fact_check_runs SET {', '.join(updates)} WHERE id = ?",
            values,
        )
        self.conn.commit()
        return self.get_fact_check_run(run_id)

    def replace_fact_check_claims(self, run_id: str, claims: list[dict]) -> list[dict]:
        run_row = self.conn.execute(
            "SELECT room_id, session_id FROM fact_check_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        if not run_row:
            return []

        self.conn.execute("DELETE FROM fact_check_claims WHERE run_id = ?", (run_id,))
        now = self._utc_now()
        for item in claims:
            self.conn.execute(
                """
                INSERT INTO fact_check_claims (
                    id, run_id, room_id, session_id, round_number, message_id,
                    participant_id, profile_id, agent_name, provider, model,
                    claim_text, verdict, evidence, source_type, source_label, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.get("id") or self._make_id("claim"),
                    run_id,
                    run_row["room_id"],
                    run_row["session_id"],
                    item.get("roundNumber"),
                    item.get("messageId"),
                    item.get("participantId"),
                    item.get("profileId"),
                    item.get("agentName"),
                    item.get("provider"),
                    item.get("model"),
                    item.get("claimText") or "",
                    item.get("verdict") or "unverified",
                    item.get("evidence") or "",
                    item.get("sourceType") or "",
                    item.get("sourceLabel") or "",
                    item.get("createdAt") or now,
                ),
            )
        self.conn.commit()
        return self.get_fact_check_run(run_id, include_claims=True).get("claims", [])

    def get_model_reliability(self, provider: str, model: str) -> dict | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM model_reliability_rollups
            WHERE provider = ? AND model = ?
            """,
            (provider, model),
        ).fetchone()
        return self.payloads.model_reliability(row)

    def apply_model_reliability_rollup(self, claims: list[dict]) -> list[dict]:
        grouped: dict[tuple[str, str], dict[str, int]] = {}
        for item in claims:
            provider = str(item.get("provider") or "").strip()
            model = str(item.get("model") or "").strip()
            verdict = str(item.get("verdict") or "unverified").strip()
            if not provider or not model:
                continue
            bucket = grouped.setdefault(
                (provider, model),
                {
                    "confirmed": 0,
                    "unverified": 0,
                    "contradicted": 0,
                    "disputed": 0,
                    "insufficient_evidence": 0,
                },
            )
            if verdict not in bucket:
                verdict = "unverified"
            bucket[verdict] += 1

        deltas: list[dict] = []
        for (provider, model), delta_counts in grouped.items():
            row = self.conn.execute(
                """
                SELECT *
                FROM model_reliability_rollups
                WHERE provider = ? AND model = ?
                """,
                (provider, model),
            ).fetchone()
            previous_counts = {
                "confirmed": row["confirmed_count"] if row else 0,
                "unverified": row["unverified_count"] if row else 0,
                "contradicted": row["contradicted_count"] if row else 0,
                "disputed": row["disputed_count"] if row else 0,
                "insufficient_evidence": row["insufficient_evidence_count"] if row else 0,
            }
            next_counts = {
                key: previous_counts[key] + delta_counts.get(key, 0)
                for key in previous_counts
            }
            previous_checked = sum(previous_counts.values())
            next_checked = sum(next_counts.values())
            previous_score = row["reliability_score"] if row else 0.0
            next_score = self.repository._score_reliability_counts(next_counts)
            self.conn.execute(
                """
                INSERT INTO model_reliability_rollups (
                    provider, model, confirmed_count, unverified_count, contradicted_count,
                    disputed_count, insufficient_evidence_count, checked_claim_count,
                    reliability_score, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, model) DO UPDATE SET
                    confirmed_count = excluded.confirmed_count,
                    unverified_count = excluded.unverified_count,
                    contradicted_count = excluded.contradicted_count,
                    disputed_count = excluded.disputed_count,
                    insufficient_evidence_count = excluded.insufficient_evidence_count,
                    checked_claim_count = excluded.checked_claim_count,
                    reliability_score = excluded.reliability_score,
                    updated_at = excluded.updated_at
                """,
                (
                    provider,
                    model,
                    next_counts["confirmed"],
                    next_counts["unverified"],
                    next_counts["contradicted"],
                    next_counts["disputed"],
                    next_counts["insufficient_evidence"],
                    next_checked,
                    next_score,
                    self._utc_now(),
                ),
            )
            deltas.append({
                "provider": provider,
                "model": model,
                "countsDelta": delta_counts,
                "checkedClaimsBefore": previous_checked,
                "checkedClaimsAfter": next_checked,
                "previousScore": previous_score,
                "nextScore": next_score,
            })
        if grouped:
            self.conn.commit()
        return deltas

    def save_report(
        self,
        session_id: str,
        room_id: str | None,
        markdown: str,
        sections: list[dict],
        provider: str | None,
        model: str | None,
    ) -> dict:
        report_id = self._make_id("report")
        generated_at = self._utc_now()
        self.conn.execute(
            """
            INSERT INTO reports (
                id, session_id, room_id, markdown, sections_json, generated_at, provider, model
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_id,
                session_id,
                room_id,
                markdown,
                self._dumps_json(sections),
                generated_at,
                provider,
                model,
            ),
        )
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
        return self.payloads.report(row)

    def get_latest_report(self, session_id: str) -> dict | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM reports
            WHERE session_id = ?
            ORDER BY generated_at DESC
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()
        return self.payloads.report(row)

    def _load_room_participants(self, room_id: str) -> tuple[list[sqlite3.Row], list[sqlite3.Row]]:
        active_rows = self.conn.execute(
            """
            SELECT *
            FROM room_participants
            WHERE room_id = ? AND status = 'active'
            ORDER BY position ASC, created_at ASC
            """,
            (room_id,),
        ).fetchall()
        benched_rows = self.conn.execute(
            """
            SELECT *
            FROM room_participants
            WHERE room_id = ? AND status = 'benched'
            ORDER BY updated_at DESC, created_at ASC
            """,
            (room_id,),
        ).fetchall()
        return active_rows, benched_rows

    def _load_current_room_session(self, room_id: str, current_session_id: str | None) -> sqlite3.Row | None:
        current_session = None
        if current_session_id:
            current_session = self.conn.execute(
                "SELECT * FROM sessions WHERE id = ?",
                (current_session_id,),
            ).fetchone()
        if current_session:
            return current_session
        return self.conn.execute(
            """
            SELECT *
            FROM sessions
            WHERE room_id = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (room_id,),
        ).fetchone()

    def _load_session_bundle(self, session_id: str | None, *, message_limit: int, review_limit: int) -> dict:
        if not session_id:
            return {
                "messages": [],
                "pinnedMessages": [],
                "observerReviews": [],
                "factCheck": None,
                "report": None,
            }
        message_rows = self.conn.execute(
            """
            SELECT payload_json
            FROM messages
            WHERE session_id = ?
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (session_id, message_limit),
        ).fetchall()
        pinned_messages = self.repository.list_pinned_messages(session_id)
        pinned_lookup = {item.get("id") for item in pinned_messages}
        messages: list[dict] = []
        for row in message_rows:
            payload = self._loads_json(row["payload_json"], {})
            payload["pinned"] = payload.get("id") in pinned_lookup
            messages.append(payload)
        review_rows = self.conn.execute(
            """
            SELECT *
            FROM observer_reviews
            WHERE session_id = ?
            ORDER BY round_number DESC
            LIMIT ?
            """,
            (session_id, review_limit),
        ).fetchall()
        return {
            "messages": messages,
            "pinnedMessages": pinned_messages,
            "observerReviews": [self.payloads.observer_review(review) for review in review_rows],
            "factCheck": self.get_latest_fact_check_run(session_id),
            "report": self.get_latest_report(session_id),
        }

    def _compose_snapshot(
        self,
        *,
        room: sqlite3.Row,
        session: sqlite3.Row | None,
        active_rows: list[sqlite3.Row],
        benched_rows: list[sqlite3.Row],
        session_bundle: dict,
        planned_events: list[dict],
    ) -> dict:
        return {
            "room": self.payloads.room(room),
            "participants": {
                "active": [self.payloads.participant(row) for row in active_rows],
                "benched": [self.payloads.participant(row) for row in benched_rows],
            },
            "inventory": self.repository.list_saved_profiles(),
            "teamPresets": self.repository.list_team_presets(),
            "customSpecialtyGroups": self.repository.list_custom_specialty_groups(),
            "session": self.payloads.session(session) if session else None,
            "messages": session_bundle["messages"],
            "pinnedMessages": session_bundle["pinnedMessages"],
            "observerReviews": session_bundle["observerReviews"],
            "report": session_bundle["report"],
            "factCheck": session_bundle["factCheck"],
            "plannedEvents": planned_events,
        }

    def _load_fact_check_claims(self, run_id: str) -> list[dict]:
        claim_rows = self.conn.execute(
            """
            SELECT *
            FROM fact_check_claims
            WHERE run_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (run_id,),
        ).fetchall()
        return [self.payloads.fact_check_claim(item) for item in claim_rows]
