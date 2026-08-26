from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from http_api.deps import get_runtime
from knowledge.lightrag_adapter import (
    delete_profile_graph,
    get_profile_knowledge_graph,
    get_profile_stored_texts,
)


router = APIRouter()


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
