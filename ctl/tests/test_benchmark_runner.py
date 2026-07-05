#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Bench runner identity — stable runner_id for analytics."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mas.ctl.benchmark.runner import MasBenchRunner, select_mas_runner
from mas.ctl.executor.mas_session import agent_manifest_label
from mas.ctl.benchmark.runner_dispatch import is_mas_manifest_kind, mas_manifest_path
from mas.ctl.compose.models import AgentBindSlice, EffectiveBindManifest
from mas.ctl.compose.models import PlacementPlan
from mas.ctl.compose.runner import ComposeResult
from mas.lab.manifest.load import entry_agent_from_compose
from mas.lab.runners.constants import DEFAULT_LAB_RUNNER_ID
from mas.lab.runners.protocol import RunResult


def test_mas_bench_runner_id_is_mas_lab():
    assert MasBenchRunner.runner_id == DEFAULT_LAB_RUNNER_ID
    assert select_mas_runner().runner_id == DEFAULT_LAB_RUNNER_ID


def test_is_mas_manifest_kind_by_kind_not_filename(tmp_path: Path):
    triage = tmp_path / "triage.yaml"
    triage.write_text("kind: mas\n", encoding="utf-8")
    config = {"kind": "mas", "metadata": {"name": "triage"}}
    assert is_mas_manifest_kind(config, triage) is True
    assert mas_manifest_path(config, triage) == triage


def test_is_mas_manifest_kind_rejects_agent_kind(tmp_path: Path):
    agent = tmp_path / "moderator.yaml"
    agent.write_text("kind: agent\n", encoding="utf-8")
    config = {"kind": "agent", "metadata": {"name": "moderator"}}
    assert is_mas_manifest_kind(config, agent) is False
    assert mas_manifest_path(config, agent) is None


def test_entry_agent_label_from_loaded_mas_runtime_dict(tmp_path: Path):
    agent_path = tmp_path / "agent.yaml"
    agent_path.write_text("kind: agent\nmetadata:\n  name: qa-agent\n", encoding="utf-8")
    runtime_cfg = {
        "_loaded_mas_raw": True,
        "mas": {"entry_agent": "qa-agent"},
        "agents": [{"id": "qa-agent", "name": "qa-agent"}],
    }
    assert agent_manifest_label(runtime_cfg, agent_path) == "qa-agent"


def test_mas_bench_runner_passes_pattern_plugin_id_from_manifest(tmp_path: Path):
    manifest = {
        "metadata": {"name": "agent"},
        "spec": {"design_pattern": {"type": "cot"}},
    }
    agent_path = tmp_path / "agent.yaml"
    agent_path.write_text("kind: agent\n", encoding="utf-8")

    with patch("mas.ctl.benchmark.runner.instantiate_runtime") as inst:
        inst.return_value = (object(), None)
        with patch.object(MasBenchRunner, "_run_controller_turns") as turns:
            turns.return_value = RunResult(content="ok")
            MasBenchRunner().run(
                "hello",
                config=manifest,
                spec_path=agent_path,
                output_dir=tmp_path / "out",
            )
    options = inst.call_args[0][0]
    assert options.pattern_plugin_id == "cot@v1"


