from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any

import httpx
import numpy as np
from lightrag import LightRAG, QueryParam
from lightrag.utils import EmbeddingFunc


logger = logging.getLogger(__name__)


_instances: dict[str, LightRAG] = {}
_lock = threading.Lock()

_loop: asyncio.AbstractEventLoop | None = None
_loop_thread: threading.Thread | None = None
_embedding_dim: int | None = None

OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_BASE") or "http://localhost:11434"
OLLAMA_OPENAI_BASE = os.getenv("OLLAMA_OPENAI_BASE_URL") or f"{OLLAMA_BASE}/v1"
LIGHTRAG_MODEL = os.getenv("LIGHTRAG_LLM_MODEL") or "gemma4:31b-cloud"
LIGHTRAG_EMBED_MODEL = os.getenv("LIGHTRAG_EMBEDDING_MODEL") or "nomic-embed-text:latest"
GRAPH_ROOT = Path(__file__).resolve().parents[1] / "data" / "graphs"
PROFILE_GRAPH_ROOT = Path(__file__).resolve().parents[1] / "data" / "profile_graphs"


def _resolve_root(root_dir: Path | None = None) -> Path:
    root = (root_dir or GRAPH_ROOT).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _instance_key(graph_id: str, root_dir: Path | None = None) -> str:
    root = _resolve_root(root_dir)
    return f"{root}::{graph_id}"


def _working_dir_for(graph_id: str, root_dir: Path | None = None) -> Path:
    root = _resolve_root(root_dir)
    return root / graph_id


def _get_event_loop() -> asyncio.AbstractEventLoop:
    global _loop, _loop_thread

    if _loop is not None and _loop.is_running():
        return _loop

    _loop = asyncio.new_event_loop()

    def _run_loop():
        asyncio.set_event_loop(_loop)
        _loop.run_forever()

    _loop_thread = threading.Thread(target=_run_loop, daemon=True, name="lightrag-loop")
    _loop_thread.start()
    return _loop


def run_async(coro):
    future = asyncio.run_coroutine_threadsafe(coro, _get_event_loop())
    return future.result(timeout=600)


