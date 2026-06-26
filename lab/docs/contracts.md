# Lab contracts

## CLI commands

| Command | Purpose |
|---------|---------|
| `check` | Structural validation of `mas.yaml` and manifest tree |
| `check-config` | Config hygiene (model/access placement) |
| `benchmark run` | End-to-end experiment execution (scenarios from lab `datasets/`) |

Smoke / scenario execution is **only** through the benchmark pipeline and golden runs — not embedded `test_knowledge` in MAS specs.
