#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
RESULTS_DIR="${MCP_CONFORMANCE_RESULTS:-${ROOT_DIR}/library-ioa/compliance/mcp/results}"
PYTHON="${MCP_CONFORMANCE_PYTHON:-${ROOT_DIR}/.venv/bin/python}"

mkdir -p "${RESULTS_DIR}"
cd "${ROOT_DIR}"

if [[ ! -x "${PYTHON}" ]]; then
	echo "Missing ${PYTHON}; install compliance dependencies first:" >&2
	echo "  uv venv .venv && uv pip install -e runtime -e library-ioa" >&2
	exit 1
fi

exec env \
	MCP_CONFORMANCE_HOST="${MCP_CONFORMANCE_HOST:-127.0.0.1}" \
	MCP_CONFORMANCE_PORT="${MCP_CONFORMANCE_PORT:-9002}" \
	MCP_CONFORMANCE_VERSION="${MCP_CONFORMANCE_VERSION:-0.2.0-alpha.11}" \
	MCP_CONFORMANCE_RESULTS="${RESULTS_DIR}" \
	"${PYTHON}" library-ioa/compliance/mcp/fixtures/mcp_conformance_server.py --run-conformance
