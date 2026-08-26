from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable

from .file_parser import parse_file
from .lightrag_adapter import create_graph, get_knowledge_graph, insert_text


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class GraphBuildStatus:
    room_id: str
    status: str = "idle"
    progress: int = 0
    graph_id: str | None = None
    file_count: int = 0
    chunk_count: int = 0
    node_count: int = 0
    edge_count: int = 0
    files: list[str] = field(default_factory=list)
    error: str | None = None
    updated_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict:
        return {
            "roomId": self.room_id,
            "status": self.status,
            "progress": self.progress,
            "graphId": self.graph_id,
            "hasKnowledge": bool(self.graph_id and self.status == "ready"),
            "fileCount": self.file_count,
            "chunkCount": self.chunk_count,
            "nodeCount": self.node_count,
            "edgeCount": self.edge_count,
            "files": list(self.files),
            "error": self.error,
            "updatedAt": self.updated_at,
        }


class GraphBuilder:
    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._statuses: dict[str, GraphBuildStatus] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    async def build_from_files(self, files: list[str], room_id: str) -> str:
        file_paths = [Path(file_path) for file_path in files]
        self._set_status(
            room_id,
            status="building",
            progress=5,
            file_count=len(file_paths),
            files=[path.name for path in file_paths],
            error=None,
            graph_id=None,
            chunk_count=0,
            node_count=0,
            edge_count=0,
        )

        parsed_documents: list[tuple[str, str]] = []
        for index, path in enumerate(file_paths, start=1):
            extracted = await asyncio.to_thread(parse_file, str(path))
            if extracted.strip():
                parsed_documents.append((path.name, extracted))
            progress = 5 + int((index / max(len(file_paths), 1)) * 20)
            self._set_status(room_id, progress=progress)

        if not parsed_documents:
            raise ValueError("Не удалось извлечь текст ни из одного файла")

        graph_id = await asyncio.to_thread(create_graph, f"room-{room_id}-knowledge")
        chunks = self._chunk_documents(parsed_documents)
        self._set_status(
            room_id,
            progress=30,
            graph_id=graph_id,
            chunk_count=len(chunks),
        )

        await self._insert_chunks(room_id, graph_id, chunks)

        graph = await asyncio.to_thread(get_knowledge_graph, graph_id)
        self._set_status(
            room_id,
            status="ready",
            progress=100,
            graph_id=graph_id,
            node_count=graph.get("node_count", len(graph.get("nodes", []))),
            edge_count=graph.get("edge_count", len(graph.get("edges", []))),
        )
        return graph_id

    async def build_from_text(self, text: str, room_id: str) -> str:
        payload = text.strip()
        if not payload:
            raise ValueError("Пустой текст для построения графа")

        self._set_status(
            room_id,
            status="building",
            progress=10,
            file_count=1,
            files=["inline-text"],
            error=None,
            graph_id=None,
            chunk_count=0,
            node_count=0,
            edge_count=0,
        )

        graph_id = await asyncio.to_thread(create_graph, f"room-{room_id}-knowledge")
        chunks = self._chunk_documents([("inline-text", payload)])
        self._set_status(room_id, progress=30, graph_id=graph_id, chunk_count=len(chunks))

        await self._insert_chunks(room_id, graph_id, chunks)

        graph = await asyncio.to_thread(get_knowledge_graph, graph_id)
        self._set_status(
            room_id,
            status="ready",
            progress=100,
            graph_id=graph_id,
            node_count=graph.get("node_count", len(graph.get("nodes", []))),
            edge_count=graph.get("edge_count", len(graph.get("edges", []))),
        )
        return graph_id

    async def start_build_from_files(
        self,
        files: list[str],
        room_id: str,
        *,
        on_success: Callable[[str], Awaitable[None] | None] | None = None,
        on_error: Callable[[Exception], Awaitable[None] | None] | None = None,
    ) -> dict:
        async with self._lock:
            existing = self._tasks.get(room_id)
            if existing and not existing.done():
                raise RuntimeError("Для этой комнаты уже строится граф знаний")

            async def runner():
                try:
                    graph_id = await self.build_from_files(files, room_id)
                    if on_success:
                        maybe_coro = on_success(graph_id)
                        if asyncio.iscoroutine(maybe_coro):
                            await maybe_coro
                except Exception as exc:
                    self._set_status(room_id, status="error", error=str(exc), progress=100)
                    if on_error:
                        maybe_coro = on_error(exc)
                        if asyncio.iscoroutine(maybe_coro):
                            await maybe_coro
                finally:
                    async with self._lock:
                        task = self._tasks.get(room_id)
                        if task is asyncio.current_task():
                            self._tasks.pop(room_id, None)

            self._tasks[room_id] = asyncio.create_task(runner(), name=f"knowledge-build-{room_id}")

        return self.get_status(room_id)

    async def start_build_from_text(
        self,
        text: str,
        room_id: str,
        *,
        on_success: Callable[[str], Awaitable[None] | None] | None = None,
        on_error: Callable[[Exception], Awaitable[None] | None] | None = None,
    ) -> dict:
        async with self._lock:
            existing = self._tasks.get(room_id)
            if existing and not existing.done():
                raise RuntimeError("Для этой комнаты уже строится граф знаний")

            async def runner():
                try:
                    graph_id = await self.build_from_text(text, room_id)
                    if on_success:
                        maybe_coro = on_success(graph_id)
                        if asyncio.iscoroutine(maybe_coro):
                            await maybe_coro
                except Exception as exc:
                    self._set_status(room_id, status="error", error=str(exc), progress=100)
                    if on_error:
                        maybe_coro = on_error(exc)
                        if asyncio.iscoroutine(maybe_coro):
                            await maybe_coro
                finally:
                    async with self._lock:
                        task = self._tasks.get(room_id)
                        if task is asyncio.current_task():
                            self._tasks.pop(room_id, None)

            self._tasks[room_id] = asyncio.create_task(runner(), name=f"knowledge-build-{room_id}")

        return self.get_status(room_id)

    def get_status(self, room_id: str) -> dict:
        status = self._statuses.get(room_id)
        if status is None:
            return GraphBuildStatus(room_id=room_id).to_dict()
        return status.to_dict()

    async def cancel(self, room_id: str) -> None:
        async with self._lock:
            task = self._tasks.pop(room_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._statuses.pop(room_id, None)

    async def _insert_chunks(self, room_id: str, graph_id: str, chunks: list[str]) -> None:
        total = max(len(chunks), 1)
        batch_size = 8
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start:start + batch_size]
            await asyncio.to_thread(insert_text, graph_id, batch)
            progress = 30 + int(((start + len(batch)) / total) * 60)
            self._set_status(room_id, progress=min(progress, 95))

    def _chunk_documents(self, documents: list[tuple[str, str]]) -> list[str]:
        chunks: list[str] = []
        for file_name, text in documents:
            cleaned = text.strip()
            if not cleaned:
                continue
            start = 0
            while start < len(cleaned):
                end = min(start + self.chunk_size, len(cleaned))
                chunk = cleaned[start:end].strip()
                if chunk:
                    chunks.append(f"[Source: {file_name}]\n{chunk}")
                if end >= len(cleaned):
                    break
                start = max(end - self.chunk_overlap, start + 1)
        return chunks

    def _set_status(self, room_id: str, **fields) -> None:
        status = self._statuses.get(room_id) or GraphBuildStatus(room_id=room_id)
        for key, value in fields.items():
            setattr(status, key, value)
        status.updated_at = _utc_now()
        self._statuses[room_id] = status
