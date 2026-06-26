#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
# MAS Lab tooling image — controller API, benchmarks, and agent runtime CLIs.
FROM python:3.12-bookworm

ENV MAS_INSTALL_ROOT=/opt/mas-lab
WORKDIR ${MAS_INSTALL_ROOT}

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

# Workspace metadata first (layer cache)
COPY pyproject.toml ./
COPY runtime/pyproject.toml runtime/
COPY ctl/pyproject.toml ctl/
COPY library-standard/pyproject.toml library-standard/
COPY library-samples/pyproject.toml library-samples/
COPY library-lab/pyproject.toml library-lab/
COPY library-eval/pyproject.toml library-eval/
COPY lab/pyproject.toml lab/
COPY lab/components/core/pyproject.toml lab/components/core/
COPY lab/components/bench/pyproject.toml lab/components/bench/
COPY lab/components/controller/pyproject.toml lab/components/controller/
COPY lab/components/content/pyproject.toml lab/components/content/

# Source trees
COPY runtime/ runtime/
COPY ctl/ ctl/
COPY library-standard/ library-standard/
COPY library-samples/ library-samples/
COPY library-lab/ library-lab/
COPY library-eval/ library-eval/
COPY lab/ lab/

# Default workspace content (overridden when /workspace is mounted)
COPY examples/sample-workspace/mas-workspace.yaml ./mas-workspace.yaml
COPY labs/ labs/
COPY docs/tutorials/ docs/tutorials/

ENV MAS_WORKSPACE_ROOT=/workspace
ENV MAS_DATA_ROOT=/data
ENV MAS_CONTROLLER_PORT=8090
ENV PYTHONUNBUFFERED=1

RUN uv sync --no-dev

COPY docker/backend/entrypoint.sh /usr/local/bin/mas-lab-entrypoint
RUN chmod +x /usr/local/bin/mas-lab-entrypoint

WORKDIR /workspace

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/api/health')"

ENTRYPOINT ["/usr/local/bin/mas-lab-entrypoint"]
CMD ["controller"]
