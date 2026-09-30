<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# System tools reference

This page lists every system tool implemented in MAS-Lab. For the rules that
enable each tool, see [System tools](../manifests/system-tools.md).

| Tool | Package | Enablement | Declaration aliases |
| --- | --- | --- | --- |
| [`activate_skill`](#activate_skill) | `mas-library-skills` | implicit (`spec.skills`) or declared | `skill-access`, `skill_access` |
| [`list_skill_files`](#list_skill_files) | `mas-library-skills` | with `activate_skill` | — |
| [`read_skill_file`](#read_skill_file) | `mas-library-skills` | with `activate_skill` | — |
| [`run_skill_script`](#run_skill_script) | `mas-library-skills` | implicit (skill `scripts/`, `auto_inject`) or declared | `run-skill-script` |
| [`request_human_input`](#request_human_input) | `mas-runtime` | declared only | — |
| [`inform_user`](#inform_user) | `mas-runtime` | declared only | — |

The skill tools require `mas-library-skills`. Without it, declaring one fails
with an unknown system tool error.

## Skill tools

### `activate_skill`

Loads the full `SKILL.md` body of a catalog skill. Frontmatter is removed from
the returned body, and bundled resources are listed.

| Argument | Type | Required | Notes |
| --- | --- | --- | --- |
| `name` | string | yes | Constrained to registered skill names. Names already activated are dropped from the enum. |

Implementation: `mas.library.skills.plugins.sk_tools.SkillToolsPlugin`.

### `list_skill_files`

Lists the files in a skill directory, such as references, scripts, and assets.

| Argument | Type | Required |
| --- | --- | --- |
| `skill` | string | yes |

### `read_skill_file`

Reads one file from a skill directory.

| Argument | Type | Required | Notes |
| --- | --- | --- | --- |
| `skill` | string | yes | |
| `path` | string | yes | Relative to the skill directory, such as `references/rules.md` |

### `run_skill_script`

Runs a script from the skill's `scripts/` directory with resource limits.
Returns `stdout`, `stderr`, and the exit code.

| Argument | Type | Required | Notes |
| --- | --- | --- | --- |
| `skill` | string | yes | |
| `script` | string | yes | Plain filename, no path |
| `args` | string[] | no | Positional arguments |
| `timeout` | integer | no | Seconds; default 30, maximum 120 |
| `env` | object | no | Extra variables. Loader-control variables such as `PATH` and `LD_PRELOAD` are rejected. |
| `stdin` | string | no | Text sent to the script's standard input |

Implementation: `mas.library.skills.plugins.sk_shell.RunSkillScriptPlugin`.

## User-communication tools

### `request_human_input`

Asks the user a question and **blocks the agent's turn** until the question is
resolved through the HITL side channel. The channel is an `HITLContract`, or
the HITL resolver registry if no contract is provided.

| Argument | Type | Required | Notes |
| --- | --- | --- | --- |
| `question` | string | yes | Up to `max_question_length` characters |
| `question_type` | string | no | `CONFIRM` (default), `FREE_FORM`, `MULTIPLE_CHOICE`, `MULTI_SELECT`, `FORM` |
| `choices` | string[] | no | Options for `MULTIPLE_CHOICE` and `MULTI_SELECT` questions |
| `context_data` | object | no | Data displayed with the question |
| `timeout` | number | no | Overrides the manifest default for one call |

| Manifest `params` | Default | Notes |
| --- | --- | --- |
| `timeout` | none (wait indefinitely) | Default timeout for each call, in seconds |
| `auto_resolve_decision` | `approve` | Answer used when the host runs unattended (`mas-ctl run-mas` with auto-HITL, benchmarks). |
| `max_question_length` | 20000 | Also sets the schema advertised to the model |

Implementation: `mas.runtime.system_tools.RequestHumanInputTool`.

### `inform_user`

Sends a **non-blocking** progress update. The call returns immediately and the
agent continues.

| Argument | Type | Required | Notes |
| --- | --- | --- | --- |
| `message` | string | yes | Up to `max_message_length` characters |
| `user_name` | string | no | |
| `involved_agents` | string[] | no | |
| `metadata` | object | no | |

| Manifest `params` | Default | Notes |
| --- | --- | --- |
| `max_message_length` | 20000 | Also sets the schema advertised to the model |

The update is delivered through a `UserIOContract` or, if none is provided,
the HITL resolver registry.

Implementation: `mas.runtime.system_tools.InformUserTool`.
