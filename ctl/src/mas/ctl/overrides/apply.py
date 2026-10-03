"""Apply CLI overrides by generating and merging canonical overlays."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from mas.ctl.overlay import merge_overlay
from mas.ctl.overrides.model import OverridePath, ParsedOverride, PathSegment
from mas.ctl.overrides.parser import parse_override
from mas.ctl.validate.schemas import load_schema

_ROOT_TARGETS = {
    "agent": "Agent",
    "mas": "MAS",
    "infra": "Infra",
    "flavour": "Flavour",
    "experiment": "Experiment",
    "workspace": "Workspace",
}


def _schema_object(node: dict[str, Any]) -> dict[str, Any]:
    for key in ("oneOf", "anyOf"):
        alternatives = node.get(key)
        if isinstance(alternatives, list):
            for alternative in alternatives:
                if isinstance(alternative, dict) and ("properties" in alternative or "items" in alternative):
                    return alternative
    parts = node.get("allOf")
    if isinstance(parts, list):
        properties: dict[str, Any] = {}
        for part in parts:
            if isinstance(part, dict):
                properties.update(_schema_object(part).get("properties") or {})
        if properties:
            return {**node, "properties": properties}
    return node


def _schema_declares(path: OverridePath, target_kind: str) -> bool:
    """True when every named segment of *path* is a declared schema property."""
    if target_kind == "Workspace":
        return True
    try:
        node: dict[str, Any] = load_schema(target_kind.lower())
    except Exception:
        return False
    for segment in path.segments:
        node = _schema_object(node)
        properties = node.get("properties")
        if isinstance(properties, dict) and segment.name in properties:
            node = properties[segment.name]
        elif isinstance(node.get("additionalProperties"), dict):
            node = node["additionalProperties"]
        else:
            return False
        if segment.selector is not None or segment.wildcard:
            node = _schema_object(node)
            if isinstance(node.get("items"), dict):
                node = node["items"]
    return True


def _assert_schema_cli_allowed(path: OverridePath, target_kind: str) -> None:
    if target_kind == "Workspace":
        return
    schema = _schema_object(load_schema(target_kind.lower()))
    node: dict[str, Any] = schema
    for segment in path.segments:
        node = _schema_object(node)
        properties = node.get("properties")
        if isinstance(properties, dict) and segment.name in properties:
            node = properties[segment.name]
        elif isinstance(node.get("additionalProperties"), dict):
            node = node["additionalProperties"]
        else:
            return
        cli_meta = node.get("x-cli") if isinstance(node, dict) else None
        if isinstance(cli_meta, dict) and cli_meta.get("allowed") is False:
            raise ValueError(f"CLI override is not allowed for path {path.text!r}")
        if segment.selector is not None or segment.wildcard:
            node = _schema_object(node)
            if isinstance(node.get("items"), dict):
                node = node["items"]
        if segment.map_key is not None:
            node = _schema_object(node)
            if isinstance(node.get("additionalProperties"), dict):
                node = node["additionalProperties"]


def _allows_missing_leaf(path: OverridePath, target_kind: str) -> bool:
    """Return whether the path's parent schema is an extensible map."""
    if target_kind == "Workspace":
        return True
    node: dict[str, Any] = _schema_object(load_schema(target_kind.lower()))
    for segment in path.segments[:-1]:
        node = _schema_object(node)
        properties = node.get("properties")
        if isinstance(properties, dict) and segment.name in properties:
            node = properties[segment.name]
        elif isinstance(node.get("additionalProperties"), dict):
            node = node["additionalProperties"]
        else:
            return False
        if segment.selector is not None or segment.wildcard:
            node = _schema_object(node)
            items = node.get("items")
            if not isinstance(items, dict):
                return False
            node = items
        if segment.map_key is not None:
            node = _schema_object(node)
            additional = node.get("additionalProperties")
            if not isinstance(additional, dict):
                return False
            node = additional
    node = _schema_object(node)
    return isinstance(node.get("additionalProperties"), dict)


def _nested_patch(names: list[str], value: Any) -> dict[str, Any]:
    patch = value
    for name in reversed(names):
        patch = {name: patch}
    return patch


def _nested_patch_segments(segments: list[PathSegment], value: Any) -> dict[str, Any]:
    patch = value
    for segment in reversed(segments):
        if segment.map_key is not None:
            patch = {segment.name: {segment.map_key: patch}}
        else:
            patch = {segment.name: patch}
    return patch


def _matches(item: Any, selector: int | tuple[str, Any]) -> bool:
    if isinstance(selector, int):
        return False
    key, expected = selector
    return isinstance(item, dict) and item.get(key) == expected


def _selected_indexes(items: list[Any], segment: PathSegment) -> list[int]:
    if segment.wildcard:
        return list(range(len(items)))
    if isinstance(segment.selector, int):
        if segment.selector >= len(items):
            raise ValueError(f"index {segment.selector} is out of range for {segment.name!r}")
        return [segment.selector]
    if segment.selector is None:
        return list(range(len(items)))
    indexes = [index for index, item in enumerate(items) if _matches(item, segment.selector)]
    if not indexes:
        key, expected = segment.selector
        raise ValueError(f"no list entry matches {key}={expected!r} for {segment.name!r}")
    return indexes


