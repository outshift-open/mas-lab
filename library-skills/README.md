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

The base install includes the bundled agentskills.io parser and skill sandbox;
no separate PyPI package is required. The
ADK and LangChain implementations wrap real, optional third-party
frameworks; pull in one or both:

```bash
uv add "mas-library-skills[adk]"        # google-adk
uv add "mas-library-skills[langchain]"  # deepagents
uv add "mas-library-skills[all]"        # both
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
| **native** (default) | bundled `agentskills` + script runner | Best-effort environment filtering, timeout, and POSIX rlimits | Useful for cooperative local scripts; not a security sandbox. |
| **adk** | `google.adk.skills` (`google-adk`) | none (delegated to ADK) | Richest native delegation — resources loaded eagerly in-memory. |
| **langchain** | `deepagents` (LangGraph agent harness) | none (delegated to deepagents) | ~70 lines of adapter glue, since deepagents is tool-call-oriented rather than exposing a plain "give me the skill body" API. |

### Security boundary

The native script runner is not a security boundary. It runs a local subprocess
with a filtered environment, a timeout, and best-effort CPU/address-space limits.
It does not provide filesystem isolation, network isolation, a container boundary,
or a complete syscall policy. Do not execute untrusted skill code with it. A
real sandboxed backend is planned for a future implementation; until then, use
Docker or another externally enforced isolation boundary for untrusted scripts.

`SkillPluginRegistry(impl="native" | "adk" | "langchain")` selects the
engine and dynamically imports the matching `plugin_skills_*.py` module —
see `docs/developer-guide.md` for the full interface and
`library-skills/tests/test_skill_plugins_functional.py` and `examples/quickstart/` for runnable comparisons.

Per-deployment `impl` selection is wired end-to-end through bootstrap:
overlay/manifest tool entries can set `impl` (`native` / `adk` /
`langchain`) and optional `base_dir`, and bootstrap propagates that
selection to both catalog injection and skill tool execution.

See `docs/user-guide.md` for the full guide, `examples/quickstart/` for a runnable example, and `docs/spec-coverage.md` for the agentskills.io specification coverage matrix.