def test_mas_bench_compose_called_once_for_mas_kind(tmp_path: Path):
    mas_path = tmp_path / "workflow.yaml"
    mas_path.write_text(
        "kind: mas\nmetadata:\n  name: demo\nspec:\n  workflow:\n    entry: alpha\n",
        encoding="utf-8",
    )
    agent_path = tmp_path / "agents" / "alpha.yaml"
    agent_path.parent.mkdir()
    agent_path.write_text(
        "kind: agent\nmetadata:\n  name: alpha\nspec:\n  design_pattern:\n    type: react\n",
        encoding="utf-8",
    )

    compose = ComposeResult(
        mas_id="demo",
        mas_config={
            "kind": "mas",
            "metadata": {"name": "demo"},
            "spec": {"workflow": {"entry": "alpha"}, "agency": {"agents": [{"id": "alpha", "ref": "agents/alpha.yaml"}]}},
        },
        effective_bind={},
        placement_plan={},
        deployment={},
        infra_refs=[],
        bind=EffectiveBindManifest(
            mas_id="demo",
            spec_revision="",
            runtime_id="mas-runtime-py",
            deployment_name="local",
            agents=[AgentBindSlice(agent_id="alpha", pattern_plugin_id="react@v1")],
        ),
        plan=PlacementPlan(),
    )

    with patch("mas.ctl.benchmark.runner.compose_run", return_value=compose) as compose_run:
        with patch("mas.ctl.benchmark.runner.instantiate_runtime") as inst:
            inst.return_value = (object(), None)
            with patch.object(MasBenchRunner, "_run_controller_turns") as turns:
                turns.return_value = RunResult(content="ok")
                MasBenchRunner().run(
                    "hello",
                    config=compose.mas_config,
                    spec_path=mas_path,
                    output_dir=tmp_path / "out",
                )
    assert compose_run.call_count == 1


def test_sequential_topology_emits_events_artifact(tmp_path: Path):
    mas_path = tmp_path / "mas.yaml"
    agent_path = tmp_path / "agents" / "step-a.yaml"
    agent_path.parent.mkdir()
    agent_path.write_text("kind: agent\nmetadata:\n  name: step-a\n", encoding="utf-8")
    mas_path.write_text(
        "kind: mas\nmetadata:\n  name: demo\nspec:\n  workflow:\n    type: sequential\n    entry: step-a\n  agency:\n    agents:\n      - id: step-a\n        ref: agents/step-a.yaml\n",
        encoding="utf-8",
    )
    entry_manifest = {"metadata": {"name": "step-a"}, "spec": {}}
    output_dir = tmp_path / "out"

    compose = ComposeResult(
        mas_id="demo",
        mas_config={
            "kind": "mas",
            "metadata": {"name": "demo"},
            "spec": {
                "workflow": {
                    "type": "sequential",
                    "entry": "step-a",
                    "nodes": [{"id": "step-a"}, {"id": "step-b"}],
                },
                "agency": {"agents": [{"id": "step-a", "ref": "agents/step-a.yaml"}]},
            },
        },
        effective_bind={},
        placement_plan={},
        deployment={},
        infra_refs=[],
        bind=EffectiveBindManifest(
            mas_id="demo",
            spec_revision="",
            runtime_id="mas-runtime-py",
            deployment_name="local",
            agents=[
                AgentBindSlice(agent_id="step-a", pattern_plugin_id="react@v1"),
                AgentBindSlice(agent_id="step-b", pattern_plugin_id="react@v1"),
            ],
        ),
        plan=PlacementPlan(),
    )
    materialized = SimpleNamespace(
        compose=compose,
        materialized=SimpleNamespace(instances={}),
        mas_base_dir=mas_path.parent,
    )

    def _fake_seq(*_args, **_kwargs):
        # Simulate the run writing events.jsonl (runner picks these up as artifacts).
        events_path = output_dir / "traces" / "events.jsonl"
        events_path.parent.mkdir(parents=True, exist_ok=True)
        events_path.write_text('{"event":"turn"}\n', encoding="utf-8")
        return "done"

    with patch("mas.ctl.benchmark.runner.compose_run", return_value=compose):
        with patch("mas.ctl.benchmark.runner.materialize_mas_compose", return_value=materialized):
            with patch("mas.ctl.benchmark.runner.is_sequential_workflow", return_value=True):
                with patch(
                    "mas.ctl.benchmark.runner.run_sequential_workflow_queries",
                    side_effect=_fake_seq,
                ) as seq:
                    result = MasBenchRunner().run(
                        "hello",
                        config=compose.mas_config,
                        spec_path=mas_path,
                        output_dir=output_dir,
                    )
                    assert seq.called

    assert result.status == "ok"
    assert any(a.kind == "events" for a in result.artifacts)


