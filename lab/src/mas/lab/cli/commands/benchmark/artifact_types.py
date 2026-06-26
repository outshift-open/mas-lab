#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""``mas-lab benchmark artifact-types`` command."""
from __future__ import annotations

import click


@click.command("artifact-types")
def artifact_types_cmd() -> None:
    """List all registered file artifact types with their abbreviation and description.

    The abbreviation shown in brackets (e.g. [CSV]) is what you pass to
    ``mas-lab benchmark show -r -v -t CSV`` to filter by type.
    """
    from mas.lab.artifacts import FILE_ARTIFACT_TYPES

    seen: set = set()
    rows: list = []
    for t in FILE_ARTIFACT_TYPES:
        if t.abbrev in seen:
            continue
        seen.add(t.abbrev)
        rows.append(t)
    width_abbrev = max(len(t.abbrev) for t in rows)
    width_label  = max(len(t.label)  for t in rows)
    header = f"  {'Abbrev':<{width_abbrev}}  {'Label':<{width_label}}  Description"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for t in rows:
        prod = f"  (produced by: {', '.join(t.produced_by)})" if t.produced_by else ""
        print(f"  {t.abbrev:<{width_abbrev}}  {t.label:<{width_label}}  {t.description}{prod}")
