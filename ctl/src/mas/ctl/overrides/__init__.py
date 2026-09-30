"""Schema-backed command-line overrides implemented as synthetic overlays."""

from mas.ctl.overrides.apply import apply_cli_overrides
from mas.ctl.overrides.model import OverridePath, ParsedOverride, PathSegment
from mas.ctl.overrides.parser import parse_override

__all__ = [
    "OverridePath",
    "ParsedOverride",
    "PathSegment",
    "apply_cli_overrides",
    "parse_override",
]
