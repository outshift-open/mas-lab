#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Shared CLI defaults for ctl runtime / kernel selection."""

from __future__ import annotations

import click

from mas.ctl.registry.catalog import list_runtime_ids


def runtime_id_choice() -> click.Choice:
    return click.Choice(list_runtime_ids(include_planned=False), case_sensitive=False)
