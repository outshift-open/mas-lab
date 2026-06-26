#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Semantic memory store (FTS) — tutorial scope, release 2026.1.

TLA: MemoryMachine.tla (QUERYING / WRITING states).
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path


def _tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-zA-Z0-9_]+", text.lower()) if len(t) > 2]


@dataclass
class SemanticMemoryStore:
    """SQLite FTS5-backed semantic memory for agent-scoped retrieval."""

    db_path: Path
    _conn: sqlite3.Connection | None = field(default=None, init=False, repr=False)

    def _connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(key, content, tokenize='porter')"
            )
        return self._conn

    def index_document(self, key: str, content: str) -> None:
        conn = self._connection()
        conn.execute("DELETE FROM chunks WHERE key = ?", (key,))
        conn.execute("INSERT INTO chunks(key, content) VALUES (?, ?)", (key, content))
        conn.commit()

    def search(self, query: str, *, limit: int = 5) -> list[tuple[str, str]]:
        tokens = _tokenize(query)
        if not tokens:
            return []
        match = " OR ".join(tokens)
        conn = self._connection()
        rows = conn.execute(
            "SELECT key, content FROM chunks WHERE chunks MATCH ? LIMIT ?",
            (match, limit),
        ).fetchall()
        return [(str(k), str(c)) for k, c in rows]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None


def default_store_path(agent_id: str = "default") -> Path:
    base = Path.home() / ".mas" / "memory" / "semantic"
    return base / f"{agent_id}.sqlite"
