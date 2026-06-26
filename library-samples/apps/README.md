# Trip planner sample app

The registry id **`trip-planner`** resolves to `apps/trip-planner/` — the canonical four-agent Arborian Network MAS (moderator coordinates specialists). Use `app: trip-planner` in experiment YAML.

**Topology and design-pattern variants** (linear pipeline, parallel, single-agent, CoT, ReAct, …) are **not** separate app folders. They live as overlays under `labs/` (e.g. `labs/design-space.lab/02-topologies/overlays/`) or as local overlays under `apps/trip-planner/overlays/`.

Shared tools also live under `library-samples/tools/`; the app folder may ship app-local `tools/`.
