#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Shared infra-ref resolution for chat / tui session bootstrap.

Both ``mas-ctl chat`` and ``mas-ctl tui`` merge infra references from the MAS
manifest, the workspace, the user default, and CLI flags, then resolve them to
concrete bundles. This helper centralises that logic so the two commands cannot
drift apart.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def resolve_session_infra(
    agent_data: dict | None,
    workspace: Any,
    user: Any,
    *,
    infra_refs_cli: tuple[str, ...] | list[str],
    anchor: Path | str,
    with_interceptors: bool = False,
) -> Any:
    """Merge MAS/workspace/user/CLI infra refs and resolve them to bundles.

    When *with_interceptors* is true (the ``chat`` path) infra interceptors and
    the MAS config are also threaded through; the ``tui`` path omits them.
    """
    from mas.ctl.infra.resolve import resolve_infra_refs
    from mas.ctl.workspace.config import (
        collect_infra_interceptors,
        collect_mas_infra_refs,
        merge_infra_interceptors,
        merge_infra_refs,
    )

    merged = merge_infra_refs(
        mas_refs=collect_mas_infra_refs(agent_data or {}),
        workspace_refs=workspace.effective_infra_refs,
        user_refs=[user.default_infra] if user.default_infra else [],
        cli_refs=list(infra_refs_cli),
        workspace_found=workspace.found,
    )
    kwargs: dict[str, Any] = {"anchor": anchor, "workspace": workspace, "user": user}
    if with_interceptors:
        kwargs["interceptors"] = merge_infra_interceptors(
            mas_interceptors=collect_infra_interceptors(agent_data or {}),
            workspace_interceptors=workspace.infra_interceptors,
            cli_interceptors=[],
        )
        kwargs["mas_config"] = agent_data or {}
    return resolve_infra_refs(merged, **kwargs)
