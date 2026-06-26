<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Contributing to MAS Lab

Thank you for your interest in contributing. This project is an Apache 2.0
open-source monorepo managed with [uv](https://docs.astral.sh/uv/).

## Getting started

```bash
git clone https://github.com/outshift-open/mas-lab.git
cd mas-lab
uv sync --all-packages
export PATH="$PWD/.venv/bin:$PATH"
```

Verify the install:

```bash
mas-runtime --help
mas-ctl --help
mas-lab --help
```

## Development workflow

1. Open an issue or comment on an existing one before large changes.
2. Create a feature branch from `main`.
3. Make focused changes with tests where behavior changes.
4. Run the relevant test suites before opening a PR.
5. Open a pull request with a clear description and test plan.

## Running tests

```bash
# Core packages
uv run pytest runtime/tests/ -v
uv run pytest ctl/tests/ -v
uv run pytest lab/tests/ -v
uv run pytest library-standard/tests/ -v

# Tutorial integration tests (optional, may require API keys)
uv run pytest tests/tutorials/ -v
```

## Code style

- Python 3.11+ with type hints where practical
- Line length: 120 (ruff)
- Match existing naming and module layout in each package
- Secrets belong in environment variables — never commit credentials

## Package layout

| Directory | Package |
| --- | --- |
| `runtime/` | `mas-runtime` |
| `ctl/` | `mas-ctl` |
| `library-standard/` | `mas-library-standard` |
| `lab/` | `mas-lab` (+ `mas-lab-core`, `mas-lab-bench` components) |

See [docs/developer-guide.md](docs/developer-guide.md) for architecture details.

## License

By contributing, you agree that your contributions will be licensed under the
Apache License 2.0. See [LICENSE](LICENSE).
