#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Select which observability layers to export as OTel spans.

Default compatibility uses the three base tree layers (structure, execution,
semantic).  Provenance (trajectory) and governance are opt-in.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mas.library.standard.lib.observability.native.envelope import _KIND_ENVELOPE

# Native envelope ``block`` → export layer name.
_BLOCK_TO_LAYER: dict[str, str] = {
    "structural": "structure",
    "execution": "execution",
    "context": "semantic",
    "trajectory": "provenance",
    "governance": "governance",
}


@dataclass(frozen=True)
class ExportLayers:
    """Layer toggles for OTel export (MasOtelConverter and plugins)."""

    structure: bool = True
    execution: bool = True
    semantic: bool = True
    provenance: bool = False
    governance: bool = False

    def enabled(self, layer: str) -> bool:
        return bool(getattr(self, layer, True))

    def to_dict(self) -> dict[str, bool]:
        return {
            "structure": self.structure,
            "execution": self.execution,
            "semantic": self.semantic,
            "provenance": self.provenance,
            "governance": self.governance,
        }


def parse_export_layers(cfg: dict[str, Any] | None) -> ExportLayers:
    """Parse layer flags from plugin/step manifest config."""
    cfg = cfg or {}
    layers_cfg = cfg.get("export_layers")
    if isinstance(layers_cfg, dict):
        cfg = {**cfg, **layers_cfg}
    return ExportLayers(
        structure=_layer_flag(cfg, "structure", "structural", default=True),
        execution=_layer_flag(cfg, "execution", default=True),
        semantic=_layer_flag(cfg, "semantic", "context", default=True),
        provenance=_layer_flag(cfg, "provenance", "trajectory", default=False),
        governance=_layer_flag(cfg, "governance", default=False),
    )


def _layer_flag(cfg: dict[str, Any], primary: str, alias: str | None = None, *, default: bool) -> bool:
    if primary in cfg:
        return bool(cfg[primary])
    if alias is not None and alias in cfg:
        return bool(cfg[alias])
    return default


def layer_for_kind(kind: str) -> str | None:
    """Map a native event kind to an export layer name."""
    entry = _KIND_ENVELOPE.get(kind)
    if entry is None:
        return None
    return _BLOCK_TO_LAYER.get(entry[0], entry[0])


def should_export_event(event: dict[str, Any], layers: ExportLayers) -> bool:
    """Return whether *event* should be converted to OTel spans."""
    kind = str(event.get("kind") or "")
    layer = str(event.get("layer") or "") or layer_for_kind(kind)
    if not layer:
        return True
    return layers.enabled(layer)


__all__ = [
    "ExportLayers",
    "layer_for_kind",
    "parse_export_layers",
    "should_export_event",
]
