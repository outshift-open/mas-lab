<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# debug_script example

gdb-like breakpoints as a **runtime** plugin (`mas.runtime.debug_script`).
Enable from `config.yaml` `plugins:`; `spec.debug` holds the script.

```yaml
spec:
  debug:
    script_file: ./debug.gdb
```

```bash
mas-ctl validate library-standard/examples/governance/debug-script/agent.yaml
mas-ctl chat library-standard/examples/governance/debug-script/agent.yaml \
  --checkpoint-dir .mas/debug-script-checkpoints \
  --debug-script @library-standard/examples/governance/debug-script/debug.gdb
```

`recover.ctl` pauses and persists a stopped session. `steer-fix.ctl` steers
a chat resumed from that checkpoint.
