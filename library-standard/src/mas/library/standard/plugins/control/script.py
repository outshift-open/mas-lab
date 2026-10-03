#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Control command language — a script file and a chained CLI are the same.

``pause --reason freeze persist --label bad --auto-stop`` in argv is
equivalent to those two lines in a file, and to curl-style ``-d @file`` /
``-d 'pause --reason freeze'``. Agents call ``ControlContract.run_script``.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONTROL_VERBS = (
    "attach",
    "inspect",
    "pause",
    "resume",
    "snapshot",
    "persist",
    "checkpoints",
    "steer",
    "enqueue",
    "enqueue_input",
    "navigate",
    "info",
)


@dataclass(frozen=True)
class ControlStatement:
    verb: str
    kwargs: dict[str, Any] = field(default_factory=dict)
    raw: str = ""


def parse_queue_at(raw: Any) -> int | str:
    """``head``, ``tail``, or a 0-based index from ``inspect_queue``."""
    if raw is None or raw is True:
        return "tail"
    if isinstance(raw, bool):
        raise ValueError(f"enqueue at must be 'head', 'tail', or an index, got {raw!r}")
    if isinstance(raw, int):
        return raw
    text = str(raw).strip()
    if text in {"head", "tail"}:
        return text
    if text.isdigit():
        return int(text)
    raise ValueError(f"enqueue at must be 'head', 'tail', or an index, got {raw!r}")


def resolve_curl_data(value: str, *, base_dir: str | Path = "") -> str:
    """curl ``-d``: ``@path`` reads a file; anything else is inline text."""
    text = str(value or "")
    if not text.startswith("@"):
        return text
    path = Path(text[1:])
    if not path.is_file() and base_dir and not path.is_absolute():
        path = Path(base_dir) / path
    if not path.is_file():
        raise FileNotFoundError(f"control script not found ({path})")
    return path.read_text(encoding="utf-8")


def parse_control_script(text: str) -> list[ControlStatement]:
    """Parse newline-oriented control commands (comments with ``#``)."""
    statements: list[ControlStatement] = []
    for raw_line in str(text or "").splitlines():
        stripped = raw_line.split("#", 1)[0].strip()
        if not stripped:
            continue
        if stripped.lower().startswith("break "):
            raise ValueError(
                "gdb breakpoints belong on --debug-script / spec.governance "
                "debug_script, not mas-ctl control -d"
            )
        statements.append(_parse_tokens(shlex.split(stripped), raw=stripped))
    return statements


def parse_control_chain(tokens: list[str]) -> list[ControlStatement]:
    """Split a chained argv into the same statements a script file would yield."""
    statements: list[ControlStatement] = []
    current: list[str] = []
    for token in tokens:
        if not str(token).startswith("-") and str(token).lower() in CONTROL_VERBS and current:
            statements.append(_parse_tokens(current, raw=" ".join(current)))
            current = [token]
            continue
        current.append(str(token))
    if current:
        statements.append(_parse_tokens(current, raw=" ".join(current)))
    return statements


def _parse_tokens(tokens: list[str], *, raw: str) -> ControlStatement:
    if not tokens:
        raise ValueError("empty control command")
    verb = tokens[0].lower().lstrip("-")
    if verb not in CONTROL_VERBS:
        raise ValueError(f"unknown control command {tokens[0]!r}")
    kwargs: dict[str, Any] = {}
    rest = tokens[1:]
    i = 0
    while i < len(rest):
        item = rest[i]
        if item.startswith("--") and item != "--":
            key = item[2:].replace("-", "_")
            if key.startswith("no_"):
                kwargs[key[3:]] = False
                i += 1
                continue
            if i + 1 < len(rest) and not str(rest[i + 1]).startswith("--"):
                kwargs[key] = _flag_value(verb, key, rest[i + 1])
                i += 2
                continue
            kwargs[key] = True
            i += 1
            continue
        if item.startswith("-") and len(item) == 2:
            short = {"r": "reason", "l": "label", "t": "text"}.get(item[1:])
            if short is None:
                raise ValueError(f"unknown flag {item!r} in {raw!r}")
            if i + 1 >= len(rest):
                raise ValueError(f"{item} requires a value in {raw!r}")
            kwargs[short] = rest[i + 1]
            i += 2
            continue
        raise ValueError(f"unexpected token {item!r} in {raw!r}")
    return ControlStatement(verb=verb, kwargs=kwargs, raw=raw)


