#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from mas.library.eval.metrics.plugins import reset_metrics_for_tests
from mas.library.eval.metrics.prompt import (
    parse_prompt_metrics,
    value_from_judge,
)
from mas.library.lab.steps.eval.mce import EvalMceStep


@pytest.fixture(autouse=True)
def _clean_hosted_metrics():
    reset_metrics_for_tests()
    yield
    reset_metrics_for_tests()


def test_value_from_judge_numeric_and_yes_no() -> None:
    assert value_from_judge({"value": 0.75, "reasoning": "ok"}) == (0.75, "ok")
    assert value_from_judge({"answer": "YES", "evidence": "tool"}) == (1.0, "tool")
    assert value_from_judge({"answer": "NO"})[0] == 0.0
    with pytest.raises(ValueError):
        value_from_judge({"comment": "no score"})


def _prompt_item(**overrides: object) -> dict:
    item = {
        "id": "used_a_tool",
        "prompt": "Did the agent call a tool?",
        "unit": "mas",
        "evidence": "trajectory",
    }
    item.update(overrides)
    return item


def test_parse_prompt_metrics_requires_id_prompt_and_scope() -> None:
    parsed = parse_prompt_metrics([_prompt_item()])
    assert len(parsed) == 1
    assert parsed[0].metric_id == "used_a_tool"
    assert parsed[0].unit == "mas"
    assert parsed[0].evidence == "trajectory"
    assert parsed[0].system is None
    with_desc = parse_prompt_metrics([_prompt_item(description="1.0 if a tool was called")])
    assert with_desc[0].description == "1.0 if a tool was called"
    with pytest.raises(ValueError, match="unit"):
        parse_prompt_metrics([{"id": "used_a_tool", "prompt": "x"}])
    with pytest.raises(ValueError, match="snake_case"):
        parse_prompt_metrics([_prompt_item(id="Used-A-Tool")])
    with pytest.raises(ValueError, match="duplicate"):
        parse_prompt_metrics(
            [
                _prompt_item(prompt="a"),
                _prompt_item(prompt="b"),
            ]
        )


@pytest.mark.asyncio
async def test_eval_mce_prompt_metrics_in_addition(tmp_path, monkeypatch) -> None:
    events = tmp_path / "topo" / "item1" / "r1" / "traces" / "events.jsonl"
    events.parent.mkdir(parents=True)
    events.write_text('{"kind":"tool_call_start","tool_name":"calc"}\n', encoding="utf-8")
    monkeypatch.setattr(
        "mas.library.eval.mce.runner.install_openai_llm_service",
        lambda *args, **kwargs: "gpt-4o",
    )
    monkeypatch.setattr(
        "mas.library.eval.mce.runner.compute_session_metrics",
        lambda *args, **kwargs: {
            "groundedness": {"value": 0.5, "reasoning": "stub", "error": None},
            "__run_quality__": {"warnings": [], "errors": [], "status": "ok"},
        },
    )
    monkeypatch.setattr(
        "mas.library.eval.metrics.prompt.complete_json",
        lambda *args, **kwargs: {"value": 1.0, "reasoning": "calc was called"},
    )
    step = EvalMceStep(
        name="eval_mce",
        config={
            "run_dir": str(events.parent.parent),
            "events_path": str(events),
            "metrics": ["groundedness"],
            "prompt_metrics": [_prompt_item()],
            "validate": False,
        },
    )
    out = await step.execute(
        SimpleNamespace(
            output_dir=tmp_path,
            pipeline=SimpleNamespace(config_path=None),
            template_vars={},
            scope_context=None,
        )
    )
    doc = json.loads(Path(out.metadata["output"]).read_text(encoding="utf-8"))
    assert doc["session"]["groundedness"]["value"] == 0.5
    assert doc["session"]["used_a_tool"]["value"] == 1.0
    assert "calc" in doc["session"]["used_a_tool"]["reasoning"]


