#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Committed conversation chunks — append/project/serialize.

After each turn commit the store is replaced with the context manager's
bounded view (summary + recent turns). Folded prefix data is dropped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import uuid4

ChunkKind = Literal["messages", "summary"]


def _new_chunk_id() -> str:
    return f"chunk_{uuid4().hex[:12]}"


@dataclass
class MessageChunk:
    chunk_id: str
    messages: list[dict[str, Any]]
    kind: ChunkKind = "messages"

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "kind": self.kind,
            "messages": list(self.messages),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MessageChunk:
        return cls(
            chunk_id=str(data["chunk_id"]),
            messages=list(data.get("messages") or []),
        )


@dataclass
class SummaryChunk:
    chunk_id: str
    text: str
    child_chunk_ids: list[str]
    kind: ChunkKind = "summary"

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "kind": self.kind,
            "text": self.text,
            "child_chunk_ids": list(self.child_chunk_ids),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SummaryChunk:
        return cls(
            chunk_id=str(data["chunk_id"]),
            text=str(data.get("text") or ""),
            child_chunk_ids=[str(x) for x in data.get("child_chunk_ids") or []],
        )


Chunk = MessageChunk | SummaryChunk


@dataclass
class ConversationChunkStore:
    """Durable turn chunks. Bounded by the context manager at turn commit."""

    chunks: dict[str, Chunk] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)
    summary_chunk_id: str = ""

    def append_turn(self, messages: list[dict[str, Any]]) -> str:
        if not messages:
            return ""
        chunk = MessageChunk(chunk_id=_new_chunk_id(), messages=list(messages))
        self.chunks[chunk.chunk_id] = chunk
        self.order.append(chunk.chunk_id)
        return chunk.chunk_id

    def replace_with(self, turns: list[list[dict[str, Any]]]) -> None:
        """Reset the store to *turns* (each item is one user-turn message list)."""
        self.chunks.clear()
        self.order.clear()
        self.summary_chunk_id = ""
        for turn in turns:
            self.append_turn(turn)

    def project_messages(self) -> list[dict[str, Any]]:
        """Linear OpenAI-shaped list for LLM assembly (summary block + recent chunks)."""
        out: list[dict[str, Any]] = []
        if self.summary_chunk_id:
            summary = self.chunks.get(self.summary_chunk_id)
            if isinstance(summary, SummaryChunk) and summary.text.strip():
                out.append(
                    {
                        "role": "system",
                        "content": f"[Conversation summary — {len(summary.child_chunk_ids)} chunk(s)]\n{summary.text}",
                    }
                )
        for chunk_id in self.order:
            chunk = self.chunks.get(chunk_id)
            if isinstance(chunk, MessageChunk):
                out.extend(chunk.messages)
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary_chunk_id": self.summary_chunk_id,
            "order": list(self.order),
            "chunks": {cid: chunk.to_dict() for cid, chunk in self.chunks.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ConversationChunkStore:
        if not data:
            return cls()
        store = cls(
            summary_chunk_id=str(data.get("summary_chunk_id") or ""),
            order=[str(x) for x in data.get("order") or []],
        )
        for cid, raw in (data.get("chunks") or {}).items():
            kind = raw.get("kind", "messages")
            if kind == "summary":
                store.chunks[str(cid)] = SummaryChunk.from_dict(raw)
            else:
                store.chunks[str(cid)] = MessageChunk.from_dict(raw)
        return store
