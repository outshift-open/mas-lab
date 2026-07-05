#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
# Removed — plugin construction moved to mas.runtime.boundary.obs.loader.
# This shim re-exports the canonical constants so old imports don't break.
DEFAULT_OTLP_ENDPOINT = "http://localhost:4318"
DEFAULT_OTLP_ENDPOINT_ENV = "OTEL_EXPORTER_OTLP_ENDPOINT"

__all__ = ["DEFAULT_OTLP_ENDPOINT", "DEFAULT_OTLP_ENDPOINT_ENV"]
