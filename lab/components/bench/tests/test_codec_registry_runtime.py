#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from mas.lab.benchmark.codecs import get_codec, list_codecs, register_codec
from mas.lab.benchmark.codecs.base import Codec


@register_codec
class _UnitCodec(Codec):
    artifact_kind = "unit_artifact"
    store_type = "unit_store"

    def encode(self, artifact, **kwargs):
        return None

    def decode(self, **kwargs):
        return {"ok": True}


def test_get_codec_via_runtime_registry() -> None:
    codec_cls = get_codec("unit_artifact", "unit_store")
    assert codec_cls is _UnitCodec


def test_list_codecs_includes_registered_runtime_codec() -> None:
    assert ("unit_artifact", "unit_store") in list_codecs()
