"""Parser for root-qualified, jq-like CLI override assignments."""

from __future__ import annotations

import re
from typing import Any

import yaml
from mas.ctl.overrides.model import OverridePath, ParsedOverride, PathSegment

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


def _split_assignment(source: str) -> tuple[str, str]:
    quote: str | None = None
    bracket_depth = 0
    for index, character in enumerate(source):
        if quote:
            if character == quote and (index == 0 or source[index - 1] != "\\"):
                quote = None
            continue
        if character in "'\"":
            quote = character
        elif character == "[":
            bracket_depth += 1
        elif character == "]":
            bracket_depth -= 1
        elif character == "=" and bracket_depth == 0:
            return source[:index], source[index + 1 :]
    raise ValueError(f"override must be PATH=VALUE, got {source!r}")


def _parse_selector(
    raw: str, source: str
) -> tuple[int | tuple[str, Any] | None, bool, str | None]:
    value = raw.strip()
    if value == "*":
        return None, True, None
    if value.startswith(('"', "'")) and value.endswith(value[0]):
        map_key = yaml.safe_load(value)
        if not isinstance(map_key, str):
            raise ValueError(f"map selector must be a string in override {source!r}")
        return None, False, map_key
    if value.isdigit():
        return int(value), False, None
    if "=" not in value:
        raise ValueError(f"invalid list selector {raw!r} in override {source!r}")
    key, encoded = value.split("=", 1)
    key = key.strip()
    if not _IDENTIFIER.fullmatch(key):
        raise ValueError(f"invalid selector key {key!r} in override {source!r}")
    try:
        selector_value = yaml.safe_load(encoded)
    except yaml.YAMLError as error:
        raise ValueError(f"invalid selector value {encoded!r} in override {source!r}") from error
    return (key, selector_value), False, None


def _split_path_segments(path: str) -> list[str]:
    segments: list[str] = []
    start = 0
    bracket_depth = 0
    quote: str | None = None
    for index, character in enumerate(path):
        if quote:
            if character == quote and path[index - 1] != "\\":
                quote = None
            continue
        if character in "'\"" and bracket_depth:
            quote = character
        elif character == "[":
            bracket_depth += 1
        elif character == "]":
            bracket_depth -= 1
        elif character == "." and bracket_depth == 0:
            segments.append(path[start:index])
            start = index + 1
    segments.append(path[start:])
    return segments


def _parse_path(raw: str, source: str) -> OverridePath:
    if ":" not in raw:
        raise ValueError(f"override path must be ROOT:PATH, got {raw!r}")
    root, path = raw.split(":", 1)
    root = root.strip()
    if not _IDENTIFIER.fullmatch(root):
        raise ValueError(f"invalid override root {root!r}")
    segments: list[PathSegment] = []
    for raw_segment in _split_path_segments(path):
        if not raw_segment:
            raise ValueError(f"empty path segment in override {source!r}")
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_-]*)(?:\[(.*)\])?", raw_segment)
        if not match:
            raise ValueError(f"invalid path segment {raw_segment!r} in override {source!r}")
        name, selector_raw = match.groups()
        selector: int | tuple[str, Any] | None = None
        wildcard = False
        map_key: str | None = None
        if selector_raw is not None:
            selector, wildcard, map_key = _parse_selector(selector_raw, source)
        segments.append(
            PathSegment(name=name, selector=selector, wildcard=wildcard, map_key=map_key)
        )
    return OverridePath(root=root, segments=tuple(segments))


def parse_override(source: str) -> ParsedOverride:
    """Parse ``ROOT:path=value`` and decode the value as YAML."""
    raw_path, raw_value = _split_assignment(source)
    path = _parse_path(raw_path.strip(), source)
    try:
        value = "" if raw_value == "" else yaml.safe_load(raw_value)
    except yaml.YAMLError as error:
        raise ValueError(f"invalid YAML value {raw_value!r} in override {source!r}") from error
    return ParsedOverride(path=path, value=value, source=source)
