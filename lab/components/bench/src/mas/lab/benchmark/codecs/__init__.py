#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Codec registry — coder/decoder pairs for artifact kinds and store types.

Usage
-----
To register a codec (typically at module level in the codec module)::

    from mas.lab.benchmark.codecs import register_codec
    from mas.lab.benchmark.codecs.base import Codec

    @register_codec
    class ClickHouseOtelCodec(Codec):
        artifact_kind = "otel_traces"
        store_type    = "clickhouse"
        ...

To look up a codec at runtime::

    from mas.lab.benchmark.codecs import get_codec
    codec_cls = get_codec("otel_traces", "clickhouse")
    codec = codec_cls(store_spec)
    codec.encode(artifact)

"""

from mas.lab.benchmark.codecs.base import Codec
from mas.lab.benchmark.codecs.registry import get_codec, list_codecs, register_codec

__all__ = ["Codec", "register_codec", "get_codec", "list_codecs"]
