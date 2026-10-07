<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Tutorial 11 — Sessions and recovery

> **Packages:** `mas-runtime`, `mas-ctl`
> **Prerequisite:** [Tutorial 0](../00-environment-setup/) and an Agent manifest
> that runs with the configured model.

This tutorial saves a complete conversation, forks the saved state, resumes the
fork without its original manifest path, and returns to an earlier checkpoint
with a steering note.

## Capture a checkpoint

From the repository root, run an agent with explicit disk persistence:

```bash
mas-ctl chat docs/tutorials/01-building-an-agent/agent.yaml \
  --checkpoint-dir .mas/checkpoints --save-checkpoint
```

Complete at least one turn, then exit with `/quit`. Find the final artifact:

```bash
mas-ctl checkpoint list .mas/checkpoints
mas-ctl checkpoint show <checkpoint-path-from-list>
```

Version 2 includes the kernel, committed conversation, manifest content and
session lineage. The manifest hash is checked when resuming.

## Fork and resume

Fork the final checkpoint. The fork gets a distinct session identity and keeps
the conversation that existed at the selected checkpoint:

```bash
mas-ctl checkpoint fork <checkpoint-path-from-list> \
  --output-dir .mas/forks --session-id experiment-a
mas-ctl chat --load-checkpoint <fork-checkpoint-path-printed-by-fork>
```

Continue the conversation in the fork, then fork again from the same source.
Each controller owns a separate working-memory registry; changes in one branch
are not visible in its sibling.

## What a checkpoint actually is

Two stores implement one `CheckpointStore` protocol
(`ctl/src/mas/ctl/adapters/checkpoint.py`):

| Store | Backs | Survives process exit |
| --- | --- | --- |
| `JsonCheckpointStore` | `--checkpoint-dir`, `--save-checkpoint`, `checkpoint fork` | Yes — one `*.checkpoint.json` file per checkpoint |
| `InMemoryCheckpointStore` | `/backtrack`, pause/inspect snapshots | No — process-local, for walking recent turns without disk I/O |

Either store accepts a raw kernel snapshot and wraps it as `version: 1`
(`kernel`, `memory_seeds`, `turn`); a snapshot that already carries
`version: 2` — kernel, committed conversation, manifest content, session
lineage — is written through unchanged. That is what `--save-checkpoint`
produces, and what [Tutorial 13](../13-control-and-debug/)'s control scripts
read directly.

`retain(session_id, mode, n)` prunes only that session's own files (matched
by filename prefix), so forking never ages out a sibling's history:
`single` keeps the latest checkpoint, `last_n` keeps the last `n`, `all`
keeps everything — this is the `spec.checkpoint.retention` block below.

## Recover manually

For automatic capture at every model response, apply the packaged `openclaw`
overlay or add this to the Agent manifest:

```yaml
spec:
  checkpoint:
    mode: every_turn
    retention:
      mode: last_n
      n: 5
```

In chat, return to the newest retained checkpoint and add a steering note:

```text
/backtrack 1 Explain what failed; do not repeat the same tool call.
```

Automatic repeated-error recovery is configured under `spec.governance`; see
[Session checkpoints](../../manifests/checkpoint.md) for the full policy and
cap behavior. Apply the packaged preset with:

```bash
mas-ctl chat docs/tutorials/01-building-an-agent/agent.yaml \
  -o pkg://mas.library.standard/overlays/openclaw.yaml
```

The captured artifact can become one comparison cell in an experiment's
starting-state axis; see the
[checkpoint-axis example](../../schemas/examples/checkpoint-axis.yaml).

`/steer` injects operator text. A paused session refuses the next user turn
until resume. In-memory snapshots are listed and walked through the same
control contract as pause; persist is a separate step.

## Reference material

- [Session checkpoints](../../manifests/checkpoint.md) — full policy,
  retention, and cap reference.
- [checkpoint-axis example](../../schemas/examples/checkpoint-axis.yaml) —
  using a checkpoint as an experiment starting-state axis.
- [Kernel operations](../../references/kernel-primitives.md) — where
  checkpoint/persist/steer sit among the runtime's primitive operations.
- Next: [Tutorial 13 — Control attach and debug](../13-control-and-debug/)
  attaches to a *live* session from another process by session id (the same
  id an A2A caller sees as `contextId`), and adds gdb-like governance
  breakpoints on top of the checkpoint mechanics from this tutorial.