def _flag_value(verb: str, key: str, raw: str) -> Any:
    if key == "at":
        return parse_queue_at(raw)
    if key in {"auto_stop"}:
        lowered = str(raw).lower()
        if lowered in {"1", "true", "yes"}:
            return True
        if lowered in {"0", "false", "no"}:
            return False
        return True
    return raw


def run_control_script(
    control: Any,
    session_id: str,
    statements: list[ControlStatement],
    *,
    default_auto_stop: bool = False,
) -> list[Any]:
    """Execute parsed statements against a ControlContract."""
    results: list[Any] = []
    for statement in statements:
        results.append(
            _run_one(
                control,
                session_id,
                statement,
                default_auto_stop=default_auto_stop,
            )
        )
    return results


def _run_one(
    control: Any,
    session_id: str,
    statement: ControlStatement,
    *,
    default_auto_stop: bool,
) -> Any:
    verb = statement.verb
    kwargs = dict(statement.kwargs)
    if verb == "attach":
        return control.inspect(session_id)
    if verb == "inspect" or verb == "info":
        topic = str(kwargs.get("topic") or kwargs.get("text") or "").strip()
        if topic in {"checkpoints", "checkpoint"}:
            return control.list_checkpoints(session_id)
        if topic in {"queue", "queued"}:
            return control.inspect_queue(session_id)
        return control.inspect(session_id)
    if verb == "pause":
        return control.pause(session_id, reason=str(kwargs.get("reason") or "operator"))
    if verb == "resume":
        return control.resume(session_id)
    if verb == "snapshot":
        auto_stop = bool(kwargs.get("auto_stop", default_auto_stop))
        return control.snapshot(
            session_id,
            label=str(kwargs.get("label") or ""),
            auto_stop=auto_stop,
        )
    if verb == "persist":
        auto_stop = bool(kwargs.get("auto_stop", default_auto_stop))
        extra: dict[str, Any] = {
            "label": str(kwargs.get("label") or ""),
            "auto_stop": auto_stop,
        }
        if kwargs.get("snapshot_id"):
            extra["snapshot_id"] = str(kwargs["snapshot_id"])
        return control.persist(session_id, **extra)
    if verb == "checkpoints":
        return control.list_checkpoints(session_id)
    if verb == "steer":
        text = str(kwargs.get("text") or "")
        if not text:
            raise ValueError("steer requires --text")
        if kwargs.get("replace") and (kwargs.get("after") or kwargs.get("enqueue")):
            raise ValueError("steer: use --replace or --after, not both")
        if kwargs.get("replace"):
            mode = "replace"
        elif kwargs.get("after") or kwargs.get("enqueue"):
            mode = "after"
        else:
            mode = "preempt"
        return control.steer(
            session_id,
            text=text,
            mode=mode,
            at=parse_queue_at(kwargs.get("at", "head")),
        )
    if verb in {"enqueue", "enqueue_input"}:
        text = str(kwargs.get("text") or "")
        if not text:
            raise ValueError("enqueue requires --text")
        action = str(kwargs.get("action") or "turn")
        if action not in {"turn", "steer"}:
            raise ValueError("enqueue --action must be turn or steer")
        return control.enqueue_input(
            session_id,
            text=text,
            source=str(kwargs.get("source") or "script"),
            action=action,
            at=parse_queue_at(kwargs.get("at", "tail")),
        )
    if verb == "navigate":
        to = str(kwargs.get("to") or "")
        if not to:
            raise ValueError("navigate requires --to")
        return control.navigate(session_id, to=to, reason=str(kwargs.get("reason") or "script"))
    raise ValueError(f"unknown control command {verb!r}")
