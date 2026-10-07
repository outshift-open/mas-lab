#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Standalone step: generic KG node annotation."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

from mas.library.kg.artifact import KGArtifact

logger = logging.getLogger(__name__)


def _as_artifact(inp: "KGArtifact | str | Path") -> KGArtifact:
    if isinstance(inp, KGArtifact):
        return inp
    return KGArtifact.from_file(inp)


def run_annotate(
    artifact: Union[KGArtifact, str, Path],
    value_fn: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]],
    *,
    node_type: str,
    edge_name: str,
    annotation_node_type: str = "Annotation",
    output_path: Optional[Union[str, Path]] = None,
    dry_run: bool = False,
) -> KGArtifact:
    """Annotate KG nodes and return the enriched KGArtifact.

    Args:
        artifact: Input KG. Accepts a KGArtifact, a path string, or a Path
            object. When a path is given and *output_path* is not set the
            input file is overwritten.
        value_fn: Called with each node where ``node["node_type"] == node_type``.
            Return a dict of annotation fields, or None to skip.
        node_type: Node type to annotate (e.g. ``"State"``).
        edge_name: Edge type to add (e.g. ``"hasEmbedding"``).
        annotation_node_type: node_type for the new annotation nodes.
        output_path: Write enriched KG here.  When *artifact* was a file path
            and this is None the input file is overwritten.  Ignored when
            *dry_run* is True.
        dry_run: Compute but do not write output.

    Returns:
        The enriched KGArtifact.
    """
    from mas.library.kg.core.annotate import annotate_kg_nodes

    input_was_path = not isinstance(artifact, KGArtifact)
    input_path_obj = Path(artifact).expanduser().resolve() if input_was_path else None

    kg = _as_artifact(artifact)
    doc = kg.to_doc()
    before_count = len(doc.get("nodes") or [])

    enriched_doc = annotate_kg_nodes(
        doc,
        node_type=node_type,
        edge_name=edge_name,
        value_fn=value_fn,
        annotation_node_type=annotation_node_type,
    )

    after_count = len(enriched_doc.get("nodes") or [])
    annotated_count = after_count - before_count

    enriched = KGArtifact.from_doc(enriched_doc)

    if not dry_run:
        # Determine where to write:
        #   1. explicit output_path
        #   2. overwrite input file when input was a path
        #   3. skip writing if input was already a KGArtifact and no output_path
        if output_path:
            out = Path(output_path).expanduser().resolve()
            out.parent.mkdir(parents=True, exist_ok=True)
            enriched.save(out)
            logger.info("annotate: added %d annotation nodes → %s", annotated_count, out)
        elif input_was_path and input_path_obj is not None:
            input_path_obj.parent.mkdir(parents=True, exist_ok=True)
            enriched.save(input_path_obj)
            logger.info("annotate: added %d annotation nodes → %s", annotated_count, input_path_obj)
        else:
            logger.info(
                "annotate: added %d annotation nodes (not saved — no output_path)", annotated_count
            )
    else:
        logger.info(
            "annotate: dry_run — %d annotation nodes computed, not written", annotated_count
        )

    return enriched