async def _llm_model_func(
    prompt: str,
    system_prompt: str = "",
    history_messages: list[dict[str, str]] | None = None,
    keyword_extraction: bool = False,
    **_: Any,
) -> str:
    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(history_messages or [])
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": LIGHTRAG_MODEL,
        "messages": messages,
        "temperature": 0.0 if keyword_extraction else 0.3,
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(f"{OLLAMA_OPENAI_BASE}/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()
    return data.get("choices", [{}])[0].get("message", {}).get("content", "") or ""


async def _embed_one(text: str) -> list[float]:
    payload = {"model": LIGHTRAG_EMBED_MODEL, "prompt": text}
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(f"{OLLAMA_BASE}/api/embeddings", json=payload)
        response.raise_for_status()
        data = response.json()

    embedding = data.get("embedding")
    if isinstance(embedding, list):
        return embedding

    raise RuntimeError("Ollama embeddings endpoint returned no embedding vector")


async def _embedding_func(texts: list[str]) -> "np.ndarray":
    # lightrag-hku ожидает numpy-массив (обращается к .size): возврат списка
    # ломает пайплайн вставки на первом же чанке.
    vectors = await asyncio.gather(*(_embed_one(text) for text in texts))
    return np.array(vectors, dtype=float)


async def _get_embedding_dim() -> int:
    global _embedding_dim
    if _embedding_dim is None:
        _embedding_dim = len(await _embed_one("dimension probe"))
    return _embedding_dim


def get_or_create_instance(graph_id: str, *, root_dir: Path | None = None) -> LightRAG:
    cache_key = _instance_key(graph_id, root_dir)
    with _lock:
        existing = _instances.get(cache_key)
        if existing is not None:
            return existing

    working_dir = _working_dir_for(graph_id, root_dir=root_dir)
    working_dir.mkdir(parents=True, exist_ok=True)
    embedding_dim = run_async(_get_embedding_dim())

    rag = LightRAG(
        working_dir=str(working_dir),
        chunk_token_size=500,
        chunk_overlap_token_size=50,
        llm_model_name=LIGHTRAG_MODEL,
        llm_model_func=_llm_model_func,
        embedding_func=EmbeddingFunc(
            embedding_dim=embedding_dim,
            max_token_size=8192,
            model_name=LIGHTRAG_EMBED_MODEL,
            func=_embedding_func,
        ),
        enable_llm_cache=True,
    )
    run_async(rag.initialize_storages())

    with _lock:
        _instances[cache_key] = rag
    return rag


def create_graph(
    name: str = "CircleTable Graph",
    *,
    root_dir: Path | None = None,
    graph_id: str | None = None,
) -> str:
    if graph_id:
        resolved_graph_id = graph_id
    else:
        slug = name.strip().lower().replace(" ", "-") or "circletable-graph"
        resolved_graph_id = f"{slug}-{uuid.uuid4().hex[:10]}"
    get_or_create_instance(resolved_graph_id, root_dir=root_dir)
    return resolved_graph_id


def create_profile_graph(profile_id: str) -> str:
    return create_graph(
        name=f"profile-{profile_id}",
        root_dir=PROFILE_GRAPH_ROOT,
        graph_id=profile_id,
    )


def get_or_create_profile_instance(profile_id: str) -> LightRAG:
    return get_or_create_instance(profile_id, root_dir=PROFILE_GRAPH_ROOT)


def delete_graph(graph_id: str, *, root_dir: Path | None = None) -> None:
    cache_key = _instance_key(graph_id, root_dir)
    with _lock:
        _instances.pop(cache_key, None)

    working_dir = _working_dir_for(graph_id, root_dir=root_dir)
    if working_dir.exists():
        shutil.rmtree(working_dir, ignore_errors=True)


def delete_profile_graph(graph_id: str) -> None:
    delete_graph(graph_id, root_dir=PROFILE_GRAPH_ROOT)


def insert_text(graph_id: str, texts: list[str], *, root_dir: Path | None = None) -> None:
    payload = [text for text in texts if text and text.strip()]
    if not payload:
        return

    rag = get_or_create_instance(graph_id, root_dir=root_dir)
    run_async(rag.ainsert(payload))


def insert_profile_memory(graph_id: str, texts: list[str]) -> None:
    insert_text(graph_id, texts, root_dir=PROFILE_GRAPH_ROOT)


def query_graph(
    graph_id: str,
    query: str,
    mode: str = "hybrid",
    top_k: int = 30,
    *,
    root_dir: Path | None = None,
) -> str:
    rag = get_or_create_instance(graph_id, root_dir=root_dir)
    result = run_async(
        rag.aquery(
            query,
            param=QueryParam(
                mode=mode,
                top_k=top_k,
                response_type="Bullet Points",
            ),
        )
    )
    return result if isinstance(result, str) else str(result)


def query_profile_graph(graph_id: str, query: str, mode: str = "hybrid", top_k: int = 10) -> str:
    return query_graph(
        graph_id,
        query,
        mode=mode,
        top_k=top_k,
        root_dir=PROFILE_GRAPH_ROOT,
    )


def get_knowledge_graph(graph_id: str, *, root_dir: Path | None = None) -> dict[str, Any]:
    rag = get_or_create_instance(graph_id, root_dir=root_dir)
    try:
        # В lightrag-hku get_knowledge_graph — корутина: обязательно через run_async.
        graph = run_async(rag.get_knowledge_graph(node_label="*", max_depth=3, max_nodes=2000))
        if isinstance(graph, dict):
            return graph
    except Exception:
        pass

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    try:
        relation_graph = getattr(rag, "chunk_entity_relation_graph", None)
        internal_graph = getattr(relation_graph, "_graph", None)
        if internal_graph is not None:
            for node_id, data in internal_graph.nodes(data=True):
                nodes.append(
                    {
                        "uuid": str(node_id),
                        "name": str(node_id),
                        "labels": [data.get("entity_type", "Entity")],
                        "summary": data.get("description", ""),
                        "attributes": {
                            key: value
                            for key, value in data.items()
                            if key not in {"entity_type", "description"}
                        },
                    }
                )
            for source_id, target_id, data in internal_graph.edges(data=True):
                edges.append(
                    {
                        "uuid": f"{source_id}_{target_id}",
                        "name": data.get("relation", ""),
                        "fact": data.get("description", ""),
                        "source_node_uuid": str(source_id),
                        "target_node_uuid": str(target_id),
                        "source_node_name": str(source_id),
                        "target_node_name": str(target_id),
                        "attributes": {
                            key: value
                            for key, value in data.items()
                            if key not in {"relation", "description"}
                        },
                    }
                )
    except Exception:
        pass

    return {
        "graph_id": graph_id,
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


def get_stored_texts(graph_id: str, *, root_dir: Path | None = None, limit: int = 40) -> list[str]:
    """Сырые тексты, вставленные в граф (фолбэк, когда сущностей ещё нет).

    Читает kv-хранилища LightRAG с диска: сначала чанки, потом полные документы.
    """
    working_dir = _working_dir_for(graph_id, root_dir=root_dir)
    texts: list[str] = []
    for filename in ("kv_store_text_chunks.json", "kv_store_full_docs.json"):
        path = working_dir / filename
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        for value in data.values():
            content = value.get("content") if isinstance(value, dict) else value
            if isinstance(content, str) and content.strip():
                texts.append(content.strip())
            if len(texts) >= limit:
                break
        if texts:
            break
    return [text[:400] for text in texts[:limit]]


def get_profile_knowledge_graph(graph_id: str) -> dict[str, Any]:
    return get_knowledge_graph(graph_id, root_dir=PROFILE_GRAPH_ROOT)


def get_profile_stored_texts(graph_id: str, *, limit: int = 40) -> list[str]:
    return get_stored_texts(graph_id, root_dir=PROFILE_GRAPH_ROOT, limit=limit)