def test_sequential_topology_applies_memory_seeds(tmp_path: Path):
    from mas.ctl.adapters.memory_seed import MemorySeed

    output_dir = tmp_path / "out"
    instance = SimpleNamespace(driver=SimpleNamespace(ctx=SimpleNamespace(memory_seeds=[])))
    materialized = SimpleNamespace(
        compose=SimpleNamespace(mas_config={"spec": {"workflow": {"type": "sequential"}}}),
        materialized=SimpleNamespace(instances={"step-a": instance, "step-b": instance}),
        mas_base_dir=tmp_path,
    )
    seeds = [MemorySeed(key="fact", content="seeded")]

    with patch("mas.ctl.benchmark.runner.run_sequential_workflow_queries", return_value="done"):
        with patch("mas.ctl.benchmark.runner.apply_memory_seeds") as apply_seeds:
            MasBenchRunner()._run_sequential_with_observability(
                materialized=materialized,
                queries=["hello"],
                output_dir=output_dir,
                entry_manifest={"metadata": {"name": "demo"}},
                entry_manifest_path=tmp_path / "demo.yaml",
                run_seed=0,
                memory_seeds=seeds,
            )
            assert apply_seeds.call_count == 2


def test_sequential_missing_edges_returns_run_result_error(tmp_path: Path):
    mas_path = tmp_path / "mas.yaml"
    mas_path.write_text("kind: mas\n", encoding="utf-8")
    output_dir = tmp_path / "out"
    materialized = SimpleNamespace(
        compose=SimpleNamespace(
            mas_config={
                "spec": {
                    "workflow": {
                        "type": "sequential",
                        "entry": "a",
                        "nodes": [{"id": "a"}, {"id": "b"}],
                    }
                }
            }
        ),
        materialized=SimpleNamespace(instances={}),
        mas_base_dir=mas_path.parent,
    )
    result = MasBenchRunner()._run_sequential_with_observability(
        materialized=materialized,
        queries=["hello"],
        output_dir=output_dir,
        entry_manifest={"metadata": {"name": "demo"}},
        entry_manifest_path=mas_path.parent / "demo.yaml",
        run_seed=0,
        memory_seeds=[],
    )
    assert result.status == "error"
    assert "workflow.edges" in (result.error or "")


def test_compose_path_skips_stacked_merge_for_loaded_mas_raw(tmp_path: Path):
    from mas.lab.manifest.load import LOADED_MAS_RAW_KEY

    mas_path = tmp_path / "mas.yaml"
    mas_path.write_text(
        "kind: mas\nmetadata:\n  name: demo\nspec:\n  workflow:\n    entry: alpha\n",
        encoding="utf-8",
    )
    agent_path = tmp_path / "agents" / "alpha.yaml"
    agent_path.parent.mkdir()
    agent_path.write_text("kind: agent\nmetadata:\n  name: alpha\n", encoding="utf-8")

    loaded_raw = {
        LOADED_MAS_RAW_KEY: True,
        "mas": {"entry_agent": "alpha"},
        "agents": [{"id": "alpha", "_agent_dir": str(agent_path.parent), "pattern_framework": "cot"}],
    }
    compose = ComposeResult(
        mas_id="demo",
        mas_config={
            "kind": "mas",
            "metadata": {"name": "demo"},
            "spec": {"workflow": {"entry": "alpha"}, "agency": {"agents": [{"id": "alpha", "ref": "agents/alpha.yaml"}]}},
        },
        effective_bind={},
        placement_plan={},
        deployment={},
        infra_refs=[],
        bind=EffectiveBindManifest(
            mas_id="demo",
            spec_revision="",
            runtime_id="mas-runtime-py",
            deployment_name="local",
            agents=[AgentBindSlice(agent_id="alpha", pattern_plugin_id="cot@v1")],
        ),
        plan=PlacementPlan(),
    )

    with patch("mas.ctl.benchmark.runner.compose_run", return_value=compose):
        with patch("mas.ctl.benchmark.runner.merge_stacked_entry_agent_manifest") as merge:
            with patch("mas.ctl.benchmark.runner.instantiate_runtime") as inst:
                inst.return_value = (object(), None)
                with patch.object(MasBenchRunner, "_run_controller_turns") as turns:
                    turns.return_value = RunResult(content="ok")
                    MasBenchRunner().run(
                        "hello",
                        config=loaded_raw,
                        spec_path=mas_path,
                        output_dir=tmp_path / "out",
                    )
                    merge.assert_not_called()


