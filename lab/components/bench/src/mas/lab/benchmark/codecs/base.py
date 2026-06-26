#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""Codec base class — abstract encoder/decoder pair.

A ``Codec`` handles encoding (write) and decoding (read) of a specific
artifact kind to/from a specific store type.

Subclasses MUST declare two class attributes::

    artifact_kind: ClassVar[str]  # e.g. "otel_traces", "kg", "events"
    store_type:    ClassVar[str]  # e.g. "clickhouse", "neo4j", "filesystem"

These two attributes form the dispatch key used by :func:`register_codec`
and :func:`get_codec`.

Example::

    from mas.lab.benchmark.codecs import register_codec
    from mas.lab.benchmark.codecs.base import Codec

    @register_codec
    class MyCodec(Codec):
        artifact_kind = "otel_traces"
        store_type    = "clickhouse"

        def encode(self, artifact, **opts):
            ...

        def decode(self, **opts):
            ...
"""


from abc import ABC, abstractmethod
from typing import Any, ClassVar

from mas.lab.infra.datastore import DatastoreSpec


class Codec(ABC):
    """Abstract encoder/decoder for a specific (artifact_kind, store_type) pair.

    Subclasses register themselves via :func:`~mas.lab.benchmark.codecs.register_codec`
    and are instantiated with the matching :class:`~mas.lab.infra.datastore.DatastoreSpec`
    from the resolved infra bundle.
    """

    artifact_kind: ClassVar[str]
    """Artifact kind handled by this codec (e.g. ``"otel_traces"``, ``"kg"``)."""

    store_type: ClassVar[str]
    """Store type handled by this codec (e.g. ``"clickhouse"``, ``"neo4j"``, ``"filesystem"``)."""

    def __init__(self, store: DatastoreSpec) -> None:
        self.store = store

    @abstractmethod
    def encode(self, artifact: Any, **opts: Any) -> None:
        """Write *artifact* to the store.

        Args:
            artifact: The object to persist.  Its type is specific to each
                      ``artifact_kind`` (e.g. a list of OTLP spans, a KG graph).
            **opts:   Optional codec-specific keyword arguments (e.g. table name,
                      output path template, compression).
        """

    @abstractmethod
    def decode(self, **opts: Any) -> Any:
        """Read an artifact from the store.

        Args:
            **opts: Optional codec-specific keyword arguments (e.g. session_id,
                    time range, filter predicates).

        Returns:
            The decoded artifact.  Type is specific to ``artifact_kind``.
        """
