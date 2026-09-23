<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# `mas-ctl` command-line reference

Complete flags for **`mas-ctl`**. `mas-ctl COMMAND --help` is always authoritative
if this page and the code diverge.

Related: [CLI overview](index.md) · [config.yaml](../references/config.yaml.md) ·
[observability (`events.jsonl`)](observability.md) · [TUI](../ctl/tui.md).

---

## Global flags

Apply before the subcommand:

```bash
mas-ctl [-v] [--env FILE] COMMAND …
```

| Flag | Default | Effect |
|------|---------|--------|
| `-v` / `--verbose` | off | Repeatable. `-v` session hints / extra logs; `-vv` also enables `--trace-engine` when tracing |
| `--env FILE` | workspace `mas_ctl.env` (default `.env`) | Load that dotenv file |

---

## Outputs

| Destination | What | Enable |
|-------------|------|--------|
| **stdout** | Conversation (`You:` / `Agent:`) | Always for `chat` / `run-mas` |
| **stderr** | Human exchange log (AGENT↔LLM↔TOOL) | `--trace` or `mas_ctl.trace` |
| **`events.jsonl`** | Machine run log | `--events` / overlay / manifest — [observability.md](observability.md) |

Stdout stays the conversation. Color is never the default (`--trace-color`).

### Precedence (exchange log)

1. CLI (`--trace`, `--no-trace`, `--trace-color`, …)
2. Workspace `config.yaml` `mas_ctl:`
3. User `$XDG_CONFIG_HOME/mas/config.yaml` `mas_ctl:`
4. Built-in: off until `--trace` or config enables it; then **summary + timestamps**, color off

---

## `mas-ctl chat [MANIFEST]`

Interactive or scripted single-agent session. Manifest defaults to `agent.yaml`
when omitted (cwd / workspace walk).

```bash
mas-ctl chat agent.yaml -q "What is 2+2?"
mas-ctl chat agent.yaml -i -o overlays/tools.yaml --trace
```

### Session

| Flag | Default | Effect |
|------|---------|--------|
| `-p` / `--prompt TEXT` | — | First user turn |
| `-q` / `--query TEXT` | — | Extra turn(s); repeatable |
| `-i` / `--interactive` · `-I` / `--no-interactive` | TTY and no scripted turns | Multi-turn REPL |
| `--single-turn` | off | Exit after the first agent reply |

### Manifest / overlays

| Flag | Default | Effect |
|------|---------|--------|
| `-o` / `--overlay PATH` | — | Overlay YAML; repeatable |
| `--tool NAME` | — | Inline overlay: add a tool by name |
| `--skill NAME` | — | Inline overlay: add a skill by name |
| `--memory ID` | — | Inline overlay: memory backend id |
| `--set KEY=VALUE` | — | Inline overlay: `spec.context` |
| `--pattern ID` | manifest | Design-pattern plugin id |
| `--flavour NAME` | `local` | Flavour from library-standard |
| `--infra-ref REF` | workspace / user | Infra bundle; repeatable; wins over `config.yaml` |
| `--runtime-ref REF` | workspace / user | `RuntimeEngine` ref; repeatable |
| `--model ID` | spec.models / `MAS_CTL_MODEL` / `MAS_LLM_MODEL` | Force the engine model for this run |
| `--no-validate` | off | Skip schema checks for seeds/checkpoints |

### Cache, stream, envelope

| Flag | Default | Effect |
|------|---------|--------|
| `--cache-read` / `--no-cache-read` | RuntimeEngine / `MAS_LLM_CACHE_READ` / true | Lookup before the LLM call |
| `--cache-write` / `--no-cache-write` | RuntimeEngine / `MAS_LLM_CACHE_WRITE` / true | Persist after the LLM call |
| `--stream` / `--no-stream` | RuntimeEngine / `MAS_LLM_STREAM` / false | SSE streaming |
| `--without-obs` | off | Disable observability summand (`M_obs`) and event recording |
| `--without-gov` | off | Disable governance summand (`M_gov`) and HITL chokepoints |

### Checkpoints / memory seed

| Flag | Default | Effect |
|------|---------|--------|
| `--memory-seed PATH` | — | Seed working / persistent memory |
| `--checkpoint-dir PATH` | — | Checkpoint directory |
| `--load-checkpoint PATH` | — | Restore a checkpoint |
| `--save-checkpoint` / `--no-save-checkpoint` | off | Save after each turn |

### Exchange log

Shared with `run-mas`. **Not** on `tui` (curses has its own pane).

| Flag | Default when tracing | Effect |
|------|----------------------|--------|
| `--trace` / `--trace summary` | — | Enable human summary: headers + timestamps; untruncated AGENT→USER |
| `--trace full` / `--trace-full` | — | Verbose payload dump (legacy `--trace` behaviour) |
| `--trace-summary` | — | Alias for `--trace` / `--trace summary` |
| `--no-trace` | — | Off even if `config.yaml` sets `mas_ctl.trace` |
| `--trace-timestamps` / `--no-trace-timestamps` | timestamps **on** | UTC + elapsed per exchange |
| `--trace-color` / `--no-trace-color` | **off** | ANSI color; never implied by `--trace` |
| `--trace-engine` | off (also `-vv`) | Raw `InvokeEngineIo` / `EngineIoReturn` JSON |

