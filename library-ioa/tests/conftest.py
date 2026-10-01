#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Pin third-party OTel off before a2a-sdk is imported during collection."""

from __future__ import annotations

import mas.third_party_otel  # noqa: F401
