from __future__ import annotations

from typing import Any

from mas.runtime.kernel.state import DpState
from mas.runtime.machines.design_pattern.protocol import DesignPatternPlugin
from mas.runtime.schema.egress import EgressSymbol, EmitClientResponse, NoOp
from mas.runtime.schema.ingress import IngressSymbol, UserInputReceived


class ScriptedResponsePlugin(DesignPatternPlugin):
    """Emit manifest-defined responses without invoking an LLM."""

    plugin_id = "scripted_response@v1"

    @staticmethod
    def _params(config: Any) -> dict[str, Any]:
        spec = config.agent_spec or {}
        binding = spec.get("design_pattern") or {}
        if not isinstance(binding, dict):
            return {}
        params = binding.get("params") or binding.get("config") or {}
        return params if isinstance(params, dict) else {}

    @staticmethod
    def _matches(rule: dict[str, Any], event: UserInputReceived) -> bool:
        turn_prefix = str(rule.get("turn_id_prefix") or "")
        prompt = rule.get("prompt")
        return (not turn_prefix or event.user_turn_id.startswith(turn_prefix)) and (
            prompt is None or event.text == str(prompt)
        )

    @classmethod
    def _response(cls, config: Any, event: UserInputReceived) -> dict[str, Any]:
        params = cls._params(config)
        for rule in params.get("rules") or []:
            if isinstance(rule, dict) and cls._matches(rule, event):
                response = rule.get("response") or {}
                return response if isinstance(response, dict) else {}
        default = params.get("default") or {}
        return default if isinstance(default, dict) else {}

    def handle_event(
        self,
        ctx: Any,
        run: Any,
        event: IngressSymbol,
        *,
        config: Any,
    ) -> list[EgressSymbol]:
        if not isinstance(event, UserInputReceived):
            return [NoOp()]
        response = self._response(config, event)
        ctx.dp = DpState.IDLE
        ctx.scheduled_egress = "NONE"
        return [
            EmitClientResponse(
                content=str(response.get("text") or ""),
                finish_reason=str(response.get("finish_reason") or "stop"),
                artifacts=tuple(response.get("artifacts") or ()),
                task_state=response.get("task_state"),
                stream_chunks=tuple(response.get("stream_chunks") or ()),
            )
        ]

    def on_user_input(self, ctx: Any, event: object) -> DpState:
        return DpState.IDLE

    def on_context_complete(self, ctx: Any) -> tuple[DpState, None]:
        return DpState.IDLE, None

    def on_evaluate(self, ctx: Any) -> tuple[DpState, None]:
        return DpState.IDLE, None
