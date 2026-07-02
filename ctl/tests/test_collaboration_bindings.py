#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import pytest

from mas.ctl.manifest.spec_bindings import SpecBindingError, parse_collaboration


def test_parse_collaboration_rejects_non_none_type():
    with pytest.raises(SpecBindingError, match="llm-delegator"):
        parse_collaboration({"type": "llm-delegator"})


def test_parse_collaboration_rejects_ref():
    with pytest.raises(SpecBindingError, match="ref"):
        parse_collaboration({"ref": "module://example.Plugin"})


def test_parse_collaboration_allows_none():
    parse_collaboration({"type": "none"})
