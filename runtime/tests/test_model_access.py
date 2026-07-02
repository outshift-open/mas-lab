#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import pytest

from mas.runtime.engine.model_access import ModelAccessLoadError, load_model_access


def test_load_model_access_returns_none_when_unconfigured():
    assert load_model_access(None) is None
    assert load_model_access({}) is None
    assert load_model_access({"provider": "mock"}) is None


def test_load_model_access_chains_import_error():
    cfg = {
        "module_path": "mas.library.standard.plugins.no_such_module",
        "class_name": "MockModelAccess",
    }
    with pytest.raises(ModelAccessLoadError, match="no_such_module") as exc_info:
        load_model_access(cfg)
    assert isinstance(exc_info.value.__cause__, ModuleNotFoundError)
