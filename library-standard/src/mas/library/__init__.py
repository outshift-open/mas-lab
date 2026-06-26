#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""``mas.library`` namespace — extended by optional workspace packages (e.g. eval)."""
from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)
