#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Pin a2a-sdk self-instrumentation off before tests import a2a."""

from __future__ import annotations

import mas.third_party_otel  # noqa: F401
