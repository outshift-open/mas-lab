#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import logging

"""
logger = logging.getLogger(__name__)
Caching and fingerprinting for pipeline steps.

Determines when steps need to be rerun based on:
- Configuration changes (step config, pipeline config)
- Dependency output changes (upstream step outputs)
- Missing outputs (expected files don't exist)

This is the canonical implementation.
"""


import json
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional


class CacheManager:
    """Manages fingerprints and caching for pipeline steps."""
    
    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # In-memory cache of fingerprints
        self._fingerprints: Dict[str, str] = {}
        self._loaded = False
    
    def _load_fingerprints(self):
        """Load all fingerprints from cache directory."""
        if self._loaded:
            return
        
        for fp_file in self.cache_dir.glob("*.fingerprint"):
            step_name = fp_file.stem
            with open(fp_file, "r") as f:
                self._fingerprints[step_name] = f.read().strip()
        
        self._loaded = True
    
    def compute_fingerprint(
        self,
        step: "PipelineStep",
        dependency_outputs: Dict[str, "StepOutput"],
    ) -> str:
        """Compute fingerprint for a step.
        
        Fingerprint = hash(step config + dependency output hashes)
        
        Args:
            step: Pipeline step
            dependency_outputs: Outputs from dependency steps
            
        Returns:
            SHA256 hex digest
        """
        inputs = {
            "type": step.type,
            "config": step.config,
            "dependencies": {
                dep_name: self._hash_step_output(output)
                for dep_name, output in dependency_outputs.items()
            },
        }
        
        # Deterministic JSON serialization
        json_str = json.dumps(inputs, sort_keys=True, default=str)
        
        return hashlib.sha256(json_str.encode()).hexdigest()
    
    def _hash_step_output(self, output: "StepOutput") -> str:
        """Hash a step output.
        
        Uses:
        - Metadata (counts, timestamps excluded)
        - File hashes (for files that exist)
        - Data keys (not values, as they may be large DataFrames)
        """
        output_repr = {
            "metadata": {
                k: v for k, v in output.metadata.items()
                if k not in ["timestamp", "duration_ms"]  # Exclude timing
            },
            "data_keys": sorted(output.data.keys()),
            "files": [
                {
                    "path": str(f),
                    "hash": self._hash_file(f) if f.exists() else None
                }
                for f in output.files
            ],
        }
        
        json_str = json.dumps(output_repr, sort_keys=True)
        return hashlib.sha256(json_str.encode()).hexdigest()
    
    def _hash_file(self, path: Path) -> str:
        """Compute SHA256 of file."""
        sha256 = hashlib.sha256()
        
        with open(path, "rb") as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        
        return sha256.hexdigest()
    
    def get_cached_fingerprint(self, step_name: str) -> Optional[str]:
        """Get cached fingerprint for step."""
        self._load_fingerprints()
        return self._fingerprints.get(step_name)
    
    def save_fingerprint(self, step_name: str, fingerprint: str):
        """Save fingerprint for step."""
        fp_path = self.cache_dir / f"{step_name}.fingerprint"
        with open(fp_path, "w") as f:
            f.write(fingerprint)
        
        self._fingerprints[step_name] = fingerprint
    
    def should_rerun(
        self,
        step: "PipelineStep",
        dependency_outputs: Dict[str, "StepOutput"],
        output_dir: Path,
    ) -> bool:
        """Determine if step needs to be rerun.
        
        Returns True if:
        - No cached fingerprint (never run)
        - Fingerprint changed (config or dependency changed)
        - Expected outputs don't exist
        
        Args:
            step: Pipeline step
            dependency_outputs: Outputs from dependencies
            output_dir: Base output directory
            
        Returns:
            True if step should be rerun
        """
        # Check if outputs exist
        if not step.outputs_exist(output_dir):
            return True
        
        # Compute current fingerprint
        current_fp = self.compute_fingerprint(step, dependency_outputs)
        
        # Get cached fingerprint
        cached_fp = self.get_cached_fingerprint(step.name)
        
        if cached_fp is None:
            return True  # Never run before
        
        if current_fp != cached_fp:
            return True  # Config or dependencies changed
        
        return False  # Cache valid
    
    def invalidate(self, step_name: str):
        """Invalidate cache for a step."""
        fp_path = self.cache_dir / f"{step_name}.fingerprint"
        if fp_path.exists():
            fp_path.unlink()
        
        if step_name in self._fingerprints:
            del self._fingerprints[step_name]
    
    def clear(self):
        """Clear all cached fingerprints."""
        for fp_file in self.cache_dir.glob("*.fingerprint"):
            fp_file.unlink()
        
        self._fingerprints.clear()

    # ------------------------------------------------------------------
    # Intermediate artifact persistence
    # ------------------------------------------------------------------

    def save_output(self, step_name: str, output: Any) -> None:
        """Persist a step's in-memory output to disk.

        Handles DataFrames (saved as Parquet) and JSON-serialisable values.
        Non-serialisable values (e.g. complex objects) are silently skipped —
        the step will be re-run if loading fails later.
        """
        step_dir = self.cache_dir / step_name
        step_dir.mkdir(parents=True, exist_ok=True)

        data_serialized: Dict[str, Any] = {}
        for key, value in output.data.items():
            try:
                import pandas as pd  # optional; skip DataFrame handling if absent
                if isinstance(value, pd.DataFrame):
                    pq_path = step_dir / f"{key}.parquet"
                    value.to_parquet(pq_path, index=False)
                    data_serialized[key] = {"__type__": "dataframe", "path": str(pq_path)}
                    continue
            except ImportError:
                logger.debug('suppressed', exc_info=True)

            if isinstance(value, Path):
                data_serialized[key] = {"__type__": "path", "path": str(value)}
                continue

            try:
                json.dumps(value, default=str)
                data_serialized[key] = value
            except (TypeError, ValueError):
                pass  # skip — step will be re-run if this key is needed

        meta: Dict[str, Any] = {
            "metadata": {
                k: v for k, v in output.metadata.items()
                if k not in ("duration_ms",)
            },
            "files":    [str(f) for f in output.files],
            "warnings": output.warnings,
            "data":     data_serialized,
        }
        (step_dir / "output.json").write_text(
            json.dumps(meta, default=str), encoding="utf-8"
        )

    def load_output(self, step_name: str) -> Optional[Any]:
        """Load a previously persisted step output, or ``None`` if unavailable."""
        output_file = self.cache_dir / step_name / "output.json"
        if not output_file.exists():
            return None

        try:
            meta = json.loads(output_file.read_text(encoding="utf-8"))
        except Exception:
            return None

        data: Dict[str, Any] = {}
        for key, value in meta.get("data", {}).items():
            if isinstance(value, dict):
                if value.get("__type__") == "dataframe":
                    try:
                        import pandas as pd
                        data[key] = pd.read_parquet(value["path"])
                    except Exception:
                        return None  # parquet missing/corrupt — force re-run
                    continue
                if value.get("__type__") == "path":
                    data[key] = Path(value["path"])
                    continue
            data[key] = value

        # Import here to avoid circular import at module level
        from mas.lab.benchmark.pipeline import StepOutput
        return StepOutput(
            data=data,
            files=[Path(f) for f in meta.get("files", [])],
            metadata=meta.get("metadata", {}),
            warnings=meta.get("warnings", []),
        )