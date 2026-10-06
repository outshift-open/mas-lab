#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Guards against import-time coupling regressions.

mas/library/kg/__init__.py uses PEP 562 module ``__getattr__`` so that
importing a narrow piece of the native or OTel→KG path never eagerly
loads unrelated KG-tooling submodules.
"""

from __future__ import annotations

import subprocess
import sys

import pytest


def _run(code: str) -> str:
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def test_importing_otel_via_norm_does_not_load_kg_tooling_submodules():
    out = _run(
        "import sys; "
        "from mas.library.kg.observability.otel_via_norm import normalize_otel; "
        "unwanted = ["
        "    'mas.library.kg.artifact', 'mas.library.kg.core.compare',"
        "    'mas.library.kg.core.query', 'mas.library.kg.core.spec',"
        "    'mas.library.kg.core.annotate',"
        "]; "
        "print([m for m in unwanted if m in sys.modules])"
    )
    assert out == "[]"


def test_importing_graph_builder_does_not_load_kg_tooling_submodules():
    """graph_builder.py lives inside core/, alongside compare.py/query.py/
    spec.py -- core/__init__.py must not eagerly import those just because
    something imports graph_builder, its unrelated sibling."""
    out = _run(
        "import sys; "
        "from mas.library.kg.core.graph_builder import extract_graph, normalize_events; "
        "unwanted = ["
        "    'mas.library.kg.artifact', 'mas.library.kg.core.compare',"
        "    'mas.library.kg.core.query', 'mas.library.kg.core.spec',"
        "    'mas.library.kg.core.annotate',"
        "]; "
        "print([m for m in unwanted if m in sys.modules])"
    )
    assert out == "[]"


def test_otel_via_norm_path_does_not_load_retired_handlers():
    out = _run(
        "import sys; "
        "from mas.library.kg.observability.otel_via_norm import normalize_otel; "
        "retired = ["
        "    'mas.library.kg.observability.handlers',"
        "    'mas.library.kg.observability.otel',"
        "]; "
        "print([m for m in retired if m in sys.modules])"
    )
    assert out == "[]"


def test_lazy_top_level_attrs_still_resolve():
    from mas.library.kg import (
        FacetQuery,
        KGArtifact,
        KGCompareResult,
        KGIndex,
        KGView,
        annotate_kg_nodes,
        build_spec_nodes,
        compare_kg,
        merge_spec_into_kg,
        stream_artifacts,
    )

    assert KGArtifact.__name__ == "KGArtifact"
    assert callable(compare_kg)
    assert callable(annotate_kg_nodes)
    assert callable(build_spec_nodes)
    assert callable(merge_spec_into_kg)
    assert callable(stream_artifacts)
    for cls in (KGIndex, FacetQuery, KGView, KGCompareResult):
        assert isinstance(cls, type)


def test_unknown_top_level_attr_raises_attribute_error():
    import mas.library.kg as kg

    with pytest.raises(AttributeError):
        kg.ThisAttributeDoesNotExist
