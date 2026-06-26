<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Deployments

**`local-inproc.yaml`** — default in-process run with `spec.runtime_id: python-v2`.

Referenced from `mas-workspace.yaml` (`mas_ctl.deployment: local-inproc`) and copied into tutorial bundles under `deployments/`.

## Local Docker Compose

See [`docker/README.md`](../docker/README.md) for volume mounts, env vars, and one-off commands.

## CI images

Container images are built via `.github/workflows/build-push-ghcr.yaml`.
