# mas-library-skills

Agent Skills support for MAS Lab — progressive disclosure via `ContextContract` + `ToolContract`.

## What it provides

| Component | Kind | Description |
|-----------|------|-------------|
| `SkillCatalogPlugin` | `ContextContract` | Injects skill catalog (name + description) into `SYSTEM_SKILLS` band |
| `SkillToolsPlugin` | `ToolContract` | `activate_skill`, `list_skill_files`, `read_skill_file` |
| `RunSkillScriptPlugin` | `ToolContract` | `run_skill_script` — executes scripts in `scripts/` |
| `ContextPart.skills()` | runtime shorthand | `ContextPart` constructor for `SYSTEM_SKILLS` placement |
| `PluginCollection` | runtime utility | `collect_results()` dispatch matching `ContextAssemblerPlugin` interface |

## Install

```bash
uv add mas-library-skills
```

The base install gives you the native implementation only (`agentskills` +
`skill-sandbox`, both plain local dependencies — no extra to opt into). The
ADK and LangChain implementations wrap real, optional third-party
frameworks; pull them in with:

```bash
uv add "mas-library-skills[all]"
```

`task install-dev` / `task ci` / `task verify` in this repo already install
the `[all]` extra, so the full test suite (including
`tests/test_skill_plugins_functional.py`, which exercises the real
frameworks rather than mocks) runs by default — no separate opt-in step.

## Quick start

```yaml
# agent.yaml
apiVersion: mas/v1
kind: Agent
metadata:
  name: my-agent
spec:
  models:
    - model: gpt-4o-mini
  context:
    role: "Answer questions helpfully."
  skills:
    - answer-formatting          # points to ./skills/answer-formatting/SKILL.md
  tools:
    - ref: skills:tools/skill-access.tool.yaml
```

`spec.skills` is a single flat list — the only place a manifest declares
which skills an agent has. There is no separate `context_manager.skills`
path: skills aren't an attribute of the context-manager plugin (which
just picks a context-window strategy — stack, sliding-window, etc.),
they're their own concept, read directly off `spec.skills` by whichever
plugins care about it (the catalog and tools plugins below). Each entry is
either a bare name (resolved via the standard locator chain: app-local
`skills/` → declared libraries → installed packages) or `@library/name`
for an explicit source.

Run:

```bash
mas-ctl chat agent.yaml -q "What is the speed of light?"
```

Or add skills via overlay — the base manifest never changes:

```bash
mas-ctl chat agent.yaml \
  -o skills:overlays/skills.yaml \
  -q "What is the speed of light?"
```

## Choosing an implementation

Skills aren't a manifest-level contract of their own — `spec.skills` just
supplies *content* (which skills exist), and that content is served to the
agent by two ordinary plugins, each satisfying a pre-existing runtime
contract:

| Plugin | Contract | Role |
|--------|----------|------|
| `SkillCatalogPlugin` | `ContextContract` | Injects the tier-1 catalog (name + description) into `SYSTEM_SKILLS` |
| `SkillToolsPlugin` | `ToolContract` | `activate_skill` / `list_skill_files` / `read_skill_file` (tiers 2-3) |

Underneath those two, there are three interchangeable *engines* — which
framework actually does discovery, frontmatter parsing, and script
execution:

| Engine | Framework wrapped | Sandboxing | Notes |
|--------|--------------------|------------|-------|
| **native** (default) | `agentskills` + `skill-sandbox` | POSIX rlimits (CPU, memory, wall clock) | Zero glue code — the right default for MAS Lab. |
| **adk** | `google.adk.skills` (`google-adk`) | none (delegated to ADK) | Richest native delegation — resources loaded eagerly in-memory. |
| **langchain** | `deepagents` (LangGraph agent harness) | none (delegated to deepagents) | ~70 lines of adapter glue, since deepagents is tool-call-oriented rather than exposing a plain "give me the skill body" API. |

`SkillPluginRegistry(impl="native" | "adk" | "langchain")` selects the
engine and dynamically imports the matching `plugin_skills_*.py` module —
see `docs/developer-guide.md` for the full interface and
`examples/skill_plugin_comparison.py` for a side-by-side comparison.

Per-deployment `impl` selection is wired end-to-end through bootstrap:
overlay/manifest tool entries can set `impl` (`native` / `adk` /
`langchain`) and optional `base_dir`, and bootstrap propagates that
selection to both catalog injection and skill tool execution.

See `docs/user-guide.md` for the full guide, `examples/quickstart/` for a runnable example, and `docs/spec-coverage.md` for the agentskills.io specification coverage matrix.
