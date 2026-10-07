#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""KG core algorithms — events→graph construction, query, comparison, spec injection.

Every name below is loaded lazily on first access (see ``__getattr__``), so
importing one submodule directly -- e.g. ``mas.library.kg.core.graph_builder``
for events→KG normalization -- never pulls in the query/compare/spec
machinery unless something actually asks for it by name.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "KGIndex",
    "FacetQuery",
    "KGSource",
    "KGView",
    "KGCompareResult",
    "compare_kg",
    "build_spec_nodes",
    "merge_spec_into_kg",
]

_LAZY_ATTRS = {
    "KGCompareResult": "mas.library.kg.core.compare",
    "compare_kg": "mas.library.kg.core.compare",
    "FacetQuery": "mas.library.kg.core.query",
    "KGIndex": "mas.library.kg.core.query",
    "KGSource": "mas.library.kg.core.query",
    "KGView": "mas.library.kg.core.query",
    "build_spec_nodes": "mas.library.kg.core.spec",
    "merge_spec_into_kg": "mas.library.kg.core.spec",
}


def __getattr__(name: str) -> Any:
    module_name = _LAZY_ATTRS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module = importlib.import_module(module_name)
    return getattr(module, name)
