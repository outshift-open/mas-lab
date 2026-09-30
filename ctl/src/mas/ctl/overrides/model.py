"""Structured representations for CLI override paths."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PathSegment:
    """One mapping key and optional list selector in an override path."""

    name: str
    selector: int | tuple[str, Any] | None = None
    wildcard: bool = False
    map_key: str | None = None


@dataclass(frozen=True)
class OverridePath:
    """A root-qualified path such as ``agent:spec.tools``."""

    root: str
    segments: tuple[PathSegment, ...]

    @property
    def text(self) -> str:
        parts: list[str] = []
        for segment in self.segments:
            value = segment.name
            if segment.wildcard:
                value += "[*]"
            elif segment.selector is not None:
                if isinstance(segment.selector, int):
                    value += f"[{segment.selector}]"
                else:
                    key, selector_value = segment.selector
                    value += f"[{key}={selector_value!r}]"
            parts.append(value)
        return f"{self.root}:{'.'.join(parts)}"


@dataclass(frozen=True)
class ParsedOverride:
    """Parsed CLI assignment with a YAML-decoded value."""

    path: OverridePath
    value: Any
    source: str
