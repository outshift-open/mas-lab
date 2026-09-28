#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from mas.lab.benchmark.pipeline.core import PipelineStep
from mas.lab.benchmark.pipeline.models import StepOutput


class _Probe(PipelineStep):
    type = "probe"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.events: list[dict] = []

    def on_event(self, event, ctx):
        self.events.append(event)

    async def execute(self, ctx) -> StepOutput:
        return StepOutput(data={"n": len(self.events)})


def test_streaming_flag_and_on_event() -> None:
    step = _Probe(name="p", config={}, streaming=True)
    assert step.streaming is True
    step.on_event({"kind": "tool"}, ctx=None)
    assert step.events[0]["kind"] == "tool"


def test_from_dict_accepts_streaming_key() -> None:
    from mas.lab.benchmark.pipeline.core import register_step_type

    register_step_type("probe_stream", _Probe)
    step = PipelineStep.from_dict({"name": "p", "type": "probe_stream", "streaming": True})
    assert step.streaming is True