@pytest.mark.asyncio
async def test_prompt_metrics_send_no_default_system(tmp_path, monkeypatch) -> None:
    events = tmp_path / "topo" / "item1" / "r1" / "traces" / "events.jsonl"
    events.parent.mkdir(parents=True)
    events.write_text('{"kind":"tool_call_start","tool_name":"calc"}\n', encoding="utf-8")
    captured: list[list[dict[str, str]]] = []

    def _capture(messages, **kwargs):
        captured.append(list(messages))
        return {"value": 1.0, "reasoning": "ok"}

    monkeypatch.setattr(
        "mas.library.eval.mce.runner.install_openai_llm_service",
        lambda *args, **kwargs: "gpt-4o",
    )
    monkeypatch.setattr(
        "mas.library.eval.metrics.prompt.complete_json",
        _capture,
    )
    step = EvalMceStep(
        name="eval_mce",
        config={
            "run_dir": str(events.parent.parent),
            "events_path": str(events),
            "metrics": [],
            "prompt_metrics": [
                _prompt_item(prompt='Did the agent call a tool? Return JSON {"value": 1.0 or 0.0, "reasoning": "..."}.')
            ],
            "validate": False,
        },
    )
    await step.execute(
        SimpleNamespace(
            output_dir=tmp_path,
            pipeline=SimpleNamespace(config_path=None),
            template_vars={},
            scope_context=None,
        )
    )
    assert captured
    roles = [m["role"] for m in captured[0]]
    assert "system" not in roles
    assert captured[0][0]["role"] == "user"
    assert "Did the agent call a tool?" in captured[0][0]["content"]
    assert "## TRACE" in captured[0][0]["content"]


@pytest.mark.asyncio
async def test_prompt_metrics_io_sends_input_output_not_trace(tmp_path, monkeypatch) -> None:
    events = tmp_path / "topo" / "item1" / "r1" / "traces" / "events.jsonl"
    events.parent.mkdir(parents=True)
    events.write_text(
        "\n".join(
            [
                '{"kind":"execution_start","parent_call_id":null,"agent_id":"root","input":"hello"}',
                '{"kind":"tool_call_start","tool_name":"calc"}',
                '{"kind":"execution_end","agent_id":"root","output":"world"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    captured: list[list[dict[str, str]]] = []

    def _capture(messages, **kwargs):
        captured.append(list(messages))
        return {"value": 1.0, "reasoning": "io only"}

    monkeypatch.setattr(
        "mas.library.eval.mce.runner.install_openai_llm_service",
        lambda *args, **kwargs: "gpt-4o",
    )
    monkeypatch.setattr(
        "mas.library.eval.metrics.prompt.complete_json",
        _capture,
    )
    step = EvalMceStep(
        name="eval_mce",
        config={
            "run_dir": str(events.parent.parent),
            "events_path": str(events),
            "metrics": [],
            "prompt_metrics": [
                _prompt_item(
                    id="answered",
                    prompt="Did OUTPUT answer INPUT?",
                    evidence="io",
                )
            ],
            "validate": False,
        },
    )
    out = await step.execute(
        SimpleNamespace(
            output_dir=tmp_path,
            pipeline=SimpleNamespace(config_path=None),
            template_vars={},
            scope_context=None,
        )
    )
    body = captured[0][0]["content"]
    assert "## INPUT" in body
    assert "hello" in body
    assert "world" in body
    assert "tool_call_start" not in body
    doc = json.loads(Path(out.metadata["output"]).read_text(encoding="utf-8"))
    assert doc["session"]["answered"]["details"]["unit"] == "mas"
    assert doc["session"]["answered"]["details"]["evidence"] == "io"


@pytest.mark.asyncio
async def test_eval_mce_prompt_metrics_collision(tmp_path, monkeypatch) -> None:
    events = tmp_path / "topo" / "item1" / "r1" / "traces" / "events.jsonl"
    events.parent.mkdir(parents=True)
    events.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(
        "mas.library.eval.mce.runner.install_openai_llm_service",
        lambda *args, **kwargs: "gpt-4o",
    )
    step = EvalMceStep(
        name="eval_mce",
        config={
            "run_dir": str(events.parent.parent),
            "events_path": str(events),
            "metrics": ["groundedness"],
            "prompt_metrics": [_prompt_item(id="groundedness", prompt="Should collide.")],
            "validate": False,
        },
    )
    out = await step.execute(
        SimpleNamespace(
            output_dir=tmp_path,
            pipeline=SimpleNamespace(config_path=None),
            template_vars={},
            scope_context=None,
        )
    )
    assert out.data["errors"] == 1
    doc = json.loads(Path(out.metadata["output"]).read_text(encoding="utf-8"))
    assert any("collide" in err for err in doc["run_quality"]["errors"])
