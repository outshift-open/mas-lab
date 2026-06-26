#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Infra manifest resolution — workspace bundles, user config, library entry points."""

from mas.ctl.infra.resolve import InfraResolveError, resolve_infra_refs

__all__ = ["InfraResolveError", "resolve_infra_refs"]