def test_entry_agent_from_compose_mas_kind_nonstandard_filename(tmp_path: Path):
    mas_path = tmp_path / "triage.yaml"
    mas_path.write_text(
        "kind: mas\nmetadata:\n  name: triage\nspec:\n  workflow:\n    entry: alpha\n  agency:\n    agents:\n      - id: alpha\n        ref: agents/alpha.yaml\n",
        encoding="utf-8",
    )
    agent_path = tmp_path / "agents" / "alpha.yaml"
    agent_path.parent.mkdir()
    agent_path.write_text("kind: agent\nmetadata:\n  name: alpha\n", encoding="utf-8")

    compose = ComposeResult(
        mas_id="triage",
        mas_config={
            "kind": "mas",
            "metadata": {"name": "triage"},
            "spec": {
                "workflow": {"entry": "alpha"},
                "agency": {"agents": [{"id": "alpha", "ref": "agents/alpha.yaml"}]},
            },
        },
        effective_bind={},
        placement_plan={},
        deployment={},
        infra_refs=[],
        bind=EffectiveBindManifest(
            mas_id="triage",
            spec_revision="",
            runtime_id="mas-runtime-py",
            deployment_name="local",
            agents=[AgentBindSlice(agent_id="alpha", pattern_plugin_id="react@v1")],
        ),
        plan=PlacementPlan(),
    )

    manifest, path = entry_agent_from_compose(compose, mas_path)
    assert path == agent_path
    assert manifest.get("metadata", {}).get("name") == "alpha"


def test_mas_bench_forwards_infra_refs_to_compose(tmp_path: Path):
    mas_path = tmp_path / "mas.yaml"
    mas_path.write_text(
        "kind: mas\nmetadata:\n  name: demo\nspec:\n  workflow:\n    entry: alpha\n"
        "  agency:\n    agents:\n      - id: alpha\n        ref: agents/alpha.yaml\n",
        encoding="utf-8",
    )
    agent_path = tmp_path / "agents" / "alpha.yaml"
    agent_path.parent.mkdir()
    agent_path.write_text("kind: agent\nmetadata:\n  name: alpha\n", encoding="utf-8")

    compose = ComposeResult(
        mas_id="demo",
        mas_config={
            "kind": "mas",
            "metadata": {"name": "demo"},
            "spec": {
                "workflow": {"entry": "alpha"},
                "agency": {"agents": [{"id": "alpha", "ref": "agents/alpha.yaml"}]},
            },
        },
        effective_bind={},
        placement_plan={},
        deployment={},
        infra_refs=["standard:llm-proxy"],
        bind=EffectiveBindManifest(
            mas_id="demo",
            spec_revision="",
            runtime_id="mas-runtime-py",
            deployment_name="local",
            agents=[AgentBindSlice(agent_id="alpha", pattern_plugin_id="react@v1")],
        ),
        plan=PlacementPlan(),
    )

    with patch("mas.ctl.benchmark.runner.compose_run", return_value=compose) as compose_run:
        with patch("mas.ctl.benchmark.runner.instantiate_runtime") as inst:
            inst.return_value = (object(), None)
            with patch.object(MasBenchRunner, "_run_controller_turns") as turns:
                turns.return_value = RunResult(content="ok")
                MasBenchRunner().run(
                    "hello",
                    config=compose.mas_config,
                    spec_path=mas_path,
                    output_dir=tmp_path / "out",
                    infra_refs=["standard:llm-proxy"],
                )
    req = compose_run.call_args[0][0]
    assert req.infra_refs == ["standard:llm-proxy"]
