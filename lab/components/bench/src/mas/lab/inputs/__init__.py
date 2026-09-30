#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Run Input Envelope — per-run inputs for bench / ctl (envelope-only)."""

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from mas.runtime.spec.source import load_yaml_file

_REF_KEYS = frozenset({"ref", "id"})


def _is_ref_object(value: Any) -> bool:
    return isinstance(value, dict) and bool(value) and set(value.keys()) <= _REF_KEYS


def _resolve_ref_object(value: dict, base_path: Optional[Path]) -> Any:
    if "id" in value and "ref" not in value:
        raise ValueError(
            f"catalog id refs are not resolved yet: {value.get('id')!r}"
        )
    ref = value.get("ref")
    if not isinstance(ref, str):
        raise TypeError("ref object needs ref: path")
    return _load_ref(ref, base_path)


def _resolve_file_slot(value: Any, base_path: Optional[Path]) -> Any:
    """tool_fixtures / memory_seeds: ``{ref:}`` or bare path shorthand."""
    if value is None:
        return None
    if isinstance(value, str):
        return _load_ref(value, base_path)
    if _is_ref_object(value):
        return _resolve_ref_object(value, base_path)
    return value


def _resolve_text_slot(value: Any, base_path: Optional[Path]) -> Any:
    """user / hitl / expectations: a string is inline text; only ``{ref:}`` loads a file."""
    if value is None:
        return None
    if _is_ref_object(value):
        return _resolve_ref_object(value, base_path)
    return value


def _split_ref(text: str) -> tuple[str, str | None]:
    path, sep, frag = str(text).partition("#")
    if not sep:
        return str(text), None
    return path, (frag.strip() or None)


def _pick_fragment(data: Any, frag: str) -> Any:
    """Select ``#id`` from a list of ``{id: ...}`` or a mapping keyed by id.

    Tries each candidate nested-list key in turn: a miss on one candidate
    (``ValueError``, the not-found signal below) falls through to the next
    candidate instead of raising immediately, so the multi-key fallback
    actually works.
    """
    if isinstance(data, dict):
        if frag in data:
            return data[frag]
        if str(data.get("id")) == frag:
            return data
        for key in ("items", "fixtures", "entries", "messages", "turns", "user"):
            nested = data.get(key)
            if isinstance(nested, list):
                try:
                    return _pick_fragment(nested, frag)
                except ValueError:
                    continue
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and str(item.get("id")) == frag:
                return item
    raise ValueError(f"fixture id {frag!r} not found")


def _load_ref(ref: str, base_path: Optional[Path]) -> Any:
    path_text, frag = _split_ref(ref)
    path = Path(path_text)
    if base_path and not path.is_absolute():
        path = base_path / path
    if not path.is_file() and ":" in path_text:
        try:
            from mas.runtime.package_refs import resolve_path_ref

            resolved = resolve_path_ref(path_text, base_path or Path("."))
            if resolved.is_file():
                path = resolved
        except Exception:
            pass
    if path.suffix.lower() in {".txt", ".md"}:
        if frag:
            raise ValueError(f"text ref {ref!r} does not support #fragments")
        return path.read_text(encoding="utf-8").rstrip("\n")
    data = load_yaml_file(path)
    if frag:
        data = _pick_fragment(data, frag)
    return data


def _is_role_message_shape(value: Any) -> bool:
    """True when ``user`` is OpenAI-style ``{role, content}`` instead of a string."""
    if isinstance(value, dict) and "role" in value and "content" in value:
        return True
    if isinstance(value, list):
        return any(
            isinstance(item, dict) and "role" in item and "content" in item
            for item in value
        )
    return False


_LEGACY_PROMPT_KEYS = ("prompt", "query", "question", "text", "input")
_LEGACY_TOP_KEYS = (
    "turns",
    "memory_seeds",
    "session_id",
    "expected_answer",
    "ground_truth",
    "correct_action",
)


