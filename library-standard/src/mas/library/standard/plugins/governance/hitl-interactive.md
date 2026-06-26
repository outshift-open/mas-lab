<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# hitl-interactive@ctl — boundary HitlTerminal (TTY / TUI)

Maps to `OperatorConsole` / curses HITL in `mas.ctl.session`.
Driver `hitl=None`; ctl drains `EmitHitlRequest` and feeds `HitlResolve`.

Manifest:

```yaml
spec:
  governance:
    hitl_on_tool: true
    hitl_mode: interactive
```

Requires a TTY for `mas-ctl chat -i` or use `mas-ctl tui`.
