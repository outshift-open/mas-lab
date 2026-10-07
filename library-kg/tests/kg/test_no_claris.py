#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""library-kg source must not import or name a private ontology package."""

from __future__ import annotations

from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src" / "mas" / "library" / "kg"
_BANNED = ("claris_ontology", "claris-ontology", "claris-lib", "claris_lib")


def test_no_claris_ontology_in_library_kg_src() -> None:
    hits: list[str] = []
    for path in _SRC.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in {".py", ".md", ".yaml", ".yml", ".toml", ".json", ".ttl"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in _BANNED:
            if token in text:
                hits.append(f"{path.relative_to(_SRC.parent.parent.parent)}:{token}")
    assert hits == [], "private package names leaked into library-kg:\n" + "\n".join(hits)
