#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from mas.runtime.constants import (
    DEFAULT_RUNTIME_ID,
    LEGACY_WORKSPACE_CONFIG_FILENAME,
    USER_CONFIG_FILENAME,
    WORKSPACE_CONFIG_FILENAME,
)
from mas.runtime.xdg import mas_user_config_file


def test_workspace_config_filename_matches_xdg_user_config() -> None:
    assert USER_CONFIG_FILENAME == WORKSPACE_CONFIG_FILENAME
    assert mas_user_config_file().name == WORKSPACE_CONFIG_FILENAME


def test_legacy_workspace_filename_is_distinct() -> None:
    assert LEGACY_WORKSPACE_CONFIG_FILENAME != WORKSPACE_CONFIG_FILENAME


def test_default_runtime_id_is_mas_runtime_py() -> None:
    assert DEFAULT_RUNTIME_ID == "mas-runtime-py"
