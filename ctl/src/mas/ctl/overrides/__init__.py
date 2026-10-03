"""Schema-backed command-line overrides implemented as synthetic overlays."""

from mas.ctl.overrides.apply import apply_cli_overrides, overrides_for_root
from mas.ctl.overrides.model import OverridePath, ParsedOverride, PathSegment
from mas.ctl.overrides.parser import parse_override
from mas.ctl.overrides.shortcuts import max_tokens_overrides

__all__ = [
    "OverridePath",
    "ParsedOverride",
    "PathSegment",
    "apply_cli_overrides",
    "max_tokens_overrides",
    "overrides_for_root",
    "parse_override",
]
