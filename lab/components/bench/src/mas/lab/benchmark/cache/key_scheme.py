#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
Deterministic cache key computation for benchmark runs.

Key is a SHA256 hash of (manifest, overlays, dataset_item) to ensure
reproducible fingerprinting across all runs and evaluations.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class CacheKeyInfo:
    """Information used to compute a cache key."""
    
    manifest_path: str
    """Path to MAS agent manifest file."""
    
    manifest_hash: str
    """SHA256 of manifest content."""
    
    overlay_paths: List[str]
    """List of overlay file paths (in order)."""
    
    overlay_hashes: List[str]
    """SHA256 of each overlay content (in order)."""
    
    item_id: str
    """Dataset item ID."""
    
    @property
    def cache_key(self) -> str:
        """Compute deterministic cache key."""
        inputs = {
            "manifest_path": self.manifest_path,
            "manifest_hash": self.manifest_hash,
            "overlay_paths": self.overlay_paths,
            "overlay_hashes": self.overlay_hashes,
            "item_id": self.item_id,
        }
        json_str = json.dumps(inputs, sort_keys=True)
        return hashlib.sha256(json_str.encode()).hexdigest()


def compute_file_hash(path: Path) -> str:
    """Compute SHA256 of file content."""
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            sha.update(chunk)
    return sha.hexdigest()


def compute_cache_key(
    manifest_path: str,
    overlay_paths: Optional[List[str]] = None,
    item_id: str = "",
    base_dir: Optional[Path] = None,
) -> str:
    """
    Compute deterministic cache key for a run.
    
    Args:
        manifest_path: Path to MAS manifest (absolute or relative to base_dir)
        overlay_paths: List of overlay paths (absolute or relative to base_dir)
        item_id: Dataset item ID
        base_dir: Base directory for relative path resolution (default: cwd)
        
    Returns:
        SHA256 hex digest (cache key)
    """
    if base_dir is None:
        base_dir = Path.cwd()
    
    manifest_p = Path(manifest_path)
    if not manifest_p.is_absolute():
        manifest_p = base_dir / manifest_p
    
    manifest_hash = compute_file_hash(manifest_p)
    
    overlay_hashes = []
    if overlay_paths:
        for opath in overlay_paths:
            op = Path(opath)
            if not op.is_absolute():
                op = base_dir / op
            overlay_hashes.append(compute_file_hash(op))
    
    info = CacheKeyInfo(
        manifest_path=str(manifest_path),
        manifest_hash=manifest_hash,
        overlay_paths=overlay_paths or [],
        overlay_hashes=overlay_hashes,
        item_id=item_id,
    )
    
    return info.cache_key