def _is_legacy_item(item: Dict[str, Any]) -> bool:
    """True when the item is not already a Run Input Envelope."""
    existing = item.get("inputs")
    envelope = isinstance(existing, dict) and existing.get("user") is not None
    if any(item.get(key) is not None for key in _LEGACY_PROMPT_KEYS):
        return True
    if isinstance(item.get("user"), (str, list)) and not envelope:
        return True
    if any(item.get(key) is not None for key in _LEGACY_TOP_KEYS) and not envelope:
        return True
    return False


def _resolve_fixture(
    fixture_val: Any,
    base_path: Optional[Path] = None,
) -> Any:
    """Load tool fixtures from the dataset item.

    Mapping (path / ``{ref:}`` / ``by_tool``) vs opaque payload.
    """
    if fixture_val is None:
        return None
    if isinstance(fixture_val, str) or _is_ref_object(fixture_val):
        return _resolve_file_slot(fixture_val, base_path)
    if isinstance(fixture_val, list):
        by_tool: Dict[str, Any] = {}
        for entry in fixture_val:
            if not isinstance(entry, dict):
                raise TypeError("tool_fixtures list entries must be mappings")
            ref = entry.get("ref") or entry.get("data")
            if not isinstance(ref, str):
                raise TypeError("tool_fixtures list entry needs ref: path")
            payload = _load_ref(ref, base_path)
            names = entry.get("tools")
            if isinstance(names, list) and names:
                tools = [str(n) for n in names]
            else:
                tools = [str(entry.get("tool") or "*")]
            for name in tools:
                by_tool[name] = payload
        return {"by_tool": by_tool}
    if isinstance(fixture_val, dict):
        mapping = fixture_val.get("by_tool") if "by_tool" in fixture_val else None
        if mapping is not None:
            resolved: Dict[str, Any] = {}
            for tool, spec in mapping.items():
                if isinstance(spec, str) or _is_ref_object(spec):
                    resolved[str(tool)] = _resolve_file_slot(spec, base_path)
                elif isinstance(spec, dict) and isinstance(
                    spec.get("ref") or spec.get("data"), str
                ):
                    resolved[str(tool)] = _load_ref(
                        str(spec.get("ref") or spec["data"]), base_path
                    )
                else:
                    resolved[str(tool)] = spec
            return {"by_tool": resolved}
        if isinstance(fixture_val.get("incident_fixture"), str):
            from mas.lab.deprecations import warn_deprecated

            warn_deprecated(
                "dataset.incident_fixture",
                where=str(base_path) if base_path is not None else "dataset item",
            )
            return _load_ref(str(fixture_val["incident_fixture"]), base_path)
        return fixture_val
    raise TypeError("tool_fixtures must be a path, mapping, list of bindings, or object")


def _as_messages(value: Any, *, default_role: str = "user") -> List[Dict[str, str]]:
    if value is None:
        return []
    if isinstance(value, str):
        return [{"role": default_role, "content": value}]
    if isinstance(value, dict):
        if "role" in value and "content" in value:
            return [
                {"role": str(value["role"]), "content": str(value["content"])}
            ]
        for key in ("messages", "turns", "user", "hitl", "items"):
            nested = value.get(key)
            if isinstance(nested, list):
                return _as_messages(nested, default_role=default_role)
        if "content" in value:
            return [
                {
                    "role": str(value.get("role") or default_role),
                    "content": str(value["content"]),
                }
            ]
        raise TypeError(f"cannot coerce mapping to messages: {sorted(value)}")
    if isinstance(value, list):
        out: List[Dict[str, str]] = []
        for item in value:
            out.extend(_as_messages(item, default_role=default_role))
        return out
    raise TypeError(f"messages must be a list, mapping, or string, got {type(value)}")


