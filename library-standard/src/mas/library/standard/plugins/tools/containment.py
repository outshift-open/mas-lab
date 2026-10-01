#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Public path-containment helpers for manifest-relative refs.

Every call site that resolves a user-supplied path (local tools, subagent
templates, skill scripts) must go through these functions. There is no
second, looser resolver.
"""

from __future__ import annotations

from pathlib import Path

from mas.runtime.registry.provider_protocol import ManifestToolLoadError


def containment_roots(
    manifest_dir: Path,
    app_root: Path | None,
    *,
    workspace_root: Path | None = None,
    tools_dir: Path | None = None,
) -> tuple[Path, ...]:
    """Return the directories a resolved ref is allowed to land in."""
    seen = {manifest_dir.resolve(): None}
    if app_root is not None:
        app = app_root.resolve()
        if workspace_root is not None:
            stop = workspace_root.resolve()
            for parent in (app, *app.parents):
                seen[parent.resolve()] = None
                if parent == stop:
                    break
        else:
            seen[app] = None
    if tools_dir is not None:
        seen[tools_dir.resolve()] = None
    from mas.library_roots import discover_library_roots

    for lib_root in discover_library_roots(manifest_dir, app_root):
        seen[lib_root.resolve()] = None
    return tuple(seen)


def resolve_under_roots(
    ref_base: Path,
    ref: str,
    *,
    containment_roots: tuple[Path, ...],
) -> Path:
    """Resolve *ref* (relative, ``samples:…``, or ``pkg://``); must stay under a containment root."""
    if Path(ref).is_absolute():
        raise ManifestToolLoadError(f"absolute tool path not allowed: {ref!r}")

    from mas.runtime.package_refs import resolve_path_ref

    if ref.startswith("pkg://"):
        path = resolve_path_ref(ref, ref_base).resolve()
    elif ":" in ref and not ref.startswith(("/", "\\")):
        scheme, _, rel = ref.partition(":")
        if scheme and "/" not in scheme and "\\" not in scheme and rel:
            path = resolve_path_ref(ref, ref_base).resolve()
        else:
            path = (ref_base.resolve() / ref).resolve()
    else:
        path = (ref_base.resolve() / ref).resolve()

    for root in containment_roots:
        try:
            path.relative_to(root)
            return path
        except ValueError:
            continue
    raise ManifestToolLoadError(
        f"path escapes allowed roots: {ref!r} from {ref_base} (roots: {', '.join(str(r) for r in containment_roots)})"
    )
