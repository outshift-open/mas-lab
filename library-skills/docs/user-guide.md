<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# mas-library-skills User Guide

`mas-library-skills` implements the [Agent Skills specification](https://agentskills.io)
for MAS Lab.  It gives agents access to specialized, on-demand instructions
without loading everything into the context window upfront.

## Core concept — progressive disclosure

| Tier | What the model sees | When | Token cost |
|------|---------------------|------|------------|
| 1 — Catalog | Name + description of each skill | Session start (always) | ~50–100 per skill |
| 2 — Instructions | Full `SKILL.md` body | When model calls `activate_skill(name)` | <5000 (recommended) |
| 3 — Resources | Scripts, references, assets | When model calls `read_skill_file(skill, path)` | Varies |

The model sees the catalog from the start and knows which skills exist.
When it decides a skill matches the task, it loads the full instructions.
This keeps context small even with many skills installed.

---

## Step 1 — Write a SKILL.md

A skill is a directory containing a `SKILL.md` file:

```
skills/
└── answer-formatting/
    ├── SKILL.md            ← required
    ├── references/         ← optional: files loaded via read_skill_file
    └── scripts/            ← optional: scripts run via run_skill_script
```

The `SKILL.md` has YAML front matter and a Markdown body:

```markdown
---
name: answer-formatting
description: >
  Format every answer with a one-sentence summary, 2-3 bullet points,
  and a confidence indicator. Use when answering factual questions.
tags: [formatting, qa]
---
# Answer Formatting

## Rules

1. Start with a **one-sentence summary**.
2. Follow with **2-3 bullet points** of supporting detail.
3. End with a confidence indicator: HIGH / MEDIUM / LOW.
```

Required front matter fields:
- `name` — must match the directory name (warning if not, still loaded)
- `description` — shown to the model in the catalog; essential for model-driven activation

---

## Step 2 — Reference the skill in the agent manifest

```yaml
spec:
  skills:
    - answer-formatting      # relative to the manifest directory
```

The runtime searches for `SKILL.md` in:
1. `<manifest_dir>/answer-formatting/SKILL.md`
2. `<manifest_dir>/skills/answer-formatting/SKILL.md`
3. Walking up to the nearest `skills/` directory (library-level shared skills)

---

## Step 3 — Add the skill-access tools

The model needs tools to load skill instructions.  Add the skill-access tool
provider to `spec.tools`:

```yaml
spec:
  tools:
    - ref: skills:tools/skill-access.tool.yaml
```

Or use the convenience overlay — the base manifest never changes:

```bash
mas-ctl chat agent.yaml \
  -o skills:overlays/skills.yaml \
  -q "What is the speed of light?"
```

---

## What the model receives

**Session start (tier 1):**

```
## Available Skills

When a task matches a skill's description, call `activate_skill(name)` to load
its full instructions before proceeding.

- **answer-formatting**: Format every answer with a one-sentence summary, ...
```

**After calling `activate_skill("answer-formatting")` (tier 2):**

```xml
<skill_content name="answer-formatting">
# Answer Formatting

## Rules
...

<skill_resources>
  <file>references/examples.md</file>
</skill_resources>

Skill directory: /path/to/skills/answer-formatting
</skill_content>
```

---

## Available tools

### `activate_skill(name)`

Load the full `SKILL.md` body for a skill.  Returns the Markdown body (front
matter stripped) wrapped in `<skill_content>` tags, plus a listing of bundled
resource files.

```json
{"name": "answer-formatting"}
→ {"content": "<skill_content name=\"answer-formatting\">...", "skill": "...", "base_dir": "..."}
```

### `list_skill_files(skill)`

List all files in a skill's directory (except `SKILL.md` itself).

```json
{"skill": "answer-formatting"}
→ {"files": ["references/examples.md"], "base_dir": "..."}
```

### `read_skill_file(skill, path)`

Read a specific file from the skill's directory.  Path is relative to the skill
directory.  Access is sandboxed — paths that escape the directory are rejected.

```json
{"skill": "answer-formatting", "path": "references/examples.md"}
→ {"content": "# Examples\n...", "skill": "...", "path": "..."}
```

---

## Shell tool (optional — trusted environments only)

`run_skill_script` executes scripts from a skill's `scripts/` directory.

```yaml
spec:
  tools:
    - ref: pkg://skills/tools/run-skill-script.tool.yaml
```

Or use the shell overlay:

```bash
mas-ctl chat agent.yaml \
  -o skills:overlays/skills-shell.yaml \
  -q "Analyse this data"
```

⚠️ Only enable in trusted environments where skill scripts have been reviewed.
The subprocess runs with the agent process's OS-level permissions.

To grant it to every skill-declaring agent in a deployment without hand-listing
the tool ref on each one, opt in per-deployment instead:

```yaml
spec:
  context_sources:
    - native:
        auto_inject: true
```

---

## Overlays reference

| Overlay | What it adds |
|---------|-------------|
| `skills:overlays/skills.yaml` | `activate_skill`, `list_skill_files`, `read_skill_file` |
| `skills:overlays/skills-shell.yaml` | Above + `run_skill_script` |

---

## Quickstart example

See `examples/quickstart/` for a self-contained runnable example that demonstrates
the before/after effect of adding a skill overlay.
