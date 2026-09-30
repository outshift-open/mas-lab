# MCP compliance results

The compliance runner writes one JSON report directory per MCP requirement
revision:

```text
library-ioa/compliance/mcp/results/
├── 2025-11-25/
└── 2026-07-28/
```

Each revision contains one timestamped directory per official scenario. The
machine-readable checks are stored at:

```text
compliance/results/<revision>/server-<scenario>-<timestamp>/checks.json
```

Each check has a status such as `SUCCESS`, `FAILURE`, `SKIPPED`, or an
informational status. A compliance run passes only when the pinned runner exits
successfully for both required revisions and reports no required `FAILURE`.
Runner-owned extension and pending scenarios may be listed as not scored; they
remain in the artifact and must not be silently removed. Informational results
and warnings are evidence to review, not failures hidden by the wrapper.

The directory is intentionally ignored by Git. Reports are produced by
`library-ioa/compliance/mcp/mcp-conformance.sh` and uploaded by CI as:

- `mcp-compliance-${GITHUB_SHA}` for pull requests and branch runs;
- `mcp-compliance-${GITHUB_REF_NAME}` for version tags.

Release artifacts retain the reports for 90 days. The runner version is pinned
by `MCP_CONFORMANCE_VERSION` and defaults to
`@modelcontextprotocol/conformance@0.2.0-alpha.11`; update the version and
record the resulting compatibility changes in this file when the upstream
runner changes behavior.

A passing workflow requires both requirement revisions to complete successfully.
Runner-owned skips and informational warnings remain in the JSON output and
must be reviewed rather than silently discarded.

The tested revisions are MCP `2025-11-25` and `2026-07-28`. The runner is pinned
to `@modelcontextprotocol/conformance@0.2.0-alpha.11` by
`MCP_CONFORMANCE_VERSION`.

Pull-request and branch artifacts use a 30-day retention policy. Version-tag
release artifacts use a 90-day retention policy and are named
`mcp-compliance-${GITHUB_REF_NAME}`.
