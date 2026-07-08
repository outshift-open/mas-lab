#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""Output validation step for fail-fast detection of missing/malformed results.

Optional step that validates experiment outputs against a schema (required files,
columns, data types). Useful as a quality gate before publishing results.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from mas.lab.benchmark.reproducibility import OutputSchema

logger = logging.getLogger(__name__)


class ValidateOutputsStep:
    """Validates experiment outputs against optional schema.
    
    This is a lightweight step that can be inserted at the end of a pipeline
    to catch missing outputs or malformed files early.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize validator with optional config.
        
        Args:
            config: Dict with keys:
                - schema: OutputSchema dict with 'required_files' and 'required_columns'
                - warn_only: If True (default), log warnings; else raise ValueError
                - output_dir: Optional override for output directory
        """
        self.config = config or {}
        self.schema: Optional[OutputSchema] = None
        self.warn_only = self.config.get("warn_only", True)
        
        if schema_dict := self.config.get("schema"):
            self.schema = OutputSchema(**schema_dict)
    
    def execute(
        self,
        experiment_dir: Path,
        scenario: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Validate outputs in experiment directory.
        
        Args:
            experiment_dir: Root directory of experiment results.
            scenario: Current scenario (for logging context).
            **kwargs: Additional context (ignored).
        
        Returns:
            Dict with validation_passed (bool) and validation_errors (list).
        
        Raises:
            ValueError if warn_only=False and validation fails.
        """
        if not self.schema:
            logger.info("No output_schema configured; skipping validation")
            return {"validation_passed": True, "validation_errors": []}
        
        errors = []
        
        # Check required files
        for file_path in self.schema.required_files:
            full_path = experiment_dir / file_path
            if not full_path.exists():
                errors.append(f"Missing required file: {file_path}")
        
        # Check required columns
        for file_path, required_cols in self.schema.required_columns.items():
            full_path = experiment_dir / file_path
            if not full_path.exists():
                errors.append(f"Cannot validate columns: {file_path} does not exist")
                continue
            
            try:
                import pandas as pd
                df = pd.read_csv(full_path)
                missing_cols = [c for c in required_cols if c not in df.columns]
                if missing_cols:
                    errors.append(
                        f"Missing columns in {file_path}: {missing_cols}. "
                        f"Found: {list(df.columns)}"
                    )
            except Exception as e:
                errors.append(f"Error reading {file_path}: {e}")
        
        if errors:
            msg = "\n  ".join(errors)
            if self.warn_only:
                logger.warning(
                    "Output schema validation failed for scenario '%s':\n  %s",
                    scenario,
                    msg,
                )
                return {"validation_passed": False, "validation_errors": errors}
            else:
                raise ValueError(
                    f"Output schema validation failed for scenario '{scenario}':\n  {msg}"
                )
        
        logger.info("Output schema validation passed for scenario '%s'", scenario)
        return {"validation_passed": True, "validation_errors": []}
