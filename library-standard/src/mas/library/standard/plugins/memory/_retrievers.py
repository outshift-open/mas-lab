# Copyright 2026 Cisco Systems, Inc. and its affiliates
#
# SPDX-License-Identifier: Apache-2.0

"""Retriever abstraction — orthogonal search axis.

Decouples HOW chunks are retrieved and scored from the storage backend.

Tagged implementations:
- ``FTSRetriever``    — SQLite FTS5 only (no embeddings)
- ``HybridRetriever`` — vector cosine + FTS5 (requires embed_fn)

Each retriever operates on a sqlite3.Connection that already has the
``chunks`` + ``chunks_fts`` + ``documents`` schema initialized.
The ``SemanticMemoryPlugin`` owns schema init; retrievers just query.
"""

from __future__ import annotations

import json
import logging
import math
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

# Default retriever tuning
DEFAULT_CHUNK_TOKENS = 400
DEFAULT_CHUNK_OVERLAP = 80
DEFAULT_MAX_RESULTS = 6
DEFAULT_MIN_SCORE = 0.35
DEFAULT_HYBRID_VECTOR_WEIGHT = 0.7
DEFAULT_HYBRID_TEXT_WEIGHT = 0.3
DEFAULT_MMR_LAMBDA = 0.7
DEFAULT_TEMPORAL_DECAY_HALF_LIFE_DAYS = 30


