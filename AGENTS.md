# Agent Guidelines

Harness-agnostic. Cursor, Claude Code, Codex, and Copilot should all follow this
file. If a `.agents/` directory exists in this working copy (intentionally
untracked; see `.gitignore` comment), follow `.agents/README.md` as well.

## Core Principles

- **Verification:** Always run the `verify` task after completing any change.
- **No pre-existing failures:** Never leave lint, type, or test failures open — even if they
  predate your edit. Fix them in the same change set when you touch the file or discover them
  during review prep.
- **Remote Operations:** NEVER push to a remote repository without explicit approval from the user.
- **Commit Messages:**
    - One `type(scope): subject` line, then a concise bullet list of
      implemented features only — the same shape as merged PRs.
    - Each bullet is one short action (one line; wrap a second only for a
      trailing clause). No design essays, no rationale paragraphs.
    - Example:
      ```
      feat(runtime): engine retries, typed failures, and library plugins

      - Retry LLM HTTP (sync and async) on transient and unavailable failures
      - Reattempt failed lab runs up to execution.max_attempts (default 3)
      - Move plugin implementations into the library, selected by spec name
      ```
    - Never write the literal string "TLDR" in the commit message.
    - Sign off with `git commit -s`. Do not copy `Signed-off-by` from cherry-picks.
- **Environment & Reproducibility:**
    - Always use `uv` in conjunction with the `direnv` environment.
    - Do not run manual `pip install` commands; instead, update the project's `pyproject.toml` or use `uv add` to ensure dependencies are captured and the environment remains reproducible.

## Documentation map

Do **not** add a new YAML-kind page for runtime behaviour.

| Reader question | Put it here |
|-----------------|-------------|
| What is this YAML `kind`? (`Agent`, `MAS`, `Overlay`, …) | `docs/manifests/<kind>.md` |
| Field companion of Agent that is not a kind (`spec.governance`) | Nested under Agent, e.g. `docs/manifests/governance.md` |
| Runtime behaviour spanning several fields (retries, circuit, logging) | `docs/references/` — e.g. [reliability.md](docs/references/reliability.md) |
| Plugin card | Next to the plugin, `library-*/…/<plugin>.md` |
| Dev contract | `runtime/docs/dev/contracts/` |

One full reference per topic. Other pages **point**; they do not copy default
tables or examples. MkDocs nav must match: kinds under Specifications, behaviour
under Runtime.

User-facing docs go through `mkdocs.yml`. After doc edits, `task verify-docs`.

## Tests and coverage

- Targeted: `uv run pytest <paths> --tb=short` (package `.venv`, not system
  `pytest`).
- Pre-commit gate: `task verify` (`verify-unit` + docs + smoke; see `Taskfile.yml`).
- Coverage config is `[tool.coverage.*]` in `pyproject.toml` (`fail_under = 90`
  on the listed packages). New runtime behaviour needs tests next to the code
  (`runtime/tests/`, `library-standard/tests/`, …).

## Feature branches

- Name `feat/<topic>` or `fix/<topic>`, not plan numbers, once the work is
  meant to merge.
- Feature branches should be squashed into 1 single commit and rebase on
  remote main also pulled and synced locally.
- Before review: `git fetch origin` so remote `main` is current, update the
  local `main` checkout to that tip, then `git rebase origin/main` in the
  feature worktree. Do not merge.
- The PR is that one commit. Amend only while HEAD is ours and unpushed.
  Commit body is a concise bullet list of implemented features only
  (one short action per bullet, matching merged PRs). Never write "TLDR".
  `git commit -s`.
- Do not copy work into a dirty checkout of the same repo. Do not push or open
  a PR unless asked.

## Task Completion Workflow

1. Implement the change.
2. Run `task verify` (or a documented subset plus `task verify-docs` when only
   docs moved).
3. If verification passes, prepare the commit.
4. Draft the commit message following the guidelines above.
5. Request approval for the commit and subsequent push.
