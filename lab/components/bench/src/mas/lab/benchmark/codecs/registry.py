#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""Codec registry — extensible (artifact_kind, store_type) → Codec dispatch.

External packages register their codecs by calling :func:`register_codec`
(or using it as a decorator) at module import time.  No static mapping is
hardcoded here — the registry is populated purely through explicit
``register_codec`` calls.

This mirrors the ``register_step_type`` pattern used for pipeline steps.
"""


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mas.lab.benchmark.codecs.base import Codec

_CODEC_REGISTRY: dict[tuple[str, str], type["Codec"]] = {}


def register_codec(codec_class: type["Codec"]) -> type["Codec"]:
    """Register a codec by its declared ``artifact_kind`` and ``store_type``.

    Can be used as a class decorator::

        @register_codec
        class ClickHouseOtelCodec(Codec):
            artifact_kind = "otel_traces"
            store_type    = "clickhouse"

    Or called directly::

        register_codec(ClickHouseOtelCodec)

    Args:
        codec_class: A :class:`~mas.lab.benchmark.codecs.base.Codec` subclass
                     with ``artifact_kind`` and ``store_type`` class attributes.

    Returns:
        The same class (so it can be used as a decorator without side-effects).

    Raises:
        AttributeError: If the class is missing ``artifact_kind`` or ``store_type``.
    """
    key = (codec_class.artifact_kind, codec_class.store_type)
    _CODEC_REGISTRY[key] = codec_class
    return codec_class


def get_codec(artifact_kind: str, store_type: str) -> type["Codec"]:
    """Retrieve the codec class for a given (artifact_kind, store_type) pair.

    Args:
        artifact_kind: Logical artifact kind (e.g. ``"otel_traces"``, ``"kg"``).
        store_type:    Target store type (e.g. ``"clickhouse"``, ``"neo4j"``,
                       ``"filesystem"``).

    Returns:
        The registered :class:`~mas.lab.benchmark.codecs.base.Codec` subclass.

    Raises:
        ValueError: If no codec is registered for this combination.  The error
                    message lists all currently registered combinations to help
                    diagnose missing imports.
    """
    key = (artifact_kind, store_type)
    codec_cls = _CODEC_REGISTRY.get(key)
    if codec_cls is None:
        available = sorted(_CODEC_REGISTRY)
        raise ValueError(
            f"No codec registered for ({artifact_kind!r}, {store_type!r}). "
            f"Did you import the codec module?  Available: {available}"
        )
    return codec_cls


def list_codecs() -> list[tuple[str, str]]:
    """Return all registered (artifact_kind, store_type) combinations."""
    return sorted(_CODEC_REGISTRY)