def _mutate_path(
    document: dict[str, Any],
    path: OverridePath,
    value: Any,
    *,
    allow_missing_leaf: bool = False,
) -> int | None:
    """Mutate selected paths and return the first selected list prefix index."""
    first_selector: int | None = None

    def visit(current: Any, position: int) -> None:
        nonlocal first_selector
        segment = path.segments[position]
        if (
            allow_missing_leaf
            and position == len(path.segments) - 1
            and isinstance(current, dict)
            and segment.name not in current
            and segment.selector is None
            and not segment.wildcard
            and segment.map_key is None
        ):
            current[segment.name] = deepcopy(value)
            return
        if not isinstance(current, dict) or segment.name not in current:
            raise ValueError(f"path segment {segment.name!r} does not exist")
        if segment.map_key is not None:
            mapping = current[segment.name]
            if not isinstance(mapping, dict):
                raise ValueError(f"{segment.name!r} is not a map")
            if position == len(path.segments) - 1:
                mapping[segment.map_key] = deepcopy(value)
                return
            if segment.map_key not in mapping:
                raise ValueError(f"map key {segment.map_key!r} does not exist")
            visit(mapping[segment.map_key], position + 1)
            return
        if segment.selector is None and not segment.wildcard:
            if position == len(path.segments) - 1:
                current[segment.name] = deepcopy(value)
                return
            visit(current[segment.name], position + 1)
            return

        items = current[segment.name]
        if not isinstance(items, list):
            raise ValueError(f"{segment.name!r} is not a list and cannot be selected")
        if first_selector is None:
            first_selector = position
        indexes = _selected_indexes(items, segment)
        if position == len(path.segments) - 1:
            for index in indexes:
                items[index] = deepcopy(value)
            return
        for index in indexes:
            visit(items[index], position + 1)

    visit(document, 0)
    return first_selector


def _list_at_path(document: dict[str, Any], names: list[str]) -> list[Any]:
    current: Any = document
    for name in names:
        if not isinstance(current, dict) or name not in current:
            raise ValueError(f"path segment {name!r} does not exist")
        current = current[name]
    if not isinstance(current, list):
        raise ValueError(f"selected path {'.'.join(names)!r} is not a list")
    return current


def _overlay_for_override(document: dict[str, Any], override: ParsedOverride, target_kind: str) -> dict[str, Any]:
    path = override.path
    patch_segments = list(path.segments)
    if patch_segments and patch_segments[0].name == "spec":
        patch_segments = patch_segments[1:]
    if not patch_segments:
        raise ValueError("override path must address a field below spec")
    allow_missing_leaf = _allows_missing_leaf(path, target_kind) or _schema_declares(path, target_kind)
    if not any(segment.selector is not None or segment.wildcard for segment in path.segments):
        _mutate_path(deepcopy(document), path, override.value, allow_missing_leaf=allow_missing_leaf)
    if any(segment.selector is not None or segment.wildcard for segment in path.segments):
        updated = deepcopy(document)
        first_selector = _mutate_path(updated, path, override.value, allow_missing_leaf=allow_missing_leaf)
        if first_selector is None:
            raise ValueError("internal error: selector path did not select a list")
        document_list_names = [segment.name for segment in path.segments[: first_selector + 1]]
        spec_offset = len(path.segments) - len(patch_segments)
        patch_selector = first_selector - spec_offset
        patch_list_names = [segment.name for segment in patch_segments[: patch_selector + 1]]
        replacement = _list_at_path(updated, document_list_names)
        patch = _nested_patch(patch_list_names, replacement)
    else:
        patch = _nested_patch_segments(patch_segments, override.value)
    return {
        "apiVersion": "mas/v1",
        "kind": "Overlay",
        "metadata": {"name": "cli-override"},
        "spec": {"target": {"kind": target_kind}, "patch": patch},
    }


def overrides_for_root(overrides: tuple[str, ...] | list[str], root: str) -> tuple[str, ...]:
    """The subset of *overrides* addressed to *root*, in argument order."""
    return tuple(source for source in overrides if parse_override(source).path.root == root)


def apply_cli_overrides(
    document: dict[str, Any], overrides: tuple[str, ...] | list[str], *, root: str
) -> dict[str, Any]:
    """Apply CLI assignments through the canonical overlay merge engine."""
    target_kind = _ROOT_TARGETS.get(root)
    if target_kind is None:
        raise ValueError(f"CLI overrides do not support root {root!r} yet")
    result = deepcopy(document)
    for source in overrides:
        parsed = parse_override(source)
        if parsed.path.root != root:
            raise ValueError(f"override root {parsed.path.root!r} does not match command root {root!r}: {source!r}")
        _assert_schema_cli_allowed(parsed.path, target_kind)
        overlay = _overlay_for_override(result, parsed, target_kind)
        result = merge_overlay(result, overlay)
    return result
