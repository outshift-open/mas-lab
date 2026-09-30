#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Version tags and package-style dependency ranges (``name@version`` / ``name@>=v1,<v3``)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_CLAUSE = re.compile(
    r"^(?P<op>~=|==|!=|<=|>=|<|>|\^)?\s*(?P<ver>v?\d+(?:\.\d+)*)$",
    re.IGNORECASE,
)


def normalize_version(version: str) -> str:
    """Return a ``v``-prefixed tag (``1`` → ``v1``, ``v2.0`` stays ``v2.0``)."""
    text = str(version or "").strip()
    if not text:
        return text
    if text.lower() == "latest":
        return text
    if not text.startswith("v"):
        return f"v{text}"
    return text


def version_sort_key(version: str) -> tuple[Any, ...]:
    text = normalize_version(version)
    if text.startswith("v"):
        text = text[1:]
    parts: list[Any] = []
    for part in text.split("."):
        parts.append(int(part) if part.isdigit() else part)
    return tuple(parts)


def _next_major(version: str) -> str:
    key = version_sort_key(version)
    major = key[0] if key and isinstance(key[0], int) else 0
    return f"v{major + 1}"


@dataclass(frozen=True)
class AppDependency:
    """An app this dataset (or other artefact) is declared to work with."""

    name: str
    spec: str | None = None
    library: str | None = None

    def __str__(self) -> str:
        prefix = f"{self.library}:" if self.library else ""
        if self.spec:
            return f"{prefix}{self.name}@{self.spec}"
        return f"{prefix}{self.name}"


def parse_app_dependency(value: str | dict[str, Any] | None) -> AppDependency | None:
    """Parse ``[library:]name[@spec]`` or ``{name, version, library}``.

    *spec* is a version tag (``v1`` = exact) or a comma-separated range
    (``>=v1,<v3``, ``^v1``). Bare *name* means any version of that app.
    """
    if value is None:
        return None
    if isinstance(value, dict):
        name = str(value.get("name") or "").strip()
        if not name:
            return None
        spec = value.get("version") or value.get("spec")
        spec_s = str(spec).strip() if spec else None
        lib = value.get("library")
        lib_s = str(lib).strip() if lib else None
        return AppDependency(name=name, spec=spec_s or None, library=lib_s)
    text = str(value).strip()
    if not text:
        return None
    library, rest = split_library_prefix(text)
    if "@" not in rest:
        return AppDependency(name=rest, spec=None, library=library)
    name, _, spec = rest.rpartition("@")
    name = name.strip()
    spec = spec.strip()
    if not name:
        return None
    if not spec or spec.lower() == "latest":
        return AppDependency(name=name, spec=None, library=library)
    return AppDependency(name=name, spec=spec, library=library)


def _clauses(spec: str) -> list[tuple[str, str]]:
    raw = spec.strip()
    if not raw:
        return []
    out: list[tuple[str, str]] = []
    for piece in raw.split(","):
        token = piece.strip()
        if not token:
            continue
        match = _CLAUSE.match(token)
        if not match:
            raise ValueError(f"Invalid version specifier {token!r} in {spec!r}")
        op = match.group("op") or "=="
        ver = normalize_version(match.group("ver"))
        out.append((op, ver))
    return out


def version_satisfies(version: str, spec: str | None) -> bool:
    """True when *version* matches *spec*. ``None`` / empty / ``latest`` match any."""
    if spec is None:
        return True
    text = str(spec).strip()
    if not text or text.lower() == "latest":
        return True
    have = normalize_version(version)
    have_key = version_sort_key(have)
    for op, bound in _clauses(text):
        bound_key = version_sort_key(bound)
        if op == "==":
            if have_key != bound_key:
                return False
        elif op == "!=":
            if have_key == bound_key:
                return False
        elif op == ">=":
            if have_key < bound_key:
                return False
        elif op == ">":
            if have_key <= bound_key:
                return False
        elif op == "<=":
            if have_key > bound_key:
                return False
        elif op == "<":
            if have_key >= bound_key:
                return False
        elif op == "^":
            if have_key < bound_key or have_key >= version_sort_key(_next_major(bound)):
                return False
        elif op == "~=":
            if have_key < bound_key:
                return False
            # Compatible release: same length-1 prefix (PEP 440-ish on our tags).
            prefix = bound_key[:-1] or bound_key[:1]
            if have_key[: len(prefix)] != prefix:
                return False
        else:
            raise ValueError(f"Unsupported version operator {op!r}")
    return True


def split_library_prefix(ref: str) -> tuple[str | None, str]:
    """Split ``library:object`` when *ref* is that form (not a filesystem path).

    Returns ``(None, ref)`` when *ref* has no valid library-name prefix
    (no ``:``, an absolute path, or a Windows-style drive letter).
    """
    text = str(ref or "").strip()
    if ":" not in text or text.startswith("/") or Path(text).is_absolute():
        return None, text
    scheme, _, rest = text.partition(":")
    if not scheme or not rest or "/" in scheme or "\\" in scheme:
        return None, text
    return scheme, rest


def split_name_version(object_id: str) -> tuple[str, str | None]:
    """Split ``name@version``. Bare ``name`` means latest (``version is None``)."""
    text = str(object_id or "").strip()
    if "@" not in text:
        return text, None
    name, _, ver = text.rpartition("@")
    name, ver = name.strip(), ver.strip()
    if not name:
        return text, None
    if not ver or ver.lower() == "latest":
        return name, None
    return name, normalize_version(ver)


def app_satisfies(app_id: str, dependency: str | dict[str, Any] | AppDependency | None) -> bool:
    """True when catalog id ``name@version`` satisfies a dataset ``spec.app`` dependency."""
    if dependency is None:
        return True
    dep = dependency if isinstance(dependency, AppDependency) else parse_app_dependency(dependency)
    if dep is None:
        return True
    lib, rest = split_library_prefix(app_id)
    if dep.library and lib and dep.library != lib:
        return False
    name, ver = split_name_version(rest)
    if name != dep.name:
        return False
    if dep.spec is None:
        return True
    if ver is None:
        # Bare name means latest; assume the resolved latest is in range.
        return True
    return version_satisfies(ver, dep.spec)
