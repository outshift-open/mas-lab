#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Commit-time conversation chunks — summaries retain children for audit/replay."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import uuid4

ChunkKind = Literal["messages", "summary"]


def _estimate_tokens(messages: list[dict[str, Any]]) -> int:
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += len(content)
        for call in msg.get("tool_calls") or []:
            fn = call.get("function") or {}
            total += len(str(fn.get("name", ""))) + len(str(fn.get("arguments", "")))
    return total // 4 + len(messages) * 4


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
    """Durable turn chunks with optional rolling summary (children kept for traceability)."""

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

    def messages_for_chunk_ids(self, chunk_ids: list[str]) -> list[dict[str, Any]]:
        msgs: list[dict[str, Any]] = []
        for chunk_id in chunk_ids:
            chunk = self.chunks.get(chunk_id)
            if isinstance(chunk, MessageChunk):
                msgs.extend(chunk.messages)
        return msgs

    def maybe_compact(
        self,
        *,
        summary_threshold: int,
        keep_message_chunks: int,
        summarize_fn: Callable[[list[dict[str, Any]]], str],
    ) -> bool:
        """Fold oldest message chunks into the rolling summary (incremental, children retained)."""
        if summary_threshold <= 0 or keep_message_chunks < 0:
            return False
        projected = self.project_messages()
        if _estimate_tokens(projected) <= summary_threshold:
            return False
        message_ids = [cid for cid in self.order if isinstance(self.chunks.get(cid), MessageChunk)]
        if len(message_ids) <= keep_message_chunks:
            return False

        to_fold = message_ids[: len(message_ids) - keep_message_chunks]
        if not to_fold:
            return False

        fold_messages = self.messages_for_chunk_ids(to_fold)
        if not fold_messages:
            return False

        if self.summary_chunk_id:
            prior = self.chunks[self.summary_chunk_id]
            if isinstance(prior, SummaryChunk):
                incremental_input = [
                    {"role": "system", "content": f"[Prior summary]\n{prior.text}"},
                    *fold_messages,
                ]
                new_text = summarize_fn(incremental_input)
                child_ids = list(prior.child_chunk_ids) + to_fold
                prior.text = new_text.strip()
                prior.child_chunk_ids = child_ids
            else:
                new_text = summarize_fn(fold_messages)
                self.summary_chunk_id = _new_chunk_id()
                self.chunks[self.summary_chunk_id] = SummaryChunk(
                    chunk_id=self.summary_chunk_id,
                    text=new_text.strip(),
                    child_chunk_ids=to_fold,
                )
        else:
            new_text = summarize_fn(fold_messages)
            self.summary_chunk_id = _new_chunk_id()
            self.chunks[self.summary_chunk_id] = SummaryChunk(
                chunk_id=self.summary_chunk_id,
                text=new_text.strip(),
                child_chunk_ids=to_fold,
            )

        self.order = [cid for cid in self.order if cid not in to_fold]
        return True

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
