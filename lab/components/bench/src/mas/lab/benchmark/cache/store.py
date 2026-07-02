#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
Unified cache store for agent execution and evaluation results.

Backend-agnostic interface with file-based implementation.
Future: pluggable DB backends.
"""

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
import gzip

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """A cached result for a single run."""
    
    cache_key: str
    """SHA256 cache key."""
    
    created_at: str
    """ISO 8601 timestamp."""
    
    manifest_hash: str
    """Manifest file hash."""
    
    overlay_hashes: list
    """Overlay file hashes."""
    
    item_id: str
    """Dataset item ID."""
    
    trace_path: str
    """Path to execution trace (events.jsonl or gzipped)."""
    
    evaluation_results: Dict[str, Any]
    """Evaluation results keyed by metric name."""
    
    metadata: Dict[str, Any]
    """Additional metadata (latency_ms, status, error, etc.)."""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict."""
        return asdict(self)
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "CacheEntry":
        """Create from dict."""
        return CacheEntry(**data)


class UnifiedCacheStore:
    """
    File-based unified cache store.
    
    Structure:
        cache_root/
          {cache_key}/
            entry.json          (metadata, paths, eval results)
            trace.jsonl         (or trace.jsonl.gz)
            artifacts/          (other files if needed)
    """
    
    def __init__(self, cache_root: Path):
        """
        Initialize cache store.
        
        Args:
            cache_root: Root directory for cache (e.g., $XDG_CACHE_HOME/mas)
        """
        self.cache_root = Path(cache_root)
        self.cache_root.mkdir(parents=True, exist_ok=True)
    
    def get_entry_dir(self, cache_key: str) -> Path:
        """Get directory for a cache entry."""
        return self.cache_root / cache_key
    
    def exists(self, cache_key: str) -> bool:
        """Check if cache entry exists."""
        entry_dir = self.get_entry_dir(cache_key)
        return (entry_dir / "entry.json").exists()
    
    def get(self, cache_key: str) -> Optional[CacheEntry]:
        """
        Retrieve cache entry.
        
        Args:
            cache_key: Cache key
            
        Returns:
            CacheEntry if exists, else None
        """
        entry_json = self.get_entry_dir(cache_key) / "entry.json"
        if not entry_json.exists():
            return None
        
        try:
            with open(entry_json, "r") as f:
                data = json.load(f)
            return CacheEntry.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to read cache entry {cache_key}: {e}")
            return None
    
    def put(
        self,
        cache_key: str,
        manifest_hash: str,
        overlay_hashes: list,
        item_id: str,
        trace_path: str,
        evaluation_results: Dict[str, Any],
        metadata: Dict[str, Any],
    ) -> CacheEntry:
        """
        Store cache entry.
        
        Args:
            cache_key: Cache key
            manifest_hash: Manifest file hash
            overlay_hashes: Overlay file hashes
            item_id: Dataset item ID
            trace_path: Path to execution trace
            evaluation_results: Dict of metric -> value
            metadata: Additional metadata
            
        Returns:
            Created CacheEntry
        """
        entry_dir = self.get_entry_dir(cache_key)
        entry_dir.mkdir(parents=True, exist_ok=True)
        
        entry = CacheEntry(
            cache_key=cache_key,
            created_at=datetime.utcnow().isoformat() + "Z",
            manifest_hash=manifest_hash,
            overlay_hashes=overlay_hashes,
            item_id=item_id,
            trace_path=str(trace_path),
            evaluation_results=evaluation_results,
            metadata=metadata,
        )
        
        entry_json = entry_dir / "entry.json"
        with open(entry_json, "w") as f:
            json.dump(entry.to_dict(), f, indent=2)
        
        logger.debug(f"Stored cache entry {cache_key} at {entry_dir}")
        
        return entry
    
    def delete(self, cache_key: str) -> bool:
        """
        Delete cache entry.
        
        Args:
            cache_key: Cache key
            
        Returns:
            True if deleted, False if not found
        """
        import shutil
        entry_dir = self.get_entry_dir(cache_key)
        if entry_dir.exists():
            shutil.rmtree(entry_dir)
            logger.info(f"Deleted cache entry {cache_key}")
            return True
        return False
    
    def list_keys(self) -> list:
        """List all cache keys."""
        return [d.name for d in self.cache_root.iterdir() if d.is_dir()]
    
    def invalidate_by_manifest(self, manifest_hash: str) -> int:
        """
        Invalidate all entries with a given manifest hash.
        
        Args:
            manifest_hash: Manifest file hash
            
        Returns:
            Number of entries deleted
        """
        count = 0
        for cache_key in self.list_keys():
            entry = self.get(cache_key)
            if entry and entry.manifest_hash == manifest_hash:
                self.delete(cache_key)
                count += 1
        logger.info(f"Invalidated {count} cache entries for manifest {manifest_hash}")
        return count
