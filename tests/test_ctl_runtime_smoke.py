#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Ctl → runtime smoke — compose path resolves and kernel runs without LLM."""

from pathlib import Path

from mas.runtime.driver.instance import RuntimeInstance
from mas.runtime.engine.simulated import SimulatedEngine
from mas.runtime.schema.ingress import EngineIoReturn


def test_runtime_instance_end_to_end_smoke():
    engine = SimulatedEngine(
        script={
            1: EngineIoReturn(
                correlation_id=1,
                response_kind="MODEL_TEXT",
                next_step="STOP",
                text="smoke ok",
            )
        }
    )
    inst = RuntimeInstance.from_parts(engine=engine)
    trace = inst.run_user_text("ping")
    assert trace.client_responses or trace.steps


def test_workspace_infra_refs_from_sample_workspace():
    from mas.ctl.infra.resolve import resolve_infra_refs
    from mas.ctl.workspace.config import WorkspaceConfig

    repo = Path(__file__).resolve().parents[1]
    sample = repo / "examples" / "sample-workspace"
    assert (sample / "config.yaml").is_file()
    ws = WorkspaceConfig.load(repo / "docs/tutorials/01-building-an-agent")
    assert ws.found
    infra = resolve_infra_refs(["standard:mock-llm"], anchor=repo, workspace=ws)
    assert infra.llm_proxy.get("provider") == "mock" or "mock" in str(infra.refs).lower()
