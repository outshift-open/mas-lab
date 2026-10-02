#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Directory copy adapter — tests and hosts without git."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from mas.runtime.boundary.related_state import RelatedStateRef


class CopyDirRelatedState:
    """Stores a full copy under ``cache / fingerprint``. Not for large trees."""

    name = "copy_dir"

    def __init__(self, root: str | Path, cache: str | Path) -> None:
        self.root = Path(root)
        self.cache = Path(cache)
        self.cache.mkdir(parents=True, exist_ok=True)

    def capture(self, session_id: str) -> RelatedStateRef:
        digest = _hash_tree(self.root)
        dest = self.cache / digest
        if dest.exists():
            shutil.rmtree(dest)
        if self.root.exists():
            shutil.copytree(self.root, dest, dirs_exist_ok=True)
        else:
            dest.mkdir()
        return RelatedStateRef(
            plugin=self.name,
            fingerprint=digest,
            locator=str(dest),
            adapter="copy_dir",
        )

    def restore(self, session_id: str, ref: RelatedStateRef) -> None:
        src = Path(ref.locator) if ref.locator else self.cache / ref.fingerprint
        if not src.exists():
            return
        if self.root.exists():
            shutil.rmtree(self.root)
        shutil.copytree(src, self.root)


def _hash_tree(root: Path) -> str:
    h = hashlib.sha256()
    if not root.exists():
        return h.hexdigest()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            h.update(str(path.relative_to(root)).encode())
            h.update(path.read_bytes())
    return h.hexdigest()
