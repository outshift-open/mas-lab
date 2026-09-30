---
date: 2026-09-30
slug: v0-2-release
authors:
  - mas.team
categories:
  - Releases
---

# MAS-Lab v0.2: Protocols at the Infrastructure Boundary

The v0.2 release grew out of a practical question: how do we add remote tools
and agent-to-agent communication without turning protocol details into every
agent's business logic? The answer in MAS-Lab is to keep those concerns at the
infrastructure boundary, where they can be configured, tested, and replaced
without rewriting the workflow.

<!-- more -->

## MCP and A2A without rewriting agents

`library-ioa` now provides the integration surface for MCP and A2A. MCP tools
can be served or invoked through the `mas-mcp` CLI and the MCP bridge. A2A
exposes agents and delegation through `mas-ctl serve --protocol a2a` and the
A2A client commands. The same agent specification can therefore be exercised
locally or through a remote protocol adapter.

The release also includes the agentskills.io-compatible skill layer in
`library-skills`, structured human approval and user communication boundaries,
and stronger manifest compilation, validation, registry, and overlay checks.

## What the conformance numbers mean

The release measurements separate executed tests from specification coverage.
The official MCP conformance suite measured `92.9%` of required checks for
revision `2025-11-25` and `98.3%` for the newer, stricter stateless revision
`2026-07-28`.

A deterministic A2A fixture was tested independently of LLM output across
JSON-RPC, HTTP+JSON, and gRPC. It passed `99/99` executed requirements, a
`100%` executed-test pass rate. The official TCK maps `79.8%` of the A2A
specification; `25` requirements were not exercised because the TCK currently
provides no mapped tests for them. The partial conformance figure is therefore
a limitation of test coverage, not a claim that those implemented areas fail.

## Start with Docker or the source tree

The Python packages are not yet published to PyPI. The public quickstart uses
the Docker path, which builds the CLI and controller from the repository:

```bash
git clone https://github.com/outshift-open/mas-lab.git
cd mas-lab
cd docker
cp .env.example .env
docker compose --profile tools build backend
docker compose --profile tools run --rm --no-deps cli \
  mas-ctl validate docs/tutorials/01-building-an-agent/agent.yaml
```

Developers working on the runtime can use the `uv` and `task` workflow described
in [Tutorial 0](../../../tutorials/00-environment-setup/README.md). The Web UI is
available through the Docker stack, and trajectory plots can be generated from
execution traces with `mas-lab plot trajectory`.

## What comes next

The next useful step is not another protocol adapter in the agent layer. It is
better release evidence around the adapters we already have: reproducible
conformance runs, retained reports, and clear boundaries between what a test
executes and what a specification formally covers.

The repository release notes contain the full compatibility and release
checklist. Continue with the
[MCP tutorial](../../../tutorials/04-mcp-tools/README.md) or the
[A2A tutorial](../../../tutorials/05-a2a-agents/README.md).
