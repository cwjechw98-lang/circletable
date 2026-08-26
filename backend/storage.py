from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from copy import deepcopy
from datetime import datetime, timezone

from storage_layers import BusinessAggregates, PayloadBuilder, SchemaManager


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def slugify_label(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return slug[:48].strip("-") or "expertise"


def dumps_json(value) -> str:
    return json.dumps(value or {}, ensure_ascii=False)


def loads_json(value, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


STAT_KEYS = ("insight", "focus", "depth", "cooperation", "showmanship")


class Repository:
    def __init__(self, db_path: str):
        self.db_path = db_path
        directory = os.path.dirname(db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._schema = SchemaManager(
            self.conn,
            normalize_room_settings=self._normalize_room_settings,
            loads_json=loads_json,
            dumps_json=dumps_json,
            utc_now=utc_now,
        )
        self._payloads = PayloadBuilder(
            self,
            loads_json=loads_json,
            normalize_room_settings=self._normalize_room_settings,
        )
        self._aggregates = BusinessAggregates(
            self,
            payloads=self._payloads,
            loads_json=loads_json,
            dumps_json=dumps_json,
            utc_now=utc_now,
            make_id=make_id,
        )
        self._create_tables()
        self._migrate_schema()

    def close(self):
        self.conn.close()

    def _create_tables(self):
        self._schema.create_tables()

    def _migrate_schema(self):
        self._schema.migrate_schema()

    def _normalize_room_settings(self, settings: dict | None) -> dict:
        raw = dict(settings or {})
        available_tools = raw.get("available_tools", raw.get("availableTools"))
        if not isinstance(available_tools, list):
            available_tools = ["search_knowledge", "calculate"]
        legacy_available_tools = [
            str(tool)
            for tool in available_tools
            if str(tool) in {"search_knowledge", "web_search", "calculate"}
        ]
        if not legacy_available_tools:
            legacy_available_tools = ["search_knowledge", "calculate"]

        tools_enabled = bool(raw.get("tools_enabled", raw.get("toolsEnabled", False)))
        internet_mode = str(raw.get("internet_mode", raw.get("internetMode", "")) or "").strip().lower()
        if internet_mode not in {"off", "auto", "on"}:
            internet_mode = "auto" if tools_enabled and "web_search" in legacy_available_tools else "off"

        return {
            "internet_mode": internet_mode,
            "tools_enabled": tools_enabled,
            "available_tools": legacy_available_tools,
        }

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
                    id, name, observer_mode, density_mode, observer_provider, observer_model,
                    current_session_id, summary, last_topic, settings_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    room_id,
                    "Главная комната",
                    "suggest",
                    "normal",
                    observer_provider,
                    observer_model,
                    None,
                    "",
                    "",
                    dumps_json({"internet_mode": "auto"}),
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
        return self._payloads.profile(row)

    def _session_payload(self, row: sqlite3.Row | None) -> dict | None:
        return self._payloads.session(row)

    def _participant_payload(self, row: sqlite3.Row) -> dict:
        return self._payloads.participant(row)

    def _observer_review_payload(self, row: sqlite3.Row) -> dict:
        return self._payloads.observer_review(row)

    def _report_payload(self, row: sqlite3.Row | None) -> dict | None:
        return self._payloads.report(row)

    def _fact_check_claim_payload(self, row: sqlite3.Row) -> dict:
        return self._payloads.fact_check_claim(row)

    def _fact_check_run_payload(self, row: sqlite3.Row | None, *, claims: list[dict] | None = None) -> dict | None:
        return self._payloads.fact_check_run(row, claims=claims)

    def _model_reliability_payload(self, row: sqlite3.Row | None) -> dict | None:
        return self._payloads.model_reliability(row)

    def _session_insight_payload(self, row: sqlite3.Row | None) -> dict | None:
        return self._payloads.session_insight(row)

    def _planned_event_payload(self, row: sqlite3.Row) -> dict:
        return self._payloads.planned_event(row)

    def _custom_specialty_payload(self, row: sqlite3.Row | None) -> dict | None:
        return self._payloads.custom_specialty(row)

    def get_custom_specialty_label(self, value: str | None) -> str | None:
        if not value:
            return None
        row = self.conn.execute(
            "SELECT label FROM custom_specialties WHERE value = ?",
            (value,),
        ).fetchone()
        return row["label"] if row else None

    def _score_reliability_counts(self, counts: dict[str, int]) -> float:
        total = sum(max(int(counts.get(key, 0)), 0) for key in (
            "confirmed",
            "unverified",
            "contradicted",
            "disputed",
            "insufficient_evidence",
        ))
        if total <= 0:
            return 0.0
        weighted = (
            counts.get("confirmed", 0) * 1.0
            + counts.get("unverified", 0) * 0.45
            + counts.get("disputed", 0) * 0.25
            + counts.get("insufficient_evidence", 0) * 0.1
        )
        return round((weighted / total) * 100, 1)

    def _room_settings_payload(self, row: sqlite3.Row) -> dict:
        return self._payloads.room_settings(row)

    def _room_payload(self, row: sqlite3.Row) -> dict:
        return self._payloads.room(row)

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
                **self._room_payload(room),
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

    # --- Лаборатория персонажей (Фаза 1: досье) ---

    def _lab_career_stats(self, profile_id: str) -> dict:
        participant_rows = self.conn.execute(
            "SELECT id FROM room_participants WHERE profile_id = ?",
            (profile_id,),
        ).fetchall()
        participant_ids = [row["id"] for row in participant_rows]
        career = {
            "participantsCount": len(participant_ids),
            "messagesCount": 0,
            "sessionsCount": 0,
            "roundsSpoken": 0,
            "firstSeenAt": None,
            "lastSeenAt": None,
        }
        if not participant_ids:
            return career
        placeholders = ",".join("?" for _ in participant_ids)
        row = self.conn.execute(
            f"""
            SELECT COUNT(*) AS messages,
                   COUNT(DISTINCT session_id) AS sessions,
                   MIN(created_at) AS first_seen,
                   MAX(created_at) AS last_seen
            FROM messages
            WHERE participant_id IN ({placeholders})
            """,
            participant_ids,
        ).fetchone()
        rounds_row = self.conn.execute(
            f"""
            SELECT COUNT(DISTINCT round_id)
            FROM messages
            WHERE participant_id IN ({placeholders}) AND round_id IS NOT NULL
            """,
            participant_ids,
        ).fetchone()
        career.update({
            "messagesCount": int(row["messages"] or 0),
            "sessionsCount": int(row["sessions"] or 0),
            "roundsSpoken": int(rounds_row[0] or 0),
            "firstSeenAt": row["first_seen"],
            "lastSeenAt": row["last_seen"],
        })
        return career

    def _lab_review_entries(self, profile_id: str) -> list[dict]:
        entries: list[dict] = []
        rows = self.conn.execute(
            """
            SELECT room_id, session_id, round_number, summary,
                   achievements_json, stats_delta_json, comments_json, created_at
            FROM observer_reviews
            ORDER BY created_at ASC, round_number ASC
            LIMIT 2000
            """
        ).fetchall()
        for row in rows:
            delta_map = loads_json(row["stats_delta_json"], {})
            delta = delta_map.get(profile_id)
            achievements = [
                item
                for item in loads_json(row["achievements_json"], [])
                if isinstance(item, dict) and item.get("profileId") == profile_id
            ]
            note = loads_json(row["comments_json"], {}).get(profile_id, "")
            if not delta and not achievements and not note:
                continue
            entries.append({
                "roomId": row["room_id"],
                "sessionId": row["session_id"],
                "roundNumber": int(row["round_number"] or 0),
                "createdAt": row["created_at"],
                "roundSummary": row["summary"] or "",
                "delta": {key: int((delta or {}).get(key, 0)) for key in STAT_KEYS},
                "achievements": [
                    {"title": item.get("title", "Заметный ход"), "reason": item.get("reason", "")}
                    for item in achievements
                ],
                "note": note,
            })
        return entries

    def list_lab_dossiers(self) -> list[dict]:
        dossiers: list[dict] = []
        for row in self.conn.execute(
            "SELECT * FROM character_profiles WHERE is_saved = 1 ORDER BY updated_at DESC, name ASC"
        ).fetchall():
            profile = self._profile_payload(row)
            career = self._lab_career_stats(profile["id"])
            review_count = self.conn.execute(
                """
                SELECT COUNT(*) FROM observer_reviews
                WHERE stats_delta_json LIKE ? OR achievements_json LIKE ?
                """,
                (f'%"{profile["id"]}"%', f'%"{profile["id"]}"%'),
            ).fetchone()[0]
            dossiers.append({
                **profile,
                "career": career,
                "reviewMentions": int(review_count or 0),
            })
        return dossiers

    def get_lab_dossier(self, profile_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM character_profiles WHERE id = ?",
            (profile_id,),
        ).fetchone()
        if not row:
            return None
        profile = self._profile_payload(row)
        entries = self._lab_review_entries(profile_id)

        totals = {key: 0 for key in STAT_KEYS}
        for entry in entries:
            for key, value in entry["delta"].items():
                totals[key] += value

        start_values = {
            key: int(profile["stats"].get(key, 50)) - totals[key]
            for key in STAT_KEYS
        }
        cumulative = dict(start_values)
        evolution: list[dict] = []
        achievements_timeline: list[dict] = []
        notes: list[dict] = []
        for entry in entries:
            for key in STAT_KEYS:
                cumulative[key] += entry["delta"][key]
            evolution.append({
                "roundNumber": entry["roundNumber"],
                "sessionId": entry["sessionId"],
                "createdAt": entry["createdAt"],
                "delta": entry["delta"],
                "values": dict(cumulative),
            })
            for achievement in entry["achievements"]:
                achievements_timeline.append({
                    "roundNumber": entry["roundNumber"],
                    "sessionId": entry["sessionId"],
                    "createdAt": entry["createdAt"],
                    "title": achievement["title"],
                    "reason": achievement["reason"],
                })
            if entry["note"]:
                notes.append({
                    "roundNumber": entry["roundNumber"],
                    "createdAt": entry["createdAt"],
                    "text": entry["note"],
                })

        review_count = self.conn.execute(
            """
            SELECT COUNT(*) FROM observer_reviews
            WHERE stats_delta_json LIKE ? OR achievements_json LIKE ?
            """,
            (f'%"{profile_id}"%', f'%"{profile_id}"%'),
        ).fetchone()[0]

        return {
            **profile,
            "career": self._lab_career_stats(profile_id),
            "statsTotals": totals,
            "startValues": start_values,
            "evolution": evolution,
            "achievements": achievements_timeline,
            "notes": notes[-8:],
            "reviewMentions": int(review_count or 0),
        }


    def list_custom_specialties(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM custom_specialties ORDER BY group_label ASC, label ASC"
        ).fetchall()
        return [self._custom_specialty_payload(row) for row in rows]

    def list_custom_specialty_groups(self) -> list[dict]:
        grouped: dict[str, list[dict]] = {}
        for item in self.list_custom_specialties():
            group_label = item.get("groupLabel") or "Кастомные оптики"
            grouped.setdefault(group_label, []).append({
                "id": item["id"],
                "value": item["value"],
                "label": item["label"],
                "description": item.get("description", ""),
                "groupLabel": group_label,
            })
        return [
            {"label": group_label, "options": options}
            for group_label, options in grouped.items()
        ]

    # --- Кастомные провайдеры (OpenAI-совместимые) ---

    def list_custom_provider_records(self) -> list[dict]:
        """Полные записи включая api_key — только для внутренней регистрации."""
        rows = self.conn.execute(
            "SELECT * FROM custom_providers ORDER BY created_at ASC"
        ).fetchall()
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "base_url": row["base_url"],
                "api_key": row["api_key"],
            }
            for row in rows
        ]

    def list_custom_providers(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM custom_providers ORDER BY created_at ASC"
        ).fetchall()
        return [self._custom_provider_payload(row) for row in rows]

    def _custom_provider_payload(self, row: sqlite3.Row) -> dict:
        key = row["api_key"] or ""
        key_hint = f"...{key[-4:]}" if len(key) > 4 else ("***" if key else "")
        return {
            "id": row["id"],
            "name": row["name"],
            "baseUrl": row["base_url"],
            "keyHint": key_hint,
            "createdAt": row["created_at"],
        }

    def create_custom_provider(self, name: str, base_url: str, api_key: str = "") -> dict:
        provider_id = make_id("prov")
        now = utc_now()
        self.conn.execute(
            """
            INSERT INTO custom_providers (id, name, base_url, api_key, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (provider_id, name, base_url.rstrip("/"), api_key, now, now),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM custom_providers WHERE id = ?",
            (provider_id,),
        ).fetchone()
        return self._custom_provider_payload(row)

    def delete_custom_provider(self, provider_id: str) -> bool:
        cursor = self.conn.execute(
            "DELETE FROM custom_providers WHERE id = ?",
            (provider_id,),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    # --- Настройки приложения (UI-editable) ---

    def get_setting(self, key: str, default=None):
        row = self.conn.execute(
            "SELECT value FROM app_settings WHERE key = ?",
            (key,),
        ).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        self.conn.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, value, utc_now()),
        )
        self.conn.commit()

    def all_settings(self) -> dict[str, str]:
        rows = self.conn.execute("SELECT key, value FROM app_settings").fetchall()
        return {row["key"]: row["value"] for row in rows}

    def add_token_usage(
        self,
        *,
        id: str,
        session_id: str | None,
        room_id: str | None,
        round_number: int | None,
        kind: str,
        provider: str | None,
        model: str | None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost: float | None = None,
    ):
        self.conn.execute(
            """
            INSERT INTO token_usage
                (id, session_id, room_id, round_number, kind, provider, model, prompt_tokens, completion_tokens, cost, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (id, session_id, room_id, round_number, kind, provider, model, prompt_tokens, completion_tokens, cost, utc_now()),
        )
        self.conn.commit()

    def token_usage_summary(self, session_id: str) -> dict:
        rows = self.conn.execute(
            "SELECT kind, model, round_number, prompt_tokens, completion_tokens, cost FROM token_usage WHERE session_id = ?",
            (session_id,),
        ).fetchall()
        by_kind: dict[str, dict] = {}
        by_model: dict[str, dict] = {}
        by_round: dict[int, dict] = {}
        total_prompt = total_completion = 0
        total_cost = 0.0
        has_cost = False
        for row in rows:
            row_cost = row["cost"]
            for bucket, key in ((by_kind, row["kind"]), (by_model, row["model"] or "—")):
                cell = bucket.setdefault(key, {"calls": 0, "promptTokens": 0, "completionTokens": 0})
                cell["calls"] += 1
                cell["promptTokens"] += row["prompt_tokens"]
                cell["completionTokens"] += row["completion_tokens"]
                if row_cost is not None:
                    has_cost = True
                    cell["cost"] = round(cell.get("cost", 0.0) + float(row_cost), 6)
            rcell = by_round.setdefault(row["round_number"] or 0, {"calls": 0, "promptTokens": 0, "completionTokens": 0})
            rcell["calls"] += 1
            rcell["promptTokens"] += row["prompt_tokens"]
            rcell["completionTokens"] += row["completion_tokens"]
            total_prompt += row["prompt_tokens"]
            total_completion += row["completion_tokens"]
            if row_cost is not None:
                total_cost += float(row_cost)
        return {
            "sessionId": session_id,
            "total": {
                "calls": len(rows),
                "promptTokens": total_prompt,
                "completionTokens": total_completion,
                "estimated": not has_cost,
                **({"cost": round(total_cost, 6)} if has_cost else {}),
            },
            "byKind": by_kind,
            "byModel": by_model,
            "byRound": [
                {"round": rnd, **cells}
                for rnd, cells in sorted(by_round.items(), key=lambda item: item[0])
            ],
        }

    def _unique_custom_specialty_value(self, label: str, value: str | None = None) -> str:
        base = re.sub(r"[^a-z0-9-]+", "-", (value or "").lower()).strip("-")
        if not base:
            base = f"custom-{slugify_label(label)}"
        if not base.startswith("custom-"):
            base = f"custom-{base}"
        candidate = base[:64].strip("-")
        suffix = 2
        while self.conn.execute("SELECT 1 FROM custom_specialties WHERE value = ?", (candidate,)).fetchone():
            suffix_text = f"-{suffix}"
            candidate = f"{base[:64 - len(suffix_text)].strip('-')}{suffix_text}"
            suffix += 1
        return candidate

    def create_custom_specialty(
        self,
        label: str,
        *,
        group_label: str = "Кастомные оптики",
        description: str = "",
        value: str | None = None,
    ) -> dict:
        normalized_label = label.strip()
        normalized_group = (group_label or "Кастомные оптики").strip() or "Кастомные оптики"
        existing = self.conn.execute(
            """
            SELECT *
            FROM custom_specialties
            WHERE lower(label) = lower(?) AND lower(group_label) = lower(?)
            """,
            (normalized_label, normalized_group),
        ).fetchone()
        if existing:
            return self._custom_specialty_payload(existing)

        now = utc_now()
        specialty_id = make_id("spec")
        specialty_value = self._unique_custom_specialty_value(normalized_label, value=value)
        self.conn.execute(
            """
            INSERT INTO custom_specialties (
                id, value, label, group_label, description, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                specialty_id,
                specialty_value,
                normalized_label,
                normalized_group,
                description.strip(),
                now,
                now,
            ),
        )
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM custom_specialties WHERE id = ?", (specialty_id,)).fetchone()
        return self._custom_specialty_payload(row)

    def update_custom_specialty(self, specialty_id: str, fields: dict) -> dict | None:
        current = self.conn.execute("SELECT * FROM custom_specialties WHERE id = ?", (specialty_id,)).fetchone()
        if not current:
            return None

        updates: list[str] = []
        values: list[object] = []
        if "label" in fields:
            label = str(fields.get("label") or "").strip()
            if label:
                updates.append("label = ?")
                values.append(label)
        if "groupLabel" in fields or "group_label" in fields:
            group_label = str(fields.get("groupLabel", fields.get("group_label")) or "").strip()
            updates.append("group_label = ?")
            values.append(group_label or "Кастомные оптики")
        if "description" in fields:
            updates.append("description = ?")
            values.append(str(fields.get("description") or "").strip())

        if not updates:
            return self._custom_specialty_payload(current)

        updates.append("updated_at = ?")
        values.extend([utc_now(), specialty_id])
        self.conn.execute(
            f"UPDATE custom_specialties SET {', '.join(updates)} WHERE id = ?",
            values,
        )
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM custom_specialties WHERE id = ?", (specialty_id,)).fetchone()
        return self._custom_specialty_payload(row)

    def custom_specialty_usage(self, value: str) -> int:
        profile_count = self.conn.execute(
            "SELECT COUNT(*) FROM character_profiles WHERE specialty = ?",
            (value,),
        ).fetchone()[0]
        participant_count = self.conn.execute(
            "SELECT COUNT(*) FROM room_participants WHERE specialty = ?",
            (value,),
        ).fetchone()[0]
        preset_count = self.conn.execute(
            "SELECT COUNT(*) FROM team_presets WHERE participants_json LIKE ?",
            (f"%{value}%",),
        ).fetchone()[0]
        return int(profile_count) + int(participant_count) + int(preset_count)

    def delete_custom_specialty(self, specialty_id: str) -> str:
        row = self.conn.execute("SELECT * FROM custom_specialties WHERE id = ?", (specialty_id,)).fetchone()
        if not row:
            return "missing"
        if self.custom_specialty_usage(row["value"]) > 0:
            return "in_use"
        self.conn.execute("DELETE FROM custom_specialties WHERE id = ?", (specialty_id,))
        self.conn.commit()
        return "deleted"

    def list_team_presets(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM team_presets ORDER BY updated_at DESC, name ASC"
        ).fetchall()
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "participants": loads_json(row["participants_json"], []),
                "createdAt": row["created_at"],
                "updatedAt": row["updated_at"],
            }
            for row in rows
        ]

    def create_team_preset(self, name: str, participants: list[dict]) -> dict:
        preset_id = make_id("preset")
        now = utc_now()
        payload = [
            {
                "profileId": item.get("profileId"),
                "name": item.get("name"),
                "role": item.get("role"),
                "specialty": item.get("specialty"),
                "provider": item.get("provider"),
                "model": item.get("model"),
                "emoji": item.get("emoji"),
                "mascot": item.get("mascot"),
            }
            for item in participants
        ]
        self.conn.execute(
            """
            INSERT INTO team_presets (id, name, participants_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (preset_id, name, dumps_json(payload), now, now),
        )
        self.conn.commit()
        return {
            "id": preset_id,
            "name": name,
            "participants": payload,
            "createdAt": now,
            "updatedAt": now,
        }

    def delete_team_preset(self, preset_id: str):
        self.conn.execute("DELETE FROM team_presets WHERE id = ?", (preset_id,))
        self.conn.commit()

    def _insert_room_participant(self, room_id: str, participant: dict, status: str = "active") -> str:
        participant_id = make_id("seat")
        now = utc_now()
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
                participant.get("profileId") or make_id("char"),
                status,
                position,
                participant["name"],
                participant["role"],
                participant["specialty"],
                participant["provider"],
                participant["model"],
                participant["emoji"],
                participant["mascot"],
                now,
                now,
            ),
        )
        self.conn.commit()
        return participant_id

    def apply_team_preset(self, room_id: str, preset_id: str) -> list[dict]:
        row = self.conn.execute("SELECT * FROM team_presets WHERE id = ?", (preset_id,)).fetchone()
        if not row:
            return []
        preset_participants = loads_json(row["participants_json"], [])
        for participant in self.get_active_participants(room_id):
            self.bench_participant(participant["id"])
        created: list[dict] = []
        for entry in preset_participants:
            participant_id = None
            profile_id = entry.get("profileId")
            if profile_id:
                participant_id = self.add_participant_from_profile(room_id, profile_id, status="active")
                if participant_id:
                    self.update_participant(
                        participant_id,
                        {
                            "name": entry.get("name"),
                            "role": entry.get("role"),
                            "specialty": entry.get("specialty"),
                            "provider": entry.get("provider"),
                            "model": entry.get("model"),
                            "emoji": entry.get("emoji"),
                            "mascot": entry.get("mascot"),
                        },
                    )
            if not participant_id:
                participant_id = self._insert_room_participant(room_id, entry, status="active")
            created_participant = self.get_participant(participant_id)
            if created_participant:
                created.append(created_participant)
        return created

    def room_exists(self, room_id: str) -> bool:
        return bool(self.conn.execute("SELECT 1 FROM rooms WHERE id = ?", (room_id,)).fetchone())

    def get_room_graph_id(self, room_id: str) -> str | None:
        row = self.conn.execute(
            "SELECT graph_id FROM rooms WHERE id = ?",
            (room_id,),
        ).fetchone()
        if not row:
            return None
        return row["graph_id"] or None

    def set_room_graph_id(self, room_id: str, graph_id: str | None):
        self.conn.execute(
            "UPDATE rooms SET graph_id = ?, updated_at = ? WHERE id = ?",
            (graph_id, utc_now(), room_id),
        )
        self.conn.commit()

    def get_profile_memory_graph_id(self, profile_id: str) -> str | None:
        row = self.conn.execute(
            "SELECT memory_graph_id FROM character_profiles WHERE id = ?",
            (profile_id,),
        ).fetchone()
        if not row:
            return None
        return row["memory_graph_id"] or None

    def set_profile_memory_graph_id(self, profile_id: str, graph_id: str | None):
        self.conn.execute(
            "UPDATE character_profiles SET memory_graph_id = ?, updated_at = ? WHERE id = ?",
            (graph_id, utc_now(), profile_id),
        )
        self.conn.commit()

    def get_profile(self, profile_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM character_profiles WHERE id = ?", (profile_id,)).fetchone()
        return self._profile_payload(row) if row else None

    def get_room_snapshot(self, room_id: str) -> dict | None:
        return self._aggregates.build_room_snapshot(room_id)

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
        return self._aggregates.build_session_snapshot(session_id, make_current=make_current)

    def set_current_session(self, session_id: str) -> dict | None:
        snapshot = self.get_session_snapshot(session_id, make_current=True)
        return snapshot

    def rename_session(self, session_id: str, title: str):
        self.update_session(session_id, {"title": title.strip()})

    def _delete_related_session_data(self, session_ids: list[str]):
        if not session_ids:
            return
        placeholders = ",".join("?" for _ in session_ids)
        cur = self.conn.cursor()
        cur.execute(
            f"""
            DELETE FROM fact_check_claims
            WHERE run_id IN (
                SELECT id
                FROM fact_check_runs
                WHERE session_id IN ({placeholders})
            )
            """,
            session_ids,
        )
        for table in (
            "fact_check_runs",
            "observer_reviews",
            "reports",
            "session_insights",
            "planned_events",
            "messages",
            "rounds",
            "room_events",
        ):
            cur.execute(f"DELETE FROM {table} WHERE session_id IN ({placeholders})", session_ids)

    def delete_session(self, session_id: str):
        session = self.conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not session:
            return
        room_id = session["room_id"]
        self._delete_related_session_data([session_id])
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
        return self._aggregates.export_session_markdown(session_id)

    def create_session_from_final(self, source_session_id: str) -> dict | None:
        source = self.conn.execute("SELECT * FROM sessions WHERE id = ?", (source_session_id,)).fetchone()
        if not source:
            return None
        room = self.conn.execute("SELECT * FROM rooms WHERE id = ?", (source["room_id"],)).fetchone()
        if not room:
            return None

        now = utc_now()
        session_id = make_id("session")
        source_title = source["title"] or source["topic"] or "Финал"
        next_title = f"Продолжение — {source_title}"[:120]
        next_chronicle = source["chronicle"] or source["topic"]
        self.conn.execute(
            """
            INSERT INTO sessions (
                id, room_id, title, topic, status, observer_mode, observer_provider, observer_model, chronicle, wrap_requested,
                final_requested, final_round_planned, extension_count, last_round_number,
                created_at, updated_at, started_at, ended_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                source["room_id"],
                next_title,
                source["topic"],
                "paused",
                source["observer_mode"],
                source["observer_provider"],
                source["observer_model"],
                next_chronicle,
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
        self.update_room_settings(source["room_id"], current_session_id=session_id, last_topic=source["topic"])
        return self.get_session(session_id)

    def create_room(self, name: str, observer_mode: str, observer_provider: str | None, observer_model: str | None, density_mode: str = "normal") -> str:
        room_id = make_id("room")
        now = utc_now()
        self.conn.execute(
            """
            INSERT INTO rooms (
                id, name, observer_mode, density_mode, observer_provider, observer_model,
                current_session_id, summary, last_topic, settings_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                room_id,
                name,
                observer_mode,
                density_mode,
                observer_provider,
                observer_model,
                None,
                "",
                "",
                dumps_json({"internet_mode": "auto"}),
                now,
                now,
            ),
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
        self._delete_related_session_data(session_ids)
        cur.execute("DELETE FROM sessions WHERE room_id = ?", (room_id,))
        cur.execute("DELETE FROM session_insights WHERE room_id = ?", (room_id,))
        cur.execute("DELETE FROM room_events WHERE room_id = ?", (room_id,))
        cur.execute("DELETE FROM planned_events WHERE room_id = ?", (room_id,))
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
            "memoryGraphId": "memory_graph_id",
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

    def update_room_settings(
        self,
        room_id: str,
        *,
        name: str | None = None,
        observer_mode: str | None = None,
        density_mode: str | None = None,
        observer_provider: str | None = None,
        observer_model: str | None = None,
        settings: dict | None = None,
        summary: str | None = None,
        last_topic: str | None = None,
        current_session_id: str | None = None,
    ):
        updates = []
        values: list[object] = []
        if name is not None:
            updates.append("name = ?")
            values.append(name)
        if observer_mode is not None:
            updates.append("observer_mode = ?")
            values.append(observer_mode)
        if density_mode is not None:
            updates.append("density_mode = ?")
            values.append(density_mode)
        if observer_provider is not None:
            updates.append("observer_provider = ?")
            values.append(observer_provider)
        if observer_model is not None:
            updates.append("observer_model = ?")
            values.append(observer_model)
        if settings is not None:
            updates.append("settings_json = ?")
            values.append(dumps_json(self._normalize_room_settings(settings)))
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
        room = self.conn.execute(
            "SELECT observer_provider, observer_model FROM rooms WHERE id = ?",
            (room_id,),
        ).fetchone()
        self.conn.execute(
            """
            INSERT INTO sessions (
                id, room_id, title, topic, status, observer_mode, observer_provider, observer_model, chronicle, wrap_requested,
                final_requested, final_round_planned, extension_count, last_round_number,
                created_at, updated_at, started_at, ended_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                room_id,
                "",
                topic,
                "running",
                observer_mode,
                room["observer_provider"] if room else None,
                room["observer_model"] if room else None,
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

    def create_session_with_seed(self, room_id: str, topic: str, observer_mode: str, chronicle: str, status: str = "paused", title: str = "") -> dict:
        now = utc_now()
        session_id = make_id("session")
        room = self.conn.execute(
            "SELECT observer_provider, observer_model FROM rooms WHERE id = ?",
            (room_id,),
        ).fetchone()
        self.conn.execute(
            """
            INSERT INTO sessions (
                id, room_id, title, topic, status, observer_mode, observer_provider, observer_model, chronicle, wrap_requested,
                final_requested, final_round_planned, extension_count, last_round_number,
                created_at, updated_at, started_at, ended_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                room_id,
                title,
                topic,
                status,
                observer_mode,
                room["observer_provider"] if room else None,
                room["observer_model"] if room else None,
                chronicle,
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
            "observerProvider": "observer_provider",
            "observerModel": "observer_model",
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
            WHERE session_id = ? AND round_number = ? AND author_type IN ('agent', 'user', 'system_event')
            ORDER BY created_at ASC
            """,
            (session_id, round_number),
        ).fetchall()
        return [loads_json(row["payload_json"], {}) for row in rows]

    def list_session_messages(self, session_id: str, limit: int | None = 60) -> list[dict]:
        if limit is None:
            rows = self.conn.execute(
                """
                SELECT payload_json
                FROM messages
                WHERE session_id = ?
                ORDER BY created_at ASC
                """,
                (session_id,),
            ).fetchall()
            return [loads_json(row["payload_json"], {}) for row in rows]

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

    def create_planned_event(
        self,
        room_id: str,
        target_round: int,
        description: str,
        session_id: str | None = None,
    ) -> dict:
        event_id = make_id("pevt")
        now = utc_now()
        self.conn.execute(
            """
            INSERT INTO planned_events (
                id, room_id, session_id, target_round, description, created_at, fired_at
            ) VALUES (?, ?, ?, ?, ?, ?, NULL)
            """,
            (event_id, room_id, session_id, int(target_round), description.strip(), now),
        )
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM planned_events WHERE id = ?", (event_id,)).fetchone()
        return self._planned_event_payload(row)

    def list_planned_events(
        self,
        room_id: str,
        session_id: str | None = None,
        *,
        include_fired: bool = True,
    ) -> list[dict]:
        params: list[object] = [room_id]
        where = "WHERE room_id = ?"
        if session_id:
            where += " AND (session_id = ? OR session_id IS NULL)"
            params.append(session_id)
        if not include_fired:
            where += " AND fired_at IS NULL"

        rows = self.conn.execute(
            f"""
            SELECT *
            FROM planned_events
            {where}
            ORDER BY
                CASE WHEN fired_at IS NULL THEN 0 ELSE 1 END,
                target_round ASC,
                created_at ASC
            """,
            params,
        ).fetchall()
        return [self._planned_event_payload(row) for row in rows]

    def get_planned_event(self, room_id: str, event_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM planned_events WHERE room_id = ? AND id = ?",
            (room_id, event_id),
        ).fetchone()
        return self._planned_event_payload(row) if row else None

    def update_planned_event(self, room_id: str, event_id: str, fields: dict) -> dict | None:
        allowed = {
            "targetRound": ("target_round", int),
            "target_round": ("target_round", int),
            "description": ("description", lambda value: str(value).strip()),
            "sessionId": ("session_id", lambda value: value),
            "session_id": ("session_id", lambda value: value),
        }
        updates = []
        values: list[object] = []
        for key, value in fields.items():
            if key not in allowed:
                continue
            column, caster = allowed[key]
            if column == "description" and not str(value).strip():
                continue
            updates.append(f"{column} = ?")
            values.append(caster(value))

        if not updates:
            return self.get_planned_event(room_id, event_id)

        values.extend([room_id, event_id])
        self.conn.execute(
            f"UPDATE planned_events SET {', '.join(updates)} WHERE room_id = ? AND id = ?",
            values,
        )
        self.conn.commit()
        return self.get_planned_event(room_id, event_id)

    def delete_planned_event(self, room_id: str, event_id: str) -> bool:
        cur = self.conn.execute(
            "DELETE FROM planned_events WHERE room_id = ? AND id = ?",
            (room_id, event_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def get_pending_events(self, room_id: str, session_id: str | None, target_round: int) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM planned_events
            WHERE room_id = ?
              AND target_round = ?
              AND fired_at IS NULL
              AND (session_id = ? OR session_id IS NULL)
            ORDER BY created_at ASC
            """,
            (room_id, int(target_round), session_id),
        ).fetchall()
        return [self._planned_event_payload(row) for row in rows]

    def mark_event_fired(self, event_id: str) -> dict | None:
        self.conn.execute(
            "UPDATE planned_events SET fired_at = ? WHERE id = ? AND fired_at IS NULL",
            (utc_now(), event_id),
        )
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM planned_events WHERE id = ?", (event_id,)).fetchone()
        return self._planned_event_payload(row) if row else None

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
                comments_json, achievements_json, stats_delta_json, progress_json, final_reason,
                missing_expert_hint, roster_advice_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                dumps_json(review.get("progress", {})),
                review.get("finalReason", ""),
                review.get("missingExpertHint", ""),
                dumps_json(review.get("rosterAdvice", {})),
                utc_now(),
            ),
        )
        self.conn.commit()

    def get_observer_reviews(self, session_id: str) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM observer_reviews
            WHERE session_id = ?
            ORDER BY round_number ASC
            """,
            (session_id,),
        ).fetchall()
        return [self._observer_review_payload(row) for row in rows]

    def save_session_insight(self, insight: dict) -> dict | None:
        return self._aggregates.save_session_insight(insight)

    def list_session_insights(
        self,
        *,
        room_id: str | None = None,
        observer_provider: str | None = None,
        observer_model: str | None = None,
        limit: int = 80,
    ) -> list[dict]:
        return self._aggregates.list_session_insights(
            room_id=room_id,
            observer_provider=observer_provider,
            observer_model=observer_model,
            limit=limit,
        )

    def get_fact_check_run(self, run_id: str, *, include_claims: bool = True) -> dict | None:
        return self._aggregates.get_fact_check_run(run_id, include_claims=include_claims)

    def get_latest_fact_check_run(self, session_id: str, *, include_claims: bool = True) -> dict | None:
        return self._aggregates.get_latest_fact_check_run(session_id, include_claims=include_claims)

    def find_reusable_fact_check_run(self, session_id: str, scope: str, target_round: int | None) -> dict | None:
        return self._aggregates.find_reusable_fact_check_run(session_id, scope, target_round)

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
        return self._aggregates.create_fact_check_run(
            room_id=room_id,
            session_id=session_id,
            scope=scope,
            target_round=target_round,
            internet_mode=internet_mode,
            provider=provider,
            model=model,
        )

    def update_fact_check_run(self, run_id: str, **fields) -> dict | None:
        return self._aggregates.update_fact_check_run(run_id, **fields)

    def replace_fact_check_claims(self, run_id: str, claims: list[dict]) -> list[dict]:
        return self._aggregates.replace_fact_check_claims(run_id, claims)

    def get_model_reliability(self, provider: str, model: str) -> dict | None:
        return self._aggregates.get_model_reliability(provider, model)

    def apply_model_reliability_rollup(self, claims: list[dict]) -> list[dict]:
        return self._aggregates.apply_model_reliability_rollup(claims)

    def save_report(self, session_id: str, room_id: str | None, markdown: str, sections: list[dict], provider: str | None, model: str | None) -> dict:
        return self._aggregates.save_report(session_id, room_id, markdown, sections, provider, model)

    def get_latest_report(self, session_id: str) -> dict | None:
        return self._aggregates.get_latest_report(session_id)

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

    def list_pinned_messages(self, session_id: str) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT m.payload_json
            FROM pinned_messages p
            JOIN messages m ON m.id = p.message_id
            WHERE p.session_id = ?
            ORDER BY p.created_at ASC
            """,
            (session_id,),
        ).fetchall()
        return [loads_json(row["payload_json"], {}) for row in rows]

    def toggle_message_pin(self, room_id: str, session_id: str, message_id: str) -> dict:
        existing = self.conn.execute(
            "SELECT id FROM pinned_messages WHERE session_id = ? AND message_id = ?",
            (session_id, message_id),
        ).fetchone()
        pinned = False
        if existing:
            self.conn.execute("DELETE FROM pinned_messages WHERE id = ?", (existing["id"],))
        else:
            self.conn.execute(
                """
                INSERT INTO pinned_messages (id, room_id, session_id, message_id, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (make_id("pin"), room_id, session_id, message_id, utc_now()),
            )
            pinned = True
        self.conn.commit()
        return {
            "pinned": pinned,
            "messageId": message_id,
            "pinnedMessages": self.list_pinned_messages(session_id),
        }
