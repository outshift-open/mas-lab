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

`spec.checkpoint` defaults to no automatic checkpointing. Configure cadence
(`mode`) and location (`storage`) on an Agent manifest, or apply the standard
`openclaw` overlay:

```yaml
spec:
  checkpoint:
    mode: every_turn
    storage:
      kind: hybrid
      path: .mas/checkpoints
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
| `storage` | `memory`, `disk`, `hybrid`, or `{kind, path}` | inferred from `mode` |
| `triggers` | `after_llm_call`, `after_tool_call`, `before_destructive_tool`, `every_n_turns` | `[]` |
| `every_n_turns` | Positive integer; used with the `every_n_turns` trigger | unset |
| `retention.mode` | `all`, `single`, `last_n` | `all` |
| `retention.n` | Positive integer for `last_n` | `5` |
| `portability` | `self_contained`, `reference` | `self_contained` |
| `auto_resume_latest` | Boolean | `false` |

`mode` is **when** to capture. `storage` is **where** payloads live, resolved
as a library **`checkpoint_store` plugin** (`memory`, `disk`, `hybrid`) that
implements kernel `persist`. It is not a new envelope slot:

- `memory` — process-local. `/backtrack` works; a new process cannot load.
- `disk` — JSON files. `checkpoint list` / `fork` / `--load-checkpoint`.
- `hybrid` — memory plus files. Fast in-process copy; disk is the resume witness.

When `storage` is omitted, `mode: in_memory` means memory; `on_event` and
`every_turn` mean disk. `auto_resume_latest` requires disk or hybrid.
A workspace or lab may enable a store via `config.yaml` `plugins:` /
`lab.enable_plugins` (`mas.checkpoint_store.hybrid`, …) when the spec omits
`storage`. Spec `storage` still wins. CLI `--checkpoint-dir` overrides
`storage.path`. When disk persistence is
enabled without either, the CLI uses `.mas/checkpoints` beside the active
manifest (or current working directory). Retention prunes only files belonging
to the same session.

A walkthrough (crash, resume, fork, backtrack):
[Tutorial 11](../tutorials/11-sessions-and-recovery/).

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