def _as_seeds(value: Any) -> Optional[List[Dict[str, Any]]]:
    if value is None:
        return None
    if isinstance(value, list):
        return value or None
    if isinstance(value, dict):
        if str(value.get("kind") or "") == "MemorySeed":
            entries = value.get("entries") or []
            seeds: List[Dict[str, Any]] = []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                seed = dict(entry)
                if "source" not in seed and seed.get("key"):
                    seed["source"] = seed["key"]
                if "content" not in seed and seed.get("text"):
                    seed["content"] = seed["text"]
                seeds.append(seed)
            return seeds or None
        for key in ("seeds", "items", "memory_seeds", "entries"):
            nested = value.get(key)
            if isinstance(nested, list):
                return nested or None
    raise TypeError(f"memory_seeds must be list, MemorySeed document, or ref, got {type(value)}")


@dataclass
class RunInput:
    user: List[Dict[str, str]]
    hitl: List[Dict[str, str]] = field(default_factory=list)
    turns: List[Dict[str, str]] = field(default_factory=list)
    """Authoritative ordered dialogue (may include roles/ordering ``user`` +
    ``hitl`` alone can't reconstruct — see :func:`_compose_dialogue`).
    Left empty, it defaults to ``list(user) + list(hitl)`` in
    :meth:`__post_init__` so it is always the single source :meth:`dialogue`
    reads, instead of ``dialogue`` also carrying its own fallback branch.
    """
    memory_seeds: Optional[List[Dict[str, Any]]] = None
    tool_fixtures: Any = None
    checkpoint_load: Any = None
    checkpoint_save: Any = False
    session_id: Optional[str] = None
    expectations: Dict[str, Any] = field(default_factory=dict)
    tool_fixture_ref: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.turns:
            self.turns = list(self.user) + list(self.hitl)

    @property
    def primary_prompt(self) -> str:
        for msg in self.dialogue():
            if msg.get("role") == "user" and msg.get("content"):
                return str(msg["content"])
        return str(self.user[0]["content"]) if self.user else ""

    def dialogue(self) -> List[Dict[str, str]]:
        """Ordered user + HITL (+ system) messages for this run."""
        return list(self.turns)

    def all_user_turns(self) -> List[Dict[str, str]]:
        """User messages after the initial prompt (multi-turn)."""
        users = [m for m in self.dialogue() if m.get("role") == "user"]
        return users[1:] if len(users) > 1 else []

    def scripted_queries(self) -> List[str]:
        """Ordered user + HITL messages for SessionController (interleaved)."""
        queries: List[str] = []
        for msg in self.dialogue():
            if msg.get("role") not in {"user", "hitl"}:
                continue
            content = msg.get("content")
            if content:
                queries.append(str(content))
        return queries


