# SRE Incident Triage

Canonical app path: **`apps/sre-triage/`** (single source of truth).

Multi-agent incident triage: SRE orchestrator delegates to telemetry, backend, DB,
comms, and verifier, then executes a verified remediation via `run_action`.

## Quick start (no overlay)

The bare `mas.yaml` is the **baseline** — default incident fixture, all agent skills,
and tools work without `-o`:

```bash
cd mas-lab-internal
mas-ctl run-mas apps/sre-triage/mas.yaml \
  -q "Payment service P99 latency spiked to 4.2s. Checkout conversion dropped 40%. Started 15 minutes ago."
```

Tools resolve `datasets/incidents/payment-async-timeout.yaml` by default
(see `tools/_scene.py`). Overlays only **improve** or **degrade** the baseline:

| Overlay | Effect |
|---------|--------|
| *(none)* | Baseline — full agent manifests as shipped |
| `overlays/full.yaml` | Extra skill routing list (enhanced) |
| `overlays/degraded.yaml` | Skills disabled (IoC challenge / naive mode) |
| `overlays/robust.yaml` | IoC constraint metadata (experimental; may require `--no-validate`) |

Historical v1 manifests live under `apps/old/sre-triage-v1/` for reference only.