def _cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class Retriever(ABC):
    """Abstract memory retriever — search + rank chunks."""

    #: Version tag for experiment tracking / ablation.
    version: str = "abstract"

    @abstractmethod
    def search(
        self,
        conn: Any,  # sqlite3.Connection
        query: str,
        max_results: int = DEFAULT_MAX_RESULTS,
        min_score: float = DEFAULT_MIN_SCORE,
        sources: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Search chunks and return scored results."""
        ...


class FTSRetriever(Retriever):
    """SQLite FTS5 full-text retriever (no embeddings needed)."""

    version = "fts-v1"

    def search(
        self,
        conn: Any,
        query: str,
        max_results: int = DEFAULT_MAX_RESULTS,
        min_score: float = DEFAULT_MIN_SCORE,
        sources: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        fts_query = " OR ".join(f'"{w}"' for w in query.split() if w.strip())
        if not fts_query:
            fts_query = f'"{query}"'

        try:
            rows = conn.execute(
                "SELECT c.id, c.text, c.created_at, d.source, d.metadata, "
                "f.rank FROM chunks_fts f "
                "JOIN chunks c ON c.rowid = f.rowid "
                "JOIN documents d ON c.doc_id = d.id "
                "WHERE chunks_fts MATCH ? "
                "ORDER BY f.rank LIMIT ?",
                (fts_query, max_results * 3),
            ).fetchall()
        except Exception as exc:
            logger.debug("FTSRetriever: search failed (%s)", exc)
            return []

        if not rows:
            return []

        max_rank = max(abs(r[5]) for r in rows) or 1
        results = []
        for row in rows:
            chunk_id, text, created_at, source, meta_json, rank = row
            if sources and not any(source.startswith(s) for s in sources):
                continue
            score = abs(rank) / max_rank  # full weight (1.0) in FTS-only mode
            if score < min_score:
                continue
            results.append({
                "id": chunk_id,
                "source": source,
                "text": text,
                "score": round(score, 4),
                "metadata": json.loads(meta_json) if meta_json else {},
                "chunk": {"created_at": created_at},
            })

        results.sort(key=lambda x: -x["score"])
        return results[:max_results]


class HybridRetriever(Retriever):
    """Hybrid vector + FTS retriever (tagged: hybrid-v1).

    Combines cosine similarity (when embed_fn is provided) with SQLite FTS5:
    ``final_score = vector_weight * cosine_sim + text_weight * fts_score``

    Falls back to FTS-only when embed_fn is None.

    Parameters
    ----------
    embed_fn:
        Callable ``(texts: List[str]) -> List[List[float]]``.
        If None, uses FTS-only search.
    vector_weight / text_weight:
        Score blend weights. Default: 0.7 / 0.3.
    mmr_enabled:
        Enable MMR re-ranking for diversity. Default: False.
    mmr_lambda:
        MMR diversity parameter. Default: 0.7.
    temporal_decay_enabled:
        Weight older chunks lower. Default: False.
    temporal_decay_half_life_days:
        Half-life in days for decay. Default: 30.
    """

    version = "hybrid-v1"

    def __init__(
        self,
        embed_fn: Optional[Callable[..., List[List[float]]]] = None,
        vector_weight: float = DEFAULT_HYBRID_VECTOR_WEIGHT,
        text_weight: float = DEFAULT_HYBRID_TEXT_WEIGHT,
        mmr_enabled: bool = False,
        mmr_lambda: float = DEFAULT_MMR_LAMBDA,
        temporal_decay_enabled: bool = False,
        temporal_decay_half_life_days: int = DEFAULT_TEMPORAL_DECAY_HALF_LIFE_DAYS,
    ) -> None:
        self._embed_fn = embed_fn
        self._vector_weight = vector_weight
        self._text_weight = text_weight
        self._mmr_enabled = mmr_enabled
        self._mmr_lambda = mmr_lambda
        self._temporal_decay_enabled = temporal_decay_enabled
        self._temporal_decay_half_life_days = temporal_decay_half_life_days

    @property
    def embed_fn(self) -> Optional[Callable[..., List[List[float]]]]:
        return self._embed_fn

    @embed_fn.setter
    def embed_fn(self, fn: Optional[Callable[..., List[List[float]]]]) -> None:
        self._embed_fn = fn

    def search(
        self,
        conn: Any,
        query: str,
        max_results: int = DEFAULT_MAX_RESULTS,
        min_score: float = DEFAULT_MIN_SCORE,
        sources: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        import json as _json
        import time as _time

        # --- Vector search ---
        vector_scores: Dict[str, float] = {}
        if self._embed_fn is not None:
            try:
                query_emb = self._embed_fn([query[-2000:]])[0]
                rows = conn.execute(
                    "SELECT c.id, c.text, c.embedding, c.created_at, d.source "
                    "FROM chunks c JOIN documents d ON c.doc_id = d.id "
                    "WHERE c.embedding IS NOT NULL"
                ).fetchall()
                for row in rows:
                    chunk_id, text, emb_json, created_at, source = row
                    if sources and not any(source.startswith(s) for s in sources):
                        continue
                    emb = _json.loads(emb_json)
                    sim = _cosine_similarity(query_emb, emb)
                    if self._temporal_decay_enabled:
                        import math as _math
                        age_days = (_time.time() - created_at) / 86400
                        decay = _math.exp(
                            -_math.log(2) * age_days / max(1, self._temporal_decay_half_life_days)
                        )
                        sim *= decay
                    vector_scores[chunk_id] = sim
            except Exception as exc:
                logger.warning("HybridRetriever: vector search failed (%s)", exc)

        # --- FTS search ---
        fts_scores: Dict[str, float] = {}
        try:
            fts_query = " OR ".join(f'"{w}"' for w in query.split() if w.strip())
            if not fts_query:
                fts_query = f'"{query}"'
            fts_rows = conn.execute(
                "SELECT c.id, c.text, c.created_at, d.source, "
                "f.rank FROM chunks_fts f "
                "JOIN chunks c ON c.rowid = f.rowid "
                "JOIN documents d ON c.doc_id = d.id "
                "WHERE chunks_fts MATCH ? "
                "ORDER BY f.rank LIMIT ?",
                (fts_query, max_results * 3),
            ).fetchall()
            if fts_rows:
                max_rank = max(abs(r[4]) for r in fts_rows) or 1
                for row in fts_rows:
                    chunk_id, _text, created_at, source, rank = row
                    if sources and not any(source.startswith(s) for s in sources):
                        continue
                    fts_scores[chunk_id] = abs(rank) / max_rank
        except Exception as exc:
            logger.debug("HybridRetriever: FTS failed (%s) — vector only", exc)

        # --- Hybrid merge ---
        all_ids = set(vector_scores.keys()) | set(fts_scores.keys())
        effective_vw = self._vector_weight
        effective_tw = self._text_weight
        if not vector_scores and fts_scores:
            effective_tw, effective_vw = 1.0, 0.0
        elif vector_scores and not fts_scores:
            effective_vw, effective_tw = 1.0, 0.0

        scored = [
            (cid, vector_scores.get(cid, 0.0) * effective_vw + fts_scores.get(cid, 0.0) * effective_tw)
            for cid in all_ids
        ]
        scored.sort(key=lambda x: -x[1])

        # --- MMR re-ranking ---
        if self._mmr_enabled and self._embed_fn is not None and len(scored) > 1:
            scored = self._apply_mmr(scored, vector_scores, max_results)

        # --- Build results ---
        results: List[Dict[str, Any]] = []
        for chunk_id, score in scored[:max_results]:
            if score < min_score:
                continue
            row = conn.execute(
                "SELECT c.text, c.char_start, c.char_end, c.created_at, d.source, d.metadata "
                "FROM chunks c JOIN documents d ON c.doc_id = d.id "
                "WHERE c.id = ?",
                (chunk_id,),
            ).fetchone()
            if row:
                text, char_start, char_end, created_at, source, meta_json = row
                results.append({
                    "id": chunk_id,
                    "source": source,
                    "text": text,
                    "score": round(score, 4),
                    "metadata": _json.loads(meta_json) if meta_json else {},
                    "chunk": {"char_start": char_start, "char_end": char_end, "created_at": created_at},
                })
        return results

    def _apply_mmr(
        self,
        scored: List[Any],
        vector_scores: Dict[str, float],
        max_results: int,
    ) -> List[Any]:
        if not scored:
            return scored
        selected = [scored[0]]
        remaining = list(scored[1:])
        while remaining and len(selected) < max_results:
            best_idx, best_mmr = 0, float("-inf")
            for i, (cid, rel) in enumerate(remaining):
                max_sim = max(
                    (vector_scores.get(cid, 0) * vector_scores.get(s_id, 0))
                    for s_id, _ in selected
                ) if selected else 0
                mmr = self._mmr_lambda * rel - (1 - self._mmr_lambda) * max_sim
                if mmr > best_mmr:
                    best_mmr, best_idx = mmr, i
            selected.append(remaining.pop(best_idx))
        return selected