def _deep_merge_dict(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for key, value in overlay.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _deep_merge_dict(out[key], value)
        else:
            out[key] = value
    return out


def _scenario_block(scenario: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not scenario:
        return {}
    block: Dict[str, Any] = {}
    if isinstance(scenario.get("inputs"), dict):
        block["inputs"] = dict(scenario["inputs"])
    if isinstance(scenario.get("expectations"), dict):
        block["expectations"] = dict(scenario["expectations"])
    spec = scenario.get("spec") or {}
    if spec.get("memory_seed") is not None:
        block.setdefault("inputs", {})["memory_seeds"] = spec["memory_seed"]
    patch = spec.get("patch") or {}
    params = patch.get("params") if isinstance(patch, dict) else None
    if not isinstance(params, dict):
        params = scenario.get("params") if isinstance(scenario.get("params"), dict) else {}
    fixture = params.get("incident_fixture") if isinstance(params, dict) else None
    if fixture and "tool_fixtures" not in block.get("inputs", {}):
        block.setdefault("inputs", {})["tool_fixtures"] = fixture
    return block


def _experiment_defaults(experiment: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not experiment:
        return {}
    spec = experiment.get("spec") or experiment
    defaults = spec.get("defaults") or {}
    out: Dict[str, Any] = {}
    if isinstance(defaults.get("inputs"), dict):
        out["inputs"] = dict(defaults["inputs"])
    if isinstance(defaults.get("expectations"), dict):
        out["expectations"] = dict(defaults["expectations"])
    return out


def _compose_dialogue(
    user: List[Dict[str, str]],
    hitl: List[Dict[str, str]],
) -> tuple[List[Dict[str, str]], List[Dict[str, str]], List[Dict[str, str]]]:
    """Ordered user + HITL dialogue (there is no public ``inputs.turns``).

    Re-splits by role rather than returning ``user``/``hitl`` unchanged since
    legacy-coerced inputs may mix roles within either list.
    """
    dialogue = list(user) + list(hitl)
    users = [m for m in dialogue if m.get("role") == "user"]
    hitls = [m for m in dialogue if m.get("role") == "hitl"]
    return users, hitls, dialogue


def _legacy_item_to_envelope(
    item: Dict[str, Any],
    *,
    where: str = "dataset item",
) -> Dict[str, Any]:
    """Accept pre-envelope items (``prompt``, ``query``, top-level seeds / GT)."""
    if _is_legacy_item(item):
        from mas.lab.deprecations import warn_deprecated

        warn_deprecated("dataset.legacy_item", where=where)
    existing = item.get("inputs")
    if isinstance(existing, dict) and existing.get("user") is not None:
        return item
    prompt: Any = None
    if isinstance(existing, dict):
        prompt = existing.get("user")
    if prompt is None:
        for key in ("prompt", "query", "question", "text", "input"):
            if item.get(key) is not None:
                prompt = item[key]
                break
    if prompt is None and isinstance(item.get("user"), (str, list)):
        prompt = item["user"]
    if prompt is None:
        prompt = ""
    inputs: Dict[str, Any] = dict(existing) if isinstance(existing, dict) else {}
    inputs["user"] = prompt
    hitl: List[str] = []
    extra_users: List[str] = []
    for turn in item.get("turns") or []:
        if not isinstance(turn, dict):
            continue
        role = str(turn.get("role") or "user")
        content = str(turn.get("content") or "")
        if role == "hitl":
            hitl.append(content)
        elif role == "user" and content:
            extra_users.append(content)
    if extra_users:
        first = prompt if isinstance(prompt, str) else str(prompt)
        inputs["user"] = [first, *extra_users]
    if hitl:
        inputs["hitl"] = hitl
    if item.get("memory_seeds") is not None:
        inputs["memory_seeds"] = item["memory_seeds"]
    if item.get("session_id"):
        inputs["session_id"] = item["session_id"]
    expectations: Dict[str, Any] = {}
    gt = item.get("ground_truth") or item.get("expected_answer")
    if gt is not None:
        expectations["ground_truth"] = gt
    if item.get("correct_action") is not None:
        expectations["correct_action"] = item["correct_action"]
    _legacy_keys = set(_LEGACY_PROMPT_KEYS) | set(_LEGACY_TOP_KEYS) | {"user"}
    out = {k: v for k, v in item.items() if k not in _legacy_keys}
    out["inputs"] = inputs
    if expectations:
        out["expectations"] = {**dict(item.get("expectations") or {}), **expectations}
    return out


def load_run_input(
    item: Dict[str, Any],
    *,
    scenario: Optional[Dict[str, Any]] = None,
    experiment: Optional[Dict[str, Any]] = None,
    base_path: Optional[Path] = None,
    source: Optional[Path] = None,
) -> RunInput:
    """Merge experiment → scenario → item envelope into :class:`RunInput`."""
    where = str(source or base_path or f"item {item.get('id')!r}")
    item = _legacy_item_to_envelope(item, where=where)
    merged: Dict[str, Any] = {}
    merged = _deep_merge_dict(merged, _experiment_defaults(experiment))
    merged = _deep_merge_dict(merged, _scenario_block(scenario))
    merged = _deep_merge_dict(
        merged,
        {
            "inputs": dict(item["inputs"]),
            "expectations": dict(item.get("expectations") or {}),
        },
    )

    inputs = merged["inputs"]
    if _is_role_message_shape(inputs.get("user")):
        from mas.lab.deprecations import warn_deprecated

        warn_deprecated("dataset.role_list_user", where=where)
    user = _as_messages(_resolve_text_slot(inputs.get("user"), base_path), default_role="user")
    hitl = _as_messages(_resolve_text_slot(inputs.get("hitl"), base_path), default_role="hitl")
    user, hitl, dialogue = _compose_dialogue(user, hitl)
    if not user:
        user = [{"role": "user", "content": ""}]
        dialogue = list(user) + list(hitl)

    memory_raw = inputs.get("memory_seeds")
    if isinstance(memory_raw, str) or _is_ref_object(memory_raw):
        memory_raw = _resolve_file_slot(memory_raw, base_path)
    memory_seeds = _as_seeds(memory_raw) if memory_raw is not None else None
    tool_fixture_ref = None
    raw_tool_fixtures = inputs.get("tool_fixtures")
    if isinstance(raw_tool_fixtures, dict) and isinstance(
        raw_tool_fixtures.get("incident_fixture"), str
    ):
        tool_fixture_ref = raw_tool_fixtures["incident_fixture"]
    tool_fixtures = (
        _resolve_fixture(inputs.get("tool_fixtures"), base_path)
        if inputs.get("tool_fixtures") is not None
        else None
    )
    expectations_raw = _resolve_text_slot(merged.get("expectations"), base_path)
    if expectations_raw is None:
        expectations: Dict[str, Any] = {}
    elif isinstance(expectations_raw, dict):
        if _is_ref_object(expectations_raw):
            loaded = _resolve_text_slot(expectations_raw, base_path)
            if not isinstance(loaded, dict):
                raise TypeError("expectations must resolve to a mapping")
            expectations = dict(loaded)
        else:
            expectations = dict(expectations_raw)
    else:
        raise TypeError("expectations must resolve to a mapping")

    checkpoint = inputs.get("checkpoint") or {}
    if isinstance(checkpoint, dict):
        load_val = checkpoint.get("load")
        if isinstance(load_val, str) or _is_ref_object(load_val):
            checkpoint_load = _resolve_file_slot(load_val, base_path)
        else:
            checkpoint_load = load_val
        checkpoint_save = checkpoint.get("save", False)
    else:
        checkpoint_load = None
        checkpoint_save = False

    return RunInput(
        user=user,
        hitl=hitl,
        turns=dialogue,
        memory_seeds=memory_seeds,
        tool_fixtures=tool_fixtures,
        checkpoint_load=checkpoint_load,
        checkpoint_save=checkpoint_save,
        session_id=inputs.get("session_id"),
        expectations=expectations,
        tool_fixture_ref=tool_fixture_ref,
    )


def run_input_to_dict(run_input: RunInput) -> Dict[str, Any]:
    user_texts = [str(m.get("content") or "") for m in run_input.user]
    user_field: Any = user_texts[0] if len(user_texts) == 1 else user_texts
    inputs: Dict[str, Any] = {"user": user_field}
    if run_input.hitl:
        inputs["hitl"] = [str(m.get("content") or "") for m in run_input.hitl]
    if run_input.memory_seeds is not None:
        inputs["memory_seeds"] = run_input.memory_seeds
    if run_input.tool_fixtures is not None:
        inputs["tool_fixtures"] = run_input.tool_fixtures
    if run_input.session_id:
        inputs["session_id"] = run_input.session_id
    if run_input.checkpoint_load is not None or run_input.checkpoint_save:
        inputs["checkpoint"] = {
            "load": run_input.checkpoint_load,
            "save": run_input.checkpoint_save,
        }
    out: Dict[str, Any] = {"inputs": inputs}
    if run_input.expectations:
        out["expectations"] = run_input.expectations
    return out


def fingerprint_run_input(run_input: RunInput) -> str:
    """Stable hash for trace-cache ``inputs.json``."""
    payload = json.dumps(run_input_to_dict(run_input), sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_run_input_envelope(data: Dict[str, Any]) -> None:
    from mas.lab.schemas.validate import validate_against_lab_schema

    validate_against_lab_schema("run-input", data)
