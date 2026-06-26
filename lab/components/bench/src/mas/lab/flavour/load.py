#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Load flavour YAML as dict for bench cache keys and infra refs."""


from pathlib import Path
from typing import Any

from mas.ctl.validate import validate_data, validation_enabled
from mas.runtime.spec.source import load_yaml_mapping


def load_flavour(path: Path | str, *, validate: bool = False) -> dict[str, Any]:
    data = load_yaml_mapping(Path(path))
    if validate and validation_enabled():
        validate_data(data, kind="flavour").raise_if_failed()
    return data
