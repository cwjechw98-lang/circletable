"""Экспорт траекторий обсуждений и генерация препринтов.

- Идея 5: JSONL-экспорт сессий (формат messages + ShareGPT) для fine-tuning и публикаций.
- Идея 1: автопрепринт «постановка → метод → результат» по завершённой сессии
  (LLM через настроенную модель памяти; при недоступности — детерминированный шаблон).
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from http_api.deps import get_runtime
from knowledge.lightrag_adapter import memory_llm_chat


router = APIRouter()


def _collect_session_trajectory(runtime, session_id: str) -> dict:
    session = runtime.repository.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    messages = runtime.repository.list_session_messages(session_id, limit=None)
    rounds = []
    for number in sorted({msg.get("round") or 0 for msg in messages}):
        if not number:
            continue
        rounds.append(number)
    return {
        "session_id": session_id,
        "room_id": session.get("roomId"),
        "topic": session.get("topic") or "",
        "status": session.get("status"),
        "observer": f"{session.get('observerProvider') or '?'}/{session.get('observerModel') or '?'}",
        "chronicle": session.get("chronicle") or "",
        "rounds": rounds,
        "messages": [
            {
                "round": msg.get("round"),
                "type": msg.get("type") or msg.get("message_type"),
                "author_type": msg.get("author_type"),
                "name": msg.get("agent_name") or msg.get("name"),
                "role": msg.get("role"),
                "specialty": msg.get("specialtyLabel") or msg.get("specialty"),
                "content": msg.get("content") or "",
            }
            for msg in messages
        ],
    }


def _to_sharegpt(trajectory: dict) -> dict:
    roster_note = f"Тема круглого стола: {trajectory['topic']}."
    conversations = [{"from": "system", "value": roster_note}]
    for msg in trajectory["messages"]:
        kind = msg.get("author_type")
        name = msg.get("name") or "Участник"
        content = msg.get("content") or ""
        if not content:
            continue
        if kind == "user":
            conversations.append({"from": "human", "value": content})
        elif kind == "system":
            continue
        else:
            role_label = msg.get("role") or "participant"
            prefix = f"[{name} ({role_label})] "
            if msg.get("type") == "agent_reaction":
                prefix = f"[{name} — реакция] "
            conversations.append({"from": "gpt", "value": prefix + content})
    return {"conversations": conversations}


@router.get("/api/export/session/{session_id}")
async def export_session(request: Request, session_id: str, format: str = "messages"):
    runtime = get_runtime(request)
    trajectory = _collect_session_trajectory(runtime, session_id)
    return _jsonl_response([_export_line(trajectory, format)], f"session_{session_id}_{format}.jsonl")


@router.get("/api/export/room/{room_id}")
async def export_room(request: Request, room_id: str, format: str = "messages"):
    runtime = get_runtime(request)
    sessions = runtime.repository.list_room_sessions(room_id)
    lines = []
    for item in sessions:
        try:
            trajectory = _collect_session_trajectory(runtime, item["id"])
        except HTTPException:
            continue
        lines.append(_export_line(trajectory, format))
    if not lines:
        raise HTTPException(status_code=404, detail="В комнате нет сессий для экспорта")
    return _jsonl_response(lines, f"room_{room_id}_{format}.jsonl")


def _export_line(trajectory: dict, format: str) -> str:
    if format == "sharegpt":
        payload = {"session_id": trajectory["session_id"], "topic": trajectory["topic"], **_to_sharegpt(trajectory)}
    elif format == "messages":
        payload = trajectory
    else:
        raise HTTPException(status_code=400, detail="format поддерживает 'messages' или 'sharegpt'")
    return json.dumps(payload, ensure_ascii=False)


def _jsonl_response(lines: list[str], filename: str) -> PlainTextResponse:
    body = "\n".join(lines) + "\n"
    return PlainTextResponse(
        body,
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


PREPRINT_PROMPT = """Ты научный редактор. По протоколу круглого стола ИИ-агентов собери препринт на русском языке.

Структура строго такая:
# {title}
## Постановка задачи
## Метод и ход обсуждения
## Результаты
## Открытые вопросы и следующие шаги

Пиши плотно и по делу, 400-700 слов. Опирайся только на протокол. Протокол:
"""


async def build_preprint(runtime, session_id: str) -> dict:
    trajectory = _collect_session_trajectory(runtime, session_id)
    protocol_lines = []
    for msg in trajectory["messages"]:
        if not (msg["content"] or "").strip() or msg["author_type"] == "system":
            continue
        who = msg.get("name") or msg.get("author_type")
        protocol_lines.append(f"[Р{msg['round']}] {who}: {msg['content'][:600]}")
    protocol = "\n".join(protocol_lines)[:14000]

    title = f"Препринт: {trajectory['topic'][:80]}"
    markdown = ""
    provider_used = None
    try:
        markdown = await memory_llm_chat(
            [{"role": "user", "content": PREPRINT_PROMPT.replace("{title}", title) + protocol}],
            temperature=0.2,
        )
        provider_used = "memory_llm"
    except Exception:
        markdown = ""

    if len(markdown.strip()) < 200:
        # Детерминированный шаблонный фолбэк без LLM.
        by_round: dict[int, list[str]] = {}
        for line in protocol_lines:
            head = line.split("]", 1)[0].lstrip("[Р")
            try:
                rnd = int(head)
            except ValueError:
                continue
            by_round.setdefault(rnd, []).append(line)
        method = "\n\n".join(
            f"**Раунд {rnd}.**\n" + "\n".join("- " + ln.split(": ", 1)[-1] for ln in lines[:6])
            for rnd, lines in sorted(by_round.items())
        )
        markdown = (
            f"# {title}\n\n## Постановка задачи\n{trajectory['topic']}\n\n"
            f"## Метод и ход обсуждения\nМультиагентное обсуждение за круглым столом "
            f"(наблюдатель: {trajectory['observer']}).\n\n{method}\n\n"
            f"## Результаты\nИтоговая хроника сессии:\n{(trajectory['chronicle'] or '—')[:3000]}\n\n"
            f"## Открытые вопросы и следующие шаги\n— (заполните вручную или перегенерируйте при доступной LLM)\n"
        )

    saved = runtime.repository.save_report(
        session_id=session_id,
        room_id=trajectory["room_id"],
        markdown=markdown,
        sections=[{"title": "kind", "value": "preprint"}],
        provider=provider_used,
        model=None,
    )
    return {"markdown": markdown, "reportId": saved["id"], "fallback": provider_used is None}


@router.post("/api/preprint/{session_id}")
async def generate_preprint(request: Request, session_id: str):
    runtime = get_runtime(request)
    result = await build_preprint(runtime, session_id)
    return result
