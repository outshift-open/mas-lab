#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Copy-on-write freeze for kernel product state and the run ledger.

A snapshot holds a reference; the live kernel pays for a clone only on
the next mutation. ``RuntimeKernel.transition`` mutates ``q`` in place
today, so the CoW seam is one chokepoint at the start of ``transition``
(and of restore): if the live object is frozen, clone it, then mutate
the clone. Snapshots keep the frozen original.

Working memory uses the same freeze bit on ``WorkingMemorySnapshot``:
in-memory snapshot cost is a pointer; the next ``sync_working_memory_out``
puts a new unfrozen object instead of appending into the frozen one.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from mas.runtime.kernel.state import QProduct, RunLedger


def cow_version(obj: Any) -> int:
    return int(getattr(obj, "_cow_version", 0) or 0)


def is_frozen(obj: Any) -> bool:
    return bool(getattr(obj, "_cow_frozen", False))


def freeze(obj: Any) -> Any:
    """Mark ``obj`` immutable for later writers. O(1). Returns ``obj``."""
    object.__setattr__(obj, "_cow_frozen", True)
    if not hasattr(obj, "_cow_version"):
        object.__setattr__(obj, "_cow_version", 0)
    return obj


def writable(obj: Any) -> Any:
    """Return ``obj`` if it is live, or a deep clone if a snapshot froze it.

    Kernel ``QProduct`` / ``RunLedger`` are small. The expensive structure
    is working memory, handled separately in the registry.
    """
    if obj is None or not is_frozen(obj):
        return obj
    clone = copy.deepcopy(obj)
    object.__setattr__(clone, "_cow_frozen", False)
    object.__setattr__(clone, "_cow_version", cow_version(obj) + 1)
    return clone


@dataclass(frozen=True)
class CowKernel:
    """In-memory kernel capture. Not a serialization format."""

    q: QProduct
    run: RunLedger
    pattern_plugin_id: str | None = None

    @property
    def version(self) -> int:
        return (cow_version(self.q) << 16) ^ cow_version(self.run)

    def materialize(self) -> dict[str, Any]:
        from mas.runtime.kernel.state_serialize import q_product_to_dict, run_to_dict

        return {
            "q": q_product_to_dict(self.q),
            "run": run_to_dict(self.run),
            "pattern_plugin_id": self.pattern_plugin_id,
        }


def capture_kernel(kernel: Any) -> CowKernel:
    """Copy q/run into a frozen snapshot. Does **not** freeze the live kernel.

    Governance snapshots run *during* ``transition``, while later envelope
    steps still mutate ``q`` in place. Freezing the live object would
    corrupt the snapshot (or raise). Kernel state is small; this copy is
    the right grain. Working memory uses freeze-in-place instead.
    """
    q = copy.deepcopy(kernel.q)
    run = copy.deepcopy(kernel.run)
    freeze(q)
    freeze(run)
    return CowKernel(
        q=q,
        run=run,
        pattern_plugin_id=getattr(getattr(kernel, "config", None), "pattern_plugin_id", None),
    )


def freeze_kernel(kernel: Any) -> CowKernel:
    """Freeze the *live* kernel. Only safe between transitions."""
    freeze(kernel.q)
    freeze(kernel.run)
    return CowKernel(
        q=kernel.q,
        run=kernel.run,
        pattern_plugin_id=getattr(getattr(kernel, "config", None), "pattern_plugin_id", None),
    )


def restore_kernel(kernel: Any, captured: CowKernel | dict[str, Any]) -> None:
    """Install captured state as a *writable* live copy (snapshots stay frozen)."""
    if isinstance(captured, CowKernel):
        kernel.q = writable(captured.q)
        kernel.run = writable(captured.run)
        return
    kernel.restore(captured)
