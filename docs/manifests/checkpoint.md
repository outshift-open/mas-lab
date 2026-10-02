<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Session checkpoints

Session checkpoints preserve the runtime kernel and conversation history as a
single resumable artifact. Version 2 also contains session lineage and the
agent manifest, so a process can rebuild a session without the original
manifest file. Keep credentials in environment/secret-store references; a
checkpoint must not contain inline secrets.

## Policy

`spec.checkpoint` defaults to no automatic checkpointing. Configure it on an
Agent manifest or apply the standard `openclaw` overlay:

```yaml
spec:
  checkpoint:
    mode: on_event
    triggers: [after_llm_call]
    retention:
      mode: last_n
      n: 5
    portability: self_contained
    auto_resume_latest: false
```

| Setting | Values | Default |
| --- | --- | --- |
| `mode` | `none`, `in_memory`, `on_event`, `every_turn` | `none` |
| `triggers` | `after_llm_call`, `after_tool_call`, `before_destructive_tool`, `every_n_turns` | `[]` |
| `every_n_turns` | Positive integer; used with the `every_n_turns` trigger | unset |
| `retention.mode` | `all`, `single`, `last_n` | `all` |
| `retention.n` | Positive integer for `last_n` | `5` |
| `portability` | `self_contained`, `reference` | `self_contained` |
| `auto_resume_latest` | Boolean | `false` |

`in_memory` supports rollback during the current process only. `on_event` writes
at selected LLM/tool boundaries; `every_turn` writes after each completed user
turn. When disk persistence is enabled without `--checkpoint-dir`, the CLI uses
`.mas/checkpoints` beside the active manifest (or current working directory).
Retention prunes only files belonging to the same session.

## Resume and fork

Create an explicit checkpoint with `mas-ctl chat agent.yaml --checkpoint-dir
.mas/checkpoints --save-checkpoint`, or enable automatic checkpoints through
the policy. List artifacts and fork one into a new session identity:

```bash
mas-ctl checkpoint list .mas/checkpoints
mas-ctl checkpoint fork <checkpoint-path-from-list> \
  --output-dir .mas/forks
mas-ctl chat --load-checkpoint <fork-checkpoint-path-printed-by-fork>
```

The fork command prints its output path. For version 2, `--load-checkpoint` can
use the embedded manifest when no manifest argument is supplied. Resume
preserves the session ID and history.
Fork creates a new session ID, records its parent and source checkpoint, and
copies history up to that point; later turns do not share mutable memory.
Version 1 checkpoints remain loadable as kernel-only snapshots when used with
an explicit manifest.

In a live process, an in-memory **snapshot tree** is cheaper than a checkpoint.
`take_snapshot` does not write disk. Walking the tree moves a debug cursor;
it does not change the live run until a branch is promoted. See
[Snapshots vs checkpoints](../references/snapshots.md). Pause
(`ControlContract.pause`) blocks the next user turn until resume.

## Backtracking

Manual backtracking is available in a managed chat with checkpoints enabled:

```text
/backtrack 1 Avoid the failed tool approach and ask for missing details first.
```

Automatic recovery is opt-in through an error-recovery governance binding:

```yaml
spec:
  checkpoint:
    mode: every_turn
  governance:
    - sample:
        error_recovery_plugin: backtrack_on_error
        backtrack:
          repeat_threshold: 2
          max_backtracks_per_session: 3
          steps: 1
          on_cap_reached: hitl
```

The recovery plugin retries the same engine error first. Once its signature
repeats, the kernel emits a backtrack boundary signal; the session layer restores
the retained checkpoint and injects a steering message. Design-pattern plugins
do not own this policy. `on_cap_reached` accepts `hitl`, `terminate`, or
`stop_backtracking`.