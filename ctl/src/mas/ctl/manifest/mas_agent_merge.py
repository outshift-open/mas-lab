#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Merge MAS workflow onto the entry agent manifest at run-mas bootstrap."""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mas.ctl.manifest.spec_bindings import parse_collaboration
from mas.runtime.boundary.delegation.llm_delegator import LlmDelegator
from mas.runtime.boundary.delegation.policy import delegation_targets
from mas.runtime.engine.llm_live import LiveLlmEngine
from mas.runtime.engine.tools import resolve_manifest_tool_refs

logger = logging.getLogger(__name__)

RunTurnFn = Callable[[str, str], str]


from mas.runtime.engine.leaf import leaf_engine


def enrich_entry_agent_for_delegation(
    agent_manifest: dict[str, Any],
    mas_config: dict[str, Any],
    *,
    manifest_dir: Path | None = None,
) -> dict[str, Any]:
    """Attach MAS ``workflow`` to the entry agent; resolve tool refs."""
    spec = agent_manifest.get("spec") or {}
    parse_collaboration(spec.get("collaboration"))
    out = copy.deepcopy(agent_manifest)
    mas_spec = mas_config.get("spec", mas_config) if isinstance(mas_config, dict) else {}
    wf = mas_spec.get("workflow")
    if isinstance(wf, dict):
        spec_out = out.setdefault("spec", {})
        if spec_out.get("workflow") and spec_out.get("workflow") != wf:
            logger.warning(
                "entry agent spec.workflow replaced by MAS workflow (MAS topology wins)"
            )
        # wf comes from mas_config (not agent_manifest); copy once to avoid shared refs.
        spec_out["workflow"] = copy.deepcopy(wf)
    if manifest_dir is not None:
        resolve_manifest_tool_refs(out, manifest_dir, inplace=True)
    return out


def wire_entry_engine_delegation(
    engine: Any,
    manifest: dict[str, Any],
    manifest_dir: Path,
    *,
    run_turn: RunTurnFn,
    entry_agent_id: str,
) -> None:
    """Set enriched manifest on the entry engine and bind ``LlmDelegator`` when peers exist.

    When peers exist, ``use_tool_loop`` is enabled on the leaf engine so the LLM can
    emit ``delegate_to_*`` tool calls. A manifest or instantiation that set
    ``use_tool_loop=False`` is overridden with a warning.
    """
    if engine is None:
        return
    leaf = leaf_engine(engine)
    leaf.manifest = manifest
    if isinstance(leaf, LiveLlmEngine):
        leaf.manifest_dir = manifest_dir
    peers = delegation_targets(manifest, agent_id=entry_agent_id)
    if not peers:
        leaf.delegation = None
        return
    leaf.delegation = LlmDelegator(run_turn=run_turn)
    if hasattr(leaf, "use_tool_loop"):
        if not leaf.use_tool_loop:
            logger.warning(
                "entry agent %r: enabling use_tool_loop for dynamic delegation (%d peers)",
                entry_agent_id,
                len(peers),
            )
            leaf.use_tool_loop = True


def reset_engine_delegation(engine: Any) -> None:
    """Clear delegate caches at the start of each user turn."""
    while engine is not None:
        delegation = getattr(engine, "delegation", None)
        reset_fn = getattr(delegation, "reset_session", None)
        if callable(reset_fn):
            reset_fn()
        engine = getattr(engine, "inner", None)
