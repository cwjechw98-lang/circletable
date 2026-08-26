from __future__ import annotations

import asyncio
import hashlib
import logging

from fastapi import APIRouter, HTTPException, Request

from http_api.deps import get_runtime
from knowledge.lightrag_adapter import (
    PROFILE_GRAPH_ROOT,
    create_profile_graph,
    delete_profile_graph,
    get_profile_knowledge_graph,
    get_profile_stored_texts,
    insert_text,
    read_profile_documents,
)


logger = logging.getLogger(__name__)

router = APIRouter()

# Переиндексация памяти: {profile_id: {"status": "running"|"done"|"error", ...}}
_REINDEX_STATE: dict[str, dict] = {}
_REINDEX_LOCK = asyncio.Lock()
REINDEX_MAX_DOCUMENTS = 80


def _dedupe_documents(documents: list[dict]) -> list[str]:
    """Свежие уникальные записи памяти: нормализованный хеш + сортировка по времени."""
    seen: set[str] = set()
    unique: list[tuple[float, str]] = []
    for doc in documents:
        normalized = " ".join((doc.get("content") or "").split())
        if len(normalized) < 40:
            continue
        fingerprint = hashlib.md5(normalized.lower().encode("utf-8")).hexdigest()
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        unique.append((float(doc.get("create_time") or 0), doc["content"]))
    unique.sort(key=lambda item: item[0], reverse=True)
    return [content for _, content in unique[:REINDEX_MAX_DOCUMENTS]]


async def _run_reindex(runtime, profile_id: str) -> dict:
    profile = runtime.repository.get_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Персонаж не найден")
    graph_id = profile.get("memoryGraphId")
    if not graph_id:
        raise HTTPException(status_code=400, detail="У персонажа ещё нет памяти для пересборки")

    documents = _dedupe_documents(read_profile_documents(graph_id))
    if not documents:
        raise HTTPException(status_code=400, detail="В графе нет записей для пересборки")

    async with _REINDEX_LOCK:
        existing = _REINDEX_STATE.get(profile_id)
        if existing and existing["status"] == "running":
            raise HTTPException(status_code=409, detail="Пересборка уже идёт")
        _REINDEX_STATE[profile_id] = {"status": "running", "total": len(documents), "processed": 0, "error": ""}

    async def _task():
        state = _REINDEX_STATE[profile_id]
        try:
            await asyncio.to_thread(delete_profile_graph, graph_id)
            fresh_graph_id = create_profile_graph(profile_id)
            runtime.repository.set_profile_memory_graph_id(profile_id, fresh_graph_id)
            # Порции по 10 документов: прогресс виден, память пишется инкрементально.
            batch_size = 10
            for start in range(0, len(documents), batch_size):
                batch = documents[start:start + batch_size]
                await asyncio.to_thread(insert_text, fresh_graph_id, batch, root_dir=PROFILE_GRAPH_ROOT)
                state["processed"] = min(start + batch_size, len(documents))
                await runtime.manager.broadcast({
                    "type": "memory_reindex_progress",
                    "profileId": profile_id,
                    "status": "running",
                    "processed": state["processed"],
                    "total": state["total"],
                })
            state["status"] = "done"
        except Exception as exc:  # noqa: BLE001 - состояние ошибки уходит в API и WS
            logger.warning("Переиндексация памяти %s не удалась: %s", profile_id, exc, exc_info=True)
            state["status"] = "error"
            state["error"] = str(exc)[:300]
        await runtime.manager.broadcast({
            "type": "memory_reindex_progress",
            "profileId": profile_id,
            "status": state["status"],
            "processed": state["processed"],
            "total": state["total"],
            "error": state["error"],
        })

    task = asyncio.create_task(_task())
    _REINDEX_STATE[profile_id]["task"] = task
    return {"started": True, "profileId": profile_id, "total": len(documents)}


async def wait_reindex_done(profile_id: str, timeout: float = 30.0) -> dict | None:
    """Хелпер для тестов: дождаться завершения фоновой пересборки."""
    state = _REINDEX_STATE.get(profile_id)
    if not state:
        return None
    task = state.get("task")
    if task:
        await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
    return state


@router.get("/api/lab/profiles")
async def list_lab_profiles(request: Request):
    runtime = get_runtime(request)
    return {"dossiers": runtime.repository.list_lab_dossiers()}


@router.get("/api/lab/profiles/{profile_id}")
async def get_lab_profile(request: Request, profile_id: str):
    runtime = get_runtime(request)
    dossier = runtime.repository.get_lab_dossier(profile_id)
    if not dossier:
        raise HTTPException(status_code=404, detail="Персонаж не найден")
    return dossier


@router.get("/api/lab/profiles/{profile_id}/memory")
async def get_profile_memory(request: Request, profile_id: str):
    runtime = get_runtime(request)
    profile = runtime.repository.get_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Персонаж не найден")
    graph_id = profile.get("memoryGraphId")
    base = {
        "profileId": profile_id,
        "graphId": graph_id,
        "hasMemory": bool(graph_id),
        "entities": [],
        "facts": [],
        "entries": [],
        "entityCount": 0,
        "factCount": 0,
    }
    if not graph_id:
        return base
    graph = get_profile_knowledge_graph(graph_id)
    entities = []
    for node in graph.get("nodes") or []:
        name = str(node.get("name") or "").strip()
        if not name:
            continue
        entities.append({
            "name": name,
            "type": ", ".join(node.get("labels") or []) or "Сущность",
            "summary": str(node.get("summary") or "").strip(),
        })
    entities.sort(key=lambda item: item["name"].lower())
    facts = []
    for edge in graph.get("edges") or []:
        fact = str(edge.get("fact") or "").strip()
        if not fact:
            continue
        facts.append({
            "relation": str(edge.get("name") or "").strip(),
            "fact": fact,
            "source": str(edge.get("source_node_name") or "").strip(),
            "target": str(edge.get("target_node_name") or "").strip(),
        })
    base.update({
        "entityCount": len(entities),
        "factCount": len(facts),
        "entities": entities[:80],
        "facts": facts[:60],
    })
    if not entities:
        # Граф без извлечённых сущностей — показываем сырые записи памяти.
        base["entries"] = get_profile_stored_texts(graph_id, limit=30)
    return base


@router.delete("/api/lab/profiles/{profile_id}/memory")
async def clear_profile_memory(request: Request, profile_id: str):
    runtime = get_runtime(request)
    profile = runtime.repository.get_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Персонаж не найден")
    graph_id = profile.get("memoryGraphId")
    cleared_graph = False
    if graph_id:
        delete_profile_graph(graph_id)
        cleared_graph = True
    runtime.repository.set_profile_memory_graph_id(profile_id, None)
    await runtime.manager.broadcast({
        "type": "participant_stats_updated",
        "inventory": runtime.repository.list_saved_profiles(),
    })
    return {"ok": True, "cleared": bool(graph_id), "clearedGraph": cleared_graph}


@router.post("/api/lab/profiles/{profile_id}/memory/reindex")
async def reindex_profile_memory(request: Request, profile_id: str):
    runtime = get_runtime(request)
    return await _run_reindex(runtime, profile_id)


@router.get("/api/lab/profiles/{profile_id}/memory/reindex-status")
async def reindex_profile_memory_status(request: Request, profile_id: str):
    state = _REINDEX_STATE.get(profile_id)
    if not state:
        return {"status": "idle"}
    return {
        "status": state["status"],
        "processed": state["processed"],
        "total": state["total"],
        "error": state["error"],
    }
