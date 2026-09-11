# Agent Guidelines

## Core Principles

- **Verification:** Always run the `verify` task after completing any change.
- **No pre-existing failures:** Never leave lint, type, or test failures open — even if they
  predate your edit. Fix them in the same change set when you touch the file or discover them
  during review prep.
- **Remote Operations:** NEVER push to a remote repository without explicit approval from the user.
- **Commit Messages:**
    - Must be succinct and crisp.
    - Detail only implemented features in a bullet list.
    - Use a TLDR-style format.
    - **NEVER** write the literal string "TLDR" in the commit message.
- **Environment & Reproducibility:**
    - Always use `uv` in conjunction with the `direnv` environment.
    - Do not run manual `pip install` commands; instead, update the project's `pyproject.toml` or use `uv add` to ensure dependencies are captured and the environment remains reproducible.

## Task Completion Workflow

1. Implement the change.
2. Run `task verify`.
3. If verification passes, prepare the commit.
4. Draft the commit message following the guidelines above.
5. Request approval for the commit and subsequent push.