Workspace / user `config.yaml`:

```yaml
mas_ctl:
  trace: summary          # off | summary | full  (true = summary)
  # trace_timestamps: true
  # trace_color: false
  # trace_engine: false
```

Field reference: [config.yaml](../references/config.yaml.md#mas_ctl).

### `events.jsonl` (`--events*`)

Shared with `run-mas` and `tui`. Full semantics: [observability.md](observability.md).

| Flag | Effect |
|------|--------|
| `--events` / `--no-events` | Force native observability on or off |
| `--events-file PATH` | JSONL path (default `traces/events.jsonl`) |
| `--events-stderr` / `--events-stdout` | Also stream JSONL on **stderr** (`--events-stdout` is a legacy alias) |
| `--events-format` | `native` · `boundary` · `both` · `otel` |

---

## `mas-ctl run-mas [MANIFEST]`

Compose → materialize → session on the MAS entry agent. Manifest defaults to
`mas.yaml`.

```bash
mas-ctl run-mas mas.yaml -q "Plan a trip from Celestia to Verdantia" --trace
```

| Flag | Default | Effect |
|------|---------|--------|
| `-p` / `--prompt TEXT` | — | First user turn |
| `-q` / `--query TEXT` | — | Extra turn(s); repeatable |
| `-o` / `--overlay PATH` | — | Overlay YAML; repeatable |
| `-d` / `--deployment PATH` | workspace `mas_ctl.deployment` | Deployment manifest |
| `--flavour NAME` | `local` | Flavour |
| `--infra-ref REF` | — | Infra bundle; repeatable |
| `--kernel ID` | package default | Runtime / kernel id |
| `-i` / `--interactive` | off | Interactive session |
| `--auto-hitl` / `--no-auto-hitl` | auto-hitl **on** | Batch auto-resolve HITL; `--no-auto-hitl` uses OperatorConsole |
| `--single-turn` | off | Exit after first reply |
| `--no-validate` | off | Skip manifest validation |

Plus the shared **`--trace*`** and **`--events*`** tables above.

---

## `mas-ctl tui [MANIFEST]`

Curses UI with the same bootstrap as `chat` (overlays, infra, HITL, `--events*`).
No `--trace` (the TUI renders exchanges itself).

| Flag | Default | Effect |
|------|---------|--------|
| `-o` / `--overlay PATH` | — | Overlay YAML; repeatable |
| `--pattern ID` | manifest | Design-pattern plugin id |
| `--flavour NAME` | `local` | Flavour |
| `--single-turn` | off | Exit after first reply |
| `--memory-seed PATH` | — | Memory seed |
| `--infra-ref` / `--infra REF` | — | Infra bundle; repeatable |
| `--runtime-ref REF` | — | RuntimeEngine ref; repeatable |
| `--no-validate` | off | Skip schema checks |
| `--model ID` | spec.models / `MAS_CTL_MODEL` / `MAS_LLM_MODEL` | Force the engine model |

Plus **`--events*`**. Guide: [ctl/tui.md](../ctl/tui.md).

---

## Other commands

| Command | Purpose | Typical flags |
|---------|---------|---------------|
| `mas-ctl validate PATH …` | Schema-check manifests | `-k/--kind`, `--strict/--no-strict`, `--no-validate`, `--resolve-refs/--no-resolve-refs`, `-o/--overlay` |
| `mas-ctl schemas` | List bundled JSON/YAML schemas | — |
| `mas-ctl compose MANIFEST` | Effective bind + placement plan | `-d/--deployment`, `-o/--overlay`, `--infra-ref`, `--runtime-ref`, `--kernel`, `-O/--output`, `--no-validate` |
| `mas-ctl plan MANIFEST` | Placement plan only | `-d/--deployment`, `--kernel`, `--no-validate` |
| `mas-ctl flavour list` | Flavours from installed libraries | — |
| `mas-ctl infra list` | Infra bundles | `-v` |
| `mas-ctl list-bundles` | All library bundles | — |
| `mas-ctl registry …` | Plugin registry introspection | `mas-ctl registry --help` |
| `mas-ctl checkpoint list DIR` | List checkpoint files | — |
| `mas-ctl checkpoint show PATH` | Print one checkpoint JSON | — |

---

## Interactive `chat` commands

At the `You:` prompt (see `mas-ctl chat --help` epilog):

| Input | Effect |
|-------|--------|
| `/quit` `/exit` `/q` | End the session |
| `/reset` | Clear working memory and turn history |
| `/steer TEXT` | Inject operator steering |
| `/skills` · `/skill NAME` | List / activate skills |

HITL (when `spec.governance.hitl_on_tool` is set): interactive mode prompts
SCHEDULE / BLOCK / SKIP on stderr. Batch `-q` auto-approves unless the overlay
sets `hitl_mode: auto-deny`.
