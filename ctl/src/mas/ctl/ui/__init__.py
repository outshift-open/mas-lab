#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Ctl UI surfaces — stdout, curses (web uses REST/WS adapters, same SessionController)."""

from mas.ctl.ui.display import ConversationDisplay
from mas.ctl.ui.stdout import StdoutConversationDisplay

__all__ = ["ConversationDisplay", "StdoutConversationDisplay"]
