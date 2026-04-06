from __future__ import annotations

import json
import os
import sqlite3
import uuid
from copy import deepcopy
from datetime import datetime, timezone


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def dumps_json(value) -> str:
    return json.dumps(value or {}, ensure_ascii=False)


def loads_json(value, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


class Repository:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
        self._migrate_schema()

    def close(self):
        self.conn.close()

    def _create_tables(self):
        cur = self.conn.cursor()
        cur.executescript(
            """
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
                is_saved INTEGER NOT NULL DEFAULT 0,
                system_provided INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS rooms (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                observer_mode TEXT NOT NULL DEFAULT 'suggest',
                observer_provider TEXT,
                observer_model TEXT,
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
                created_at TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    def _migrate_schema(self):
        session_columns = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(sessions)").fetchall()
        }
        if "title" not in session_columns:
            self.conn.execute("ALTER TABLE sessions ADD COLUMN title TEXT NOT NULL DEFAULT ''")
            self.conn.commit()

    def bootstrap(self, default_profiles: list[dict], observer_provider: str | None, observer_model: str | None):
        now = utc_now()
        cur = self.conn.cursor()

        for profile in default_profiles:
            existing_profile = cur.execute(
                "SELECT id FROM character_profiles WHERE id = ?",
                (profile["id"],),
            ).fetchone()
            if existing_profile:
                cur.execute(
                    """
                    UPDATE character_profiles
                    SET
                        name = ?,
                        role = ?,
                        specialty = ?,
                        provider = ?,
                        model = ?,
                        emoji = ?,
                        mascot = ?,
                        is_saved = ?,
                        system_provided = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        profile["name"],
                        profile["role"],
                        profile["specialty"],
                        profile["provider"],
                        profile["model"],
                        profile["emoji"],
                        profile["mascot"],
                        int(profile.get("is_saved", 1)),
                        int(profile.get("system_provided", 1)),
                        now,
                        profile["id"],
                    ),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO character_profiles (
                        id, name, role, specialty, provider, model, emoji, mascot,
                        stats_json, strengths_json, weaknesses_json, summary, last_note,
                        is_saved, system_provided, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        profile["id"],
                        profile["name"],
                        profile["role"],
                        profile["specialty"],
                        profile["provider"],
                        profile["model"],
                        profile["emoji"],
                        profile["mascot"],
                        dumps_json(profile.get("stats")),
                        dumps_json(profile.get("strengths", [])),
                        dumps_json(profile.get("weaknesses", [])),
                        profile.get("summary", ""),
                        profile.get("last_note", ""),
                        int(profile.get("is_saved", 1)),
                        int(profile.get("system_provided", 1)),
                        now,
                        now,
                    ),
                )

            cur.execute(
                """
                UPDATE room_participants
                SET
                    name = ?,
                    role = ?,
                    specialty = ?,
                    provider = ?,
                    model = ?,
                    emoji = ?,
                    mascot = ?,
                    updated_at = ?
                WHERE profile_id = ?
                """,
                (
                    profile["name"],
                    profile["role"],
                    profile["specialty"],
                    profile["provider"],
                    profile["model"],
                    profile["emoji"],
                    profile["mascot"],
                    now,
                    profile["id"],
                ),
            )

        room_count = cur.execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
        if room_count == 0:
            room_id = make_id("room")
            cur.execute(
                """
                INSERT INTO rooms (
                    id, name, observer_mode, observer_provider, observer_model,
                    current_session_id, summary, last_topic, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    room_id,
                    "Главная комната",
                    "suggest",
                    observer_provider,
                    observer_model,
                    None,
                    "",
                    "",
                    now,
                    now,
                ),
            )

            profiles = cur.execute(
                "SELECT * FROM character_profiles WHERE system_provided = 1 ORDER BY created_at ASC"
            ).fetchall()
            for index, profile in enumerate(profiles):
                cur.execute(
                    """
                    INSERT INTO room_participants (
                        id, room_id, profile_id, status, position,
                        name, role, specialty, provider, model, emoji, mascot,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        make_id("seat"),
                        room_id,
                        profile["id"],
                        "active",
                        index,
                        profile["name"],
                        profile["role"],
                        profile["specialty"],
                        profile["provider"],
                        profile["model"],
                        profile["emoji"],
                        profile["mascot"],
                        now,
                        now,
                    ),
                )

            cur.execute(
                "INSERT OR REPLACE INTO app_state(key, value) VALUES('current_room_id', ?)",
                (room_id,),
            )
        else:
            current_room = cur.execute(
                "SELECT value FROM app_state WHERE key = 'current_room_id'"
            ).fetchone()
            if not current_room:
                first_room = cur.execute("SELECT id FROM rooms ORDER BY created_at ASC LIMIT 1").fetchone()
                if first_room:
                    cur.execute(
                        "INSERT OR REPLACE INTO app_state(key, value) VALUES('current_room_id', ?)",
                        (first_room["id"],),
                    )

        if observer_provider and observer_model:
            cur.execute(
                """
                UPDATE rooms
                SET observer_provider = ?, observer_model = ?, updated_at = ?
                WHERE observer_provider IS NULL
                   OR observer_model IS NULL
                   OR (observer_provider = 'ollama' AND observer_model NOT LIKE '%:cloud')
                """,
                (observer_provider, observer_model, now),
            )

        self.conn.commit()

    def get_current_room_id(self) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM app_state WHERE key = 'current_room_id'"
        ).fetchone()
        return row["value"] if row else None

    def set_current_room(self, room_id: str):
        self.conn.execute(
            "INSERT OR REPLACE INTO app_state(key, value) VALUES('current_room_id', ?)",
            (room_id,),
        )
        self.conn.commit()

    def normalize_incomplete_sessions(self):
        now = utc_now()
        self.conn.execute(
            """
            UPDATE sessions
            SET status = 'paused', updated_at = ?
            WHERE status IN ('running', 'pause_requested', 'observer_review', 'finalizing')
            """,
            (now,),
        )
        self.conn.commit()

    def _profile_payload(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "name": row["name"],
            "role": row["role"],
            "specialty": row["specialty"],
            "provider": row["provider"],
            "model": row["model"],
            "emoji": row["emoji"],
            "mascot": row["mascot"],
            "stats": loads_json(row["stats_json"], {}),
            "strengths": loads_json(row["strengths_json"], []),
            "weaknesses": loads_json(row["weaknesses_json"], []),
            "summary": row["summary"],
            "lastNote": row["last_note"],
            "isSaved": bool(row["is_saved"]),
            "systemProvided": bool(row["system_provided"]),
        }

    def _session_payload(self, row: sqlite3.Row | None) -> dict | None:
        if not row:
            return None
        return {
            "id": row["id"],
            "title": row["title"],
            "topic": row["topic"],
            "status": row["status"],
            "observerMode": row["observer_mode"],
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

    def _participant_payload(self, row: sqlite3.Row) -> dict:
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
            "provider": row["provider"],
            "model": row["model"],
            "emoji": row["emoji"],
            "mascot": row["mascot"],
            "stats": loads_json(profile["stats_json"], {}) if profile else {},
            "strengths": loads_json(profile["strengths_json"], []) if profile else [],
            "weaknesses": loads_json(profile["weaknesses_json"], []) if profile else [],
            "summary": profile["summary"] if profile else "",
            "lastNote": profile["last_note"] if profile else "",
            "isSavedProfile": bool(profile["is_saved"]) if profile else False,
            "systemProvided": bool(profile["system_provided"]) if profile else False,
        }

    def list_rooms(self) -> list[dict]:
        cur = self.conn.cursor()
        rooms = cur.execute(
            """
            SELECT
                r.*,
                (
                    SELECT COUNT(*)
                    FROM room_participants rp
                    WHERE rp.room_id = r.id AND rp.status = 'active'
                ) AS active_count,
                (
                    SELECT COUNT(*)
                    FROM room_participants rp
                    WHERE rp.room_id = r.id AND rp.status = 'benched'
                ) AS benched_count
            FROM rooms r
            ORDER BY r.updated_at DESC
            """
        ).fetchall()

        result = []
        for room in rooms:
            latest_session = cur.execute(
                """
                SELECT id, title, topic, status, last_round_number, updated_at
                FROM sessions
                WHERE room_id = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (room["id"],),
            ).fetchone()
            result.append({
                "id": room["id"],
                "name": room["name"],
                "observerMode": room["observer_mode"],
                "observerProvider": room["observer_provider"],
                "observerModel": room["observer_model"],
                "summary": room["summary"],
                "lastTopic": room["last_topic"],
                "activeCount": room["active_count"],
                "benchedCount": room["benched_count"],
                "latestSession": {
                    "id": latest_session["id"],
                    "title": latest_session["title"],
                    "topic": latest_session["topic"],
                    "status": latest_session["status"],
                    "lastRoundNumber": latest_session["last_round_number"],
                    "updatedAt": latest_session["updated_at"],
                } if latest_session else None,
            })
        return result

    def list_saved_profiles(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM character_profiles WHERE is_saved = 1 ORDER BY updated_at DESC, name ASC"
        ).fetchall()
        return [self._profile_payload(row) for row in rows]

    def room_exists(self, room_id: str) -> bool:
        return bool(self.conn.execute("SELECT 1 FROM rooms WHERE id = ?", (room_id,)).fetchone())

    def get_profile(self, profile_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM character_profiles WHERE id = ?", (profile_id,)).fetchone()
        return self._profile_payload(row) if row else None

    def get_room_snapshot(self, room_id: str) -> dict | None:
        room = self.conn.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
        if not room:
            return None

        self.set_current_room(room_id)

        active = self.conn.execute(
            """
            SELECT *
            FROM room_participants
            WHERE room_id = ? AND status = 'active'
            ORDER BY position ASC, created_at ASC
            """,
            (room_id,),
        ).fetchall()
        benched = self.conn.execute(
            """
            SELECT *
            FROM room_participants
            WHERE room_id = ? AND status = 'benched'
            ORDER BY updated_at DESC, created_at ASC
            """,
            (room_id,),
        ).fetchall()

        current_session = None
        if room["current_session_id"]:
            current_session = self.conn.execute(
                "SELECT * FROM sessions WHERE id = ?",
                (room["current_session_id"],),
            ).fetchone()
        if not current_session:
            current_session = self.conn.execute(
                """
                SELECT *
                FROM sessions
                WHERE room_id = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (room_id,),
            ).fetchone()

        messages = []
        observer_reviews = []
        if current_session:
            message_rows = self.conn.execute(
                """
                SELECT payload_json
                FROM messages
                WHERE session_id = ?
                ORDER BY created_at ASC
                LIMIT 300
                """,
                (current_session["id"],),
            ).fetchall()
            messages = [loads_json(row["payload_json"], {}) for row in message_rows]

            review_rows = self.conn.execute(
                """
                SELECT *
                FROM observer_reviews
                WHERE session_id = ?
                ORDER BY round_number DESC
                LIMIT 12
                """,
                (current_session["id"],),
            ).fetchall()
            observer_reviews = [
                {
                    "id": review["id"],
                    "roundNumber": review["round_number"],
                    "summary": review["summary"],
                    "recommendation": review["recommendation"],
                    "chronicleAfter": review["chronicle_after"],
                    "comments": loads_json(review["comments_json"], {}),
                    "achievements": loads_json(review["achievements_json"], []),
                    "statsDelta": loads_json(review["stats_delta_json"], {}),
                }
                for review in review_rows
            ]

        return {
            "room": {
                "id": room["id"],
                "name": room["name"],
                "observerMode": room["observer_mode"],
                "observerProvider": room["observer_provider"],
                "observerModel": room["observer_model"],
                "summary": room["summary"],
                "lastTopic": room["last_topic"],
            },
            "participants": {
                "active": [self._participant_payload(row) for row in active],
                "benched": [self._participant_payload(row) for row in benched],
            },
            "inventory": self.list_saved_profiles(),
            "session": self._session_payload(current_session) if current_session else None,
            "messages": messages,
            "observerReviews": observer_reviews,
        }

    def list_room_sessions(self, room_id: str, query: str = "", limit: int = 80) -> list[dict]:
        search = (query or "").strip()
        params: list[object] = [room_id]
        where = "WHERE s.room_id = ?"
        if search:
            like = f"%{search}%"
            where += """
                AND (
                    s.title LIKE ?
                    OR s.topic LIKE ?
                    OR EXISTS (
                        SELECT 1
                        FROM messages m
                        WHERE m.session_id = s.id AND m.payload_json LIKE ?
                    )
                )
            """
            params.extend([like, like, like])
        params.append(max(1, min(int(limit or 80), 200)))

        rows = self.conn.execute(
            f"""
            SELECT
                s.*,
                (
                    SELECT COUNT(*)
                    FROM messages m
                    WHERE m.session_id = s.id
                ) AS message_count,
                (
                    SELECT COUNT(*)
                    FROM rounds r
                    WHERE r.session_id = s.id
                ) AS round_count
            FROM sessions s
            {where}
            ORDER BY s.updated_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

        result = []
        for row in rows:
            result.append({
                **self._session_payload(row),
                "messageCount": row["message_count"],
                "roundCount": row["round_count"],
                "preview": (row["chronicle"] or row["topic"] or "")[:220],
            })
        return result

    def get_session_snapshot(self, session_id: str, *, make_current: bool = False) -> dict | None:
        session = self.conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not session:
            return None
        room_id = session["room_id"]
        room = self.conn.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
        if not room:
            return None
        if make_current:
            self.set_current_room(room_id)
            self.update_room_settings(room_id, current_session_id=session_id, last_topic=session["topic"])

        active = self.conn.execute(
            """
            SELECT *
            FROM room_participants
            WHERE room_id = ? AND status = 'active'
            ORDER BY position ASC, created_at ASC
            """,
            (room_id,),
        ).fetchall()
        benched = self.conn.execute(
            """
            SELECT *
            FROM room_participants
            WHERE room_id = ? AND status = 'benched'
            ORDER BY updated_at DESC, created_at ASC
            """,
            (room_id,),
        ).fetchall()
        message_rows = self.conn.execute(
            """
            SELECT payload_json
            FROM messages
            WHERE session_id = ?
            ORDER BY created_at ASC
            LIMIT 800
            """,
            (session_id,),
        ).fetchall()
        review_rows = self.conn.execute(
            """
            SELECT *
            FROM observer_reviews
            WHERE session_id = ?
            ORDER BY round_number DESC
            LIMIT 24
            """,
            (session_id,),
        ).fetchall()

        return {
            "room": {
                "id": room["id"],
                "name": room["name"],
                "observerMode": room["observer_mode"],
                "observerProvider": room["observer_provider"],
                "observerModel": room["observer_model"],
                "summary": room["summary"],
                "lastTopic": room["last_topic"],
            },
            "participants": {
                "active": [self._participant_payload(row) for row in active],
                "benched": [self._participant_payload(row) for row in benched],
            },
            "inventory": self.list_saved_profiles(),
            "session": self._session_payload(session),
            "messages": [loads_json(row["payload_json"], {}) for row in message_rows],
            "observerReviews": [
                {
                    "id": review["id"],
                    "roundNumber": review["round_number"],
                    "summary": review["summary"],
                    "recommendation": review["recommendation"],
                    "chronicleAfter": review["chronicle_after"],
                    "comments": loads_json(review["comments_json"], {}),
                    "achievements": loads_json(review["achievements_json"], []),
                    "statsDelta": loads_json(review["stats_delta_json"], {}),
                }
                for review in review_rows
            ],
        }

    def set_current_session(self, session_id: str) -> dict | None:
        snapshot = self.get_session_snapshot(session_id, make_current=True)
        return snapshot

    def rename_session(self, session_id: str, title: str):
        self.update_session(session_id, {"title": title.strip()})

    def delete_session(self, session_id: str):
        session = self.conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not session:
            return
        room_id = session["room_id"]
        self.conn.execute("DELETE FROM observer_reviews WHERE session_id = ?", (session_id,))
        self.conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        self.conn.execute("DELETE FROM rounds WHERE session_id = ?", (session_id,))
        self.conn.execute("DELETE FROM room_events WHERE session_id = ?", (session_id,))
        self.conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

        room = self.conn.execute("SELECT current_session_id FROM rooms WHERE id = ?", (room_id,)).fetchone()
        if room and room["current_session_id"] == session_id:
            next_session = self.conn.execute(
                """
                SELECT id, topic
                FROM sessions
                WHERE room_id = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (room_id,),
            ).fetchone()
            self.conn.execute(
                "UPDATE rooms SET current_session_id = ?, last_topic = ?, updated_at = ? WHERE id = ?",
                (
                    next_session["id"] if next_session else None,
                    next_session["topic"] if next_session else "",
                    utc_now(),
                    room_id,
                ),
            )
        self.conn.commit()

    def export_session_markdown(self, session_id: str) -> str | None:
        snapshot = self.get_session_snapshot(session_id, make_current=False)
        if not snapshot or not snapshot["session"]:
            return None
        session = snapshot["session"]
        room = snapshot["room"]
        title = session.get("title") or session["topic"] or "Сессия"
        lines = [
            f"# {title}",
            "",
            f"- Комната: {room['name']}",
            f"- Статус: {session['status']}",
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
        return "\n".join(lines).strip() + "\n"

    def create_room(self, name: str, observer_mode: str, observer_provider: str | None, observer_model: str | None) -> str:
        room_id = make_id("room")
        now = utc_now()
        self.conn.execute(
            """
            INSERT INTO rooms (
                id, name, observer_mode, observer_provider, observer_model,
                current_session_id, summary, last_topic, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (room_id, name, observer_mode, observer_provider, observer_model, None, "", "", now, now),
        )
        self.conn.commit()
        self.set_current_room(room_id)
        return room_id

    def rename_room(self, room_id: str, name: str):
        self.conn.execute(
            "UPDATE rooms SET name = ?, updated_at = ? WHERE id = ?",
            (name, utc_now(), room_id),
        )
        self.conn.commit()

    def delete_room(self, room_id: str):
        cur = self.conn.cursor()
        session_rows = cur.execute("SELECT id FROM sessions WHERE room_id = ?", (room_id,)).fetchall()
        session_ids = [row["id"] for row in session_rows]
        if session_ids:
            placeholders = ",".join("?" for _ in session_ids)
            cur.execute(f"DELETE FROM messages WHERE session_id IN ({placeholders})", session_ids)
            cur.execute(f"DELETE FROM rounds WHERE session_id IN ({placeholders})", session_ids)
            cur.execute(f"DELETE FROM observer_reviews WHERE session_id IN ({placeholders})", session_ids)
            cur.execute(f"DELETE FROM room_events WHERE session_id IN ({placeholders})", session_ids)
        cur.execute("DELETE FROM sessions WHERE room_id = ?", (room_id,))
        cur.execute("DELETE FROM room_events WHERE room_id = ?", (room_id,))
        cur.execute("DELETE FROM room_participants WHERE room_id = ?", (room_id,))
        cur.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
        self.conn.commit()

        current_room_id = self.get_current_room_id()
        if current_room_id == room_id:
            first_room = cur.execute("SELECT id FROM rooms ORDER BY updated_at DESC LIMIT 1").fetchone()
            self.set_current_room(first_room["id"] if first_room else "")

    def create_profile(self, data: dict, is_saved: bool, system_provided: bool = False) -> str:
        profile_id = data.get("id") or make_id("char")
        now = utc_now()
        self.conn.execute(
            """
            INSERT INTO character_profiles (
                id, name, role, specialty, provider, model, emoji, mascot,
                stats_json, strengths_json, weaknesses_json, summary, last_note,
                is_saved, system_provided, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                profile_id,
                data["name"],
                data["role"],
                data["specialty"],
                data["provider"],
                data["model"],
                data["emoji"],
                data["mascot"],
                dumps_json(data.get("stats", {})),
                dumps_json(data.get("strengths", [])),
                dumps_json(data.get("weaknesses", [])),
                data.get("summary", ""),
                data.get("lastNote", "Новый герой ещё не оценён Хрономантом."),
                int(is_saved),
                int(system_provided),
                now,
                now,
            ),
        )
        self.conn.commit()
        return profile_id

    def update_profile(self, profile_id: str, fields: dict):
        if not fields:
            return
        mapping = {
            "name": "name",
            "role": "role",
            "specialty": "specialty",
            "provider": "provider",
            "model": "model",
            "emoji": "emoji",
            "mascot": "mascot",
            "summary": "summary",
            "lastNote": "last_note",
            "isSaved": "is_saved",
            "systemProvided": "system_provided",
        }
        updates: list[str] = []
        values: list[object] = []
        for key, column in mapping.items():
            if key in fields:
                updates.append(f"{column} = ?")
                values.append(fields[key])
        if "stats" in fields:
            updates.append("stats_json = ?")
            values.append(dumps_json(fields["stats"]))
        if "strengths" in fields:
            updates.append("strengths_json = ?")
            values.append(dumps_json(fields["strengths"]))
        if "weaknesses" in fields:
            updates.append("weaknesses_json = ?")
            values.append(dumps_json(fields["weaknesses"]))
        updates.append("updated_at = ?")
        values.append(utc_now())
        values.append(profile_id)
        self.conn.execute(
            f"UPDATE character_profiles SET {', '.join(updates)} WHERE id = ?",
            values,
        )
        self.conn.commit()

    def delete_profile(self, profile_id: str):
        usage = self.conn.execute(
            "SELECT COUNT(*) FROM room_participants WHERE profile_id = ?",
            (profile_id,),
        ).fetchone()[0]
        if usage:
            self.update_profile(profile_id, {"isSaved": 0})
        else:
            self.conn.execute("DELETE FROM character_profiles WHERE id = ?", (profile_id,))
            self.conn.commit()

    def sync_participant_to_profile(self, participant_id: str):
        row = self.conn.execute(
            "SELECT * FROM room_participants WHERE id = ?",
            (participant_id,),
        ).fetchone()
        if not row:
            return
        self.update_profile(
            row["profile_id"],
            {
                "name": row["name"],
                "role": row["role"],
                "specialty": row["specialty"],
                "provider": row["provider"],
                "model": row["model"],
                "emoji": row["emoji"],
                "mascot": row["mascot"],
                "isSaved": 1,
            },
        )

    def _next_active_position(self, room_id: str) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(MAX(position), -1) AS max_position FROM room_participants WHERE room_id = ? AND status = 'active'",
            (room_id,),
        ).fetchone()
        return int(row["max_position"]) + 1

    def get_participant(self, participant_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM room_participants WHERE id = ?", (participant_id,)).fetchone()
        return self._participant_payload(row) if row else None

    def get_active_participants(self, room_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM room_participants WHERE room_id = ? AND status = 'active' ORDER BY position ASC, created_at ASC",
            (room_id,),
        ).fetchall()
        return [self._participant_payload(row) for row in rows]

    def add_participant_from_profile(self, room_id: str, profile_id: str, status: str = "active") -> str | None:
        existing = self.conn.execute(
            "SELECT * FROM room_participants WHERE room_id = ? AND profile_id = ? AND status != 'archived' ORDER BY created_at ASC LIMIT 1",
            (room_id, profile_id),
        ).fetchone()
        now = utc_now()
        if existing:
            position = self._next_active_position(room_id) if status == "active" else existing["position"]
            self.conn.execute(
                "UPDATE room_participants SET status = ?, position = ?, updated_at = ? WHERE id = ?",
                (status, position, now, existing["id"]),
            )
            self.conn.commit()
            return existing["id"]

        profile = self.conn.execute("SELECT * FROM character_profiles WHERE id = ?", (profile_id,)).fetchone()
        if not profile:
            return None
        participant_id = make_id("seat")
        position = self._next_active_position(room_id) if status == "active" else 0
        self.conn.execute(
            """
            INSERT INTO room_participants (
                id, room_id, profile_id, status, position,
                name, role, specialty, provider, model, emoji, mascot,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                participant_id,
                room_id,
                profile_id,
                status,
                position,
                profile["name"],
                profile["role"],
                profile["specialty"],
                profile["provider"],
                profile["model"],
                profile["emoji"],
                profile["mascot"],
                now,
                now,
            ),
        )
        self.conn.commit()
        return participant_id

    def create_and_add_participant(self, room_id: str, data: dict, save_to_inventory: bool) -> str | None:
        profile_id = self.create_profile(data, is_saved=save_to_inventory, system_provided=False)
        participant_id = self.add_participant_from_profile(room_id, profile_id, status="active")
        if participant_id:
            self.update_participant(
                participant_id,
                {
                    "name": data["name"],
                    "role": data["role"],
                    "specialty": data["specialty"],
                    "provider": data["provider"],
                    "model": data["model"],
                    "emoji": data["emoji"],
                    "mascot": data["mascot"],
                },
            )
        return participant_id

    def update_participant(self, participant_id: str, fields: dict):
        if not fields:
            return
        mapping = {
            "name": "name",
            "role": "role",
            "specialty": "specialty",
            "provider": "provider",
            "model": "model",
            "emoji": "emoji",
            "mascot": "mascot",
            "status": "status",
            "position": "position",
        }
        updates = []
        values: list[object] = []
        for key, column in mapping.items():
            if key in fields:
                updates.append(f"{column} = ?")
                values.append(fields[key])
        updates.append("updated_at = ?")
        values.append(utc_now())
        values.append(participant_id)
        self.conn.execute(
            f"UPDATE room_participants SET {', '.join(updates)} WHERE id = ?",
            values,
        )
        self.conn.commit()

    def bench_participant(self, participant_id: str):
        self.update_participant(participant_id, {"status": "benched"})

    def restore_participant(self, participant_id: str):
        row = self.conn.execute(
            "SELECT room_id FROM room_participants WHERE id = ?",
            (participant_id,),
        ).fetchone()
        if row:
            self.update_participant(
                participant_id,
                {"status": "active", "position": self._next_active_position(row["room_id"])},
            )

    def update_room_settings(self, room_id: str, *, name: str | None = None, observer_mode: str | None = None, observer_provider: str | None = None, observer_model: str | None = None, summary: str | None = None, last_topic: str | None = None, current_session_id: str | None = None):
        updates = []
        values: list[object] = []
        if name is not None:
            updates.append("name = ?")
            values.append(name)
        if observer_mode is not None:
            updates.append("observer_mode = ?")
            values.append(observer_mode)
        if observer_provider is not None:
            updates.append("observer_provider = ?")
            values.append(observer_provider)
        if observer_model is not None:
            updates.append("observer_model = ?")
            values.append(observer_model)
        if summary is not None:
            updates.append("summary = ?")
            values.append(summary)
        if last_topic is not None:
            updates.append("last_topic = ?")
            values.append(last_topic)
        if current_session_id is not None:
            updates.append("current_session_id = ?")
            values.append(current_session_id)
        updates.append("updated_at = ?")
        values.append(utc_now())
        values.append(room_id)
        self.conn.execute(
            f"UPDATE rooms SET {', '.join(updates)} WHERE id = ?",
            values,
        )
        self.conn.commit()

    def create_session(self, room_id: str, topic: str, observer_mode: str) -> dict:
        now = utc_now()
        session_id = make_id("session")
        self.conn.execute(
            """
            INSERT INTO sessions (
                id, room_id, title, topic, status, observer_mode, chronicle, wrap_requested,
                final_requested, final_round_planned, extension_count, last_round_number,
                created_at, updated_at, started_at, ended_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                room_id,
                "",
                topic,
                "running",
                observer_mode,
                "",
                0,
                0,
                0,
                0,
                0,
                now,
                now,
                now,
                None,
            ),
        )
        self.conn.commit()
        self.update_room_settings(room_id, current_session_id=session_id, last_topic=topic)
        return self.get_session(session_id)

    def get_session(self, session_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return self._session_payload(row)

    def get_current_session(self, room_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT current_session_id FROM rooms WHERE id = ?",
            (room_id,),
        ).fetchone()
        if not row or not row["current_session_id"]:
            return None
        return self.get_session(row["current_session_id"])

    def update_session(self, session_id: str, fields: dict):
        if not fields:
            return
        mapping = {
            "title": "title",
            "topic": "topic",
            "status": "status",
            "observerMode": "observer_mode",
            "chronicle": "chronicle",
            "wrapRequested": "wrap_requested",
            "finalRequested": "final_requested",
            "finalRoundPlanned": "final_round_planned",
            "extensionCount": "extension_count",
            "lastRoundNumber": "last_round_number",
            "startedAt": "started_at",
            "endedAt": "ended_at",
        }
        updates: list[str] = []
        values: list[object] = []
        for key, column in mapping.items():
            if key in fields:
                updates.append(f"{column} = ?")
                values.append(fields[key])
        updates.append("updated_at = ?")
        values.append(utc_now())
        values.append(session_id)
        self.conn.execute(
            f"UPDATE sessions SET {', '.join(updates)} WHERE id = ?",
            values,
        )
        self.conn.commit()

    def create_round(self, room_id: str, session_id: str, round_number: int) -> str:
        round_id = make_id("round")
        self.conn.execute(
            """
            INSERT INTO rounds (
                id, room_id, session_id, round_number, status, summary, chronicle_after,
                recommendation, created_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                round_id,
                room_id,
                session_id,
                round_number,
                "running",
                "",
                "",
                "continue",
                utc_now(),
                None,
            ),
        )
        self.conn.commit()
        return round_id

    def complete_round(self, round_id: str, review: dict):
        self.conn.execute(
            """
            UPDATE rounds
            SET status = ?, summary = ?, chronicle_after = ?, recommendation = ?, completed_at = ?
            WHERE id = ?
            """,
            (
                "completed",
                review.get("roundSummary", ""),
                review.get("chronicle", ""),
                review.get("recommendation", "continue"),
                utc_now(),
                round_id,
            ),
        )
        self.conn.commit()

    def append_message(self, room_id: str, session_id: str, payload: dict, *, round_id: str | None = None, round_number: int | None = None, message_type: str = "status", author_type: str = "system", participant_id: str | None = None):
        message_id = payload.get("id") or make_id("msg")
        enriched = {"id": message_id, **deepcopy(payload)}
        self.conn.execute(
            """
            INSERT INTO messages (
                id, room_id, session_id, round_id, round_number,
                message_type, author_type, participant_id, created_at, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                room_id,
                session_id,
                round_id,
                round_number,
                message_type,
                author_type,
                participant_id,
                utc_now(),
                dumps_json(enriched),
            ),
        )
        self.conn.commit()
        return enriched

    def list_round_messages(self, session_id: str, round_number: int) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT payload_json
            FROM messages
            WHERE session_id = ? AND round_number = ? AND author_type IN ('agent', 'user')
            ORDER BY created_at ASC
            """,
            (session_id, round_number),
        ).fetchall()
        return [loads_json(row["payload_json"], {}) for row in rows]

    def list_session_messages(self, session_id: str, limit: int = 60) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT payload_json
            FROM messages
            WHERE session_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
        return [loads_json(row["payload_json"], {}) for row in reversed(rows)]

    def add_room_event(self, room_id: str, session_id: str | None, event_type: str, payload: dict):
        self.conn.execute(
            """
            INSERT INTO room_events (id, room_id, session_id, event_type, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (make_id("event"), room_id, session_id, event_type, dumps_json(payload), utc_now()),
        )
        self.conn.commit()

    def list_recent_room_events(self, room_id: str, session_id: str | None, limit: int = 10) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM room_events
            WHERE room_id = ? AND (session_id = ? OR session_id IS NULL)
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (room_id, session_id, limit),
        ).fetchall()
        return [
            {
                "type": row["event_type"],
                "payload": loads_json(row["payload_json"], {}),
                "createdAt": row["created_at"],
            }
            for row in rows
        ]

    def save_observer_review(self, room_id: str, session_id: str, round_id: str, round_number: int, review: dict):
        self.conn.execute(
            """
            INSERT INTO observer_reviews (
                id, room_id, session_id, round_id, round_number, summary,
                chronicle_before, chronicle_after, recommendation, suggested_rounds_left,
                comments_json, achievements_json, stats_delta_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                make_id("review"),
                room_id,
                session_id,
                round_id,
                round_number,
                review.get("roundSummary", ""),
                review.get("chronicleBefore", ""),
                review.get("chronicle", ""),
                review.get("recommendation", "continue"),
                review.get("suggestedRoundsLeft"),
                dumps_json(review.get("participantComments", {})),
                dumps_json(review.get("achievements", [])),
                dumps_json(review.get("statsDelta", {})),
                utc_now(),
            ),
        )
        self.conn.commit()

    def apply_stats_delta(self, stats_delta: dict, comments: dict):
        for profile_id, delta in stats_delta.items():
            row = self.conn.execute("SELECT * FROM character_profiles WHERE id = ?", (profile_id,)).fetchone()
            if not row:
                continue
            stats = loads_json(row["stats_json"], {})
            for key, change in delta.items():
                current = int(stats.get(key, 50))
                stats[key] = max(0, min(100, current + int(change)))
            note = comments.get(profile_id) or row["last_note"]
            self.update_profile(profile_id, {"stats": stats, "lastNote": note})
