#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""Integration helpers for embedding metadata capture in existing pipeline steps.

These utilities make it easy to add reproducibility metadata to any step
without rewriting the step itself.
"""

import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from mas.lab.benchmark.reproducibility import (
    ExperimentMetadata,
    MetadataWriter,
    get_framework_commit,
    load_mas_lab_version,
)

logger = logging.getLogger(__name__)


class MetadataCapture:
    """Helper to inject metadata capture into a step."""
    
    @staticmethod
    def wrap_step(
        original_step_execute: Callable,
        output_dir: Path,
        config: Dict[str, Any],
    ) -> Callable:
        """Wrap a step's execute() method to capture metadata.
        
        Usage:
            step = MyStep(config)
            step.execute = MetadataCapture.wrap_step(
                step.execute,
                output_dir=Path("results"),
                config=config,
            )
            result = step.execute(...)  # Metadata captured automatically
        
        Args:
            original_step_execute: The original execute method.
            output_dir: Directory where metadata.json will be written.
            config: Step config dict (should contain 'metadata' key if available).
        
        Returns:
            Wrapped function that calls original and writes metadata.
        """
        
        def wrapped(*args, **kwargs) -> Any:
            result = original_step_execute(*args, **kwargs)
            
            # Extract metadata from config if present
            metadata_config = config.get("metadata", {})
            if not metadata_config:
                logger.debug("No metadata config found; skipping metadata capture")
                return result
            
            # Build metadata object
            try:
                metadata = ExperimentMetadata(
                    mas_lab_version=load_mas_lab_version(),
                    framework_commit=get_framework_commit(),
                    model_name=metadata_config.get("model_name", "unknown"),
                    model_endpoint=metadata_config.get("model_endpoint", "unknown"),
                    recorded_at=(
                        metadata_config.get("recorded_at")
                        or __import__("datetime").datetime.now(
                            __import__("datetime").timezone.utc
                        ).isoformat()
                    ),
                    experiment_name=metadata_config.get("experiment_name", "unknown"),
                    dataset_version=metadata_config.get("dataset_version", "unknown"),
                    dataset_item_count=metadata_config.get("dataset_item_count", 0),
                    n_runs=metadata_config.get("n_runs", 0),
                    governance_overlays=metadata_config.get("governance_overlays", []),
                    plugin_versions=metadata_config.get("plugin_versions", {}),
                    notes=metadata_config.get("notes", ""),
                )
                
                # Write metadata
                writer = MetadataWriter()
                writer.write_experiment_metadata(output_dir, metadata)
                
            except Exception as e:
                logger.warning("Failed to capture metadata: %s", e)
            
            return result
        
        return wrapped


def should_capture_metadata(config: Dict[str, Any]) -> bool:
    """Check if config requests metadata capture.
    
    Args:
        config: Step or experiment config.
    
    Returns:
        True if 'metadata' key is present and non-empty.
    """
    return bool(config.get("metadata"))


def extract_metadata_config(experiment_config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract metadata config from experiment YAML.
    
    Args:
        experiment_config: experiment dict from parsed YAML.
    
    Returns:
        metadata dict if present, else None.
    """
    return experiment_config.get("metadata")


def merge_metadata_with_defaults(
    explicit_metadata: Dict[str, Any],
    defaults: Optional[Dict[str, Any]] = None,
) -> ExperimentMetadata:
    """Merge explicit metadata with auto-captured defaults.
    
    Args:
        explicit_metadata: User-provided metadata from experiment.yaml.
        defaults: Optional overrides (e.g., from CLI --override).
    
    Returns:
        Fully populated ExperimentMetadata.
    """
    all_metadata = {
        "mas_lab_version": load_mas_lab_version(),
        "framework_commit": get_framework_commit(),
        "recorded_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
    }
    all_metadata.update(explicit_metadata or {})
    if defaults:
        all_metadata.update(defaults)
    
    # Fill required fields with defaults if missing
    required_fields = [
        "model_name",
        "model_endpoint",
        "experiment_name",
        "dataset_version",
        "dataset_item_count",
        "n_runs",
    ]
    for field in required_fields:
        if field not in all_metadata:
            all_metadata[field] = "unknown"
    
    return ExperimentMetadata(**all_metadata)
