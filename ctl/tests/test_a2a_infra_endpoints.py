from __future__ import annotations

import json
import socket
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import uvicorn
import yaml
from fastapi.testclient import TestClient
from library_ioa.plugins.a2a.agent_comm import A2AAgentComm
from library_ioa.plugins.a2a.exposure import A2AExposure
from library_ioa.plugins.a2a.server.app import build_app
from library_ioa.plugins.a2a.server.executor import MasLabAgentExecutor
from mas.ctl.cli.commands.serve import _make_runtime_handler
from mas.ctl.infra.resolve import (
    application_endpoint_is_deployed,
    application_endpoint_is_used,
    application_endpoint_usage,
    resolve_infra_refs,
)
from mas.ctl.manifest.mas_agent_merge import wire_entry_engine_delegation
from mas.ctl.overlay.merge import OverlayTargetError, merge_mas_overlay
from mas.ctl.validate import validate_file
from mas.ctl.workspace.config import WorkspaceConfig
from mas.runtime.boundary.agentcomm.routing import AgentCommRoute
from mas.runtime.driver.instance import RuntimeInstance
from mas.runtime.driver.mocks import AutoCtxAssembler
from mas.runtime.engine.llm_live import LiveLlmEngine


def test_application_infra_resolves_named_a2a_endpoint(tmp_path: Path) -> None:
    infra_path = tmp_path / "a2a.yaml"
    infra_path.write_text(
        yaml.safe_dump(
            {
                "apiVersion": "infra/v1",
                "kind": "Application",
                "metadata": {"name": "a2a-agents"},
                "spec": {
                    "endpoints": {
                        "weather-oracle": {
                            "protocol": "a2a",
                            "url": "http://127.0.0.1:9005",
                            "usage": "use-and-deploy",
                            "a2a": {
                                "listen": {"host": "0.0.0.0", "port": 9008},
                                "grpc_port": 9007,
                                "grpc_url": "grpc://a2a.example.test:9007",
                                "capabilities": {
                                    "streaming": False,
                                    "pushNotifications": False,
                                },
                            },
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    validation = validate_file(infra_path, kind="infra", strict=True)
    assert validation.ok, validation.issues

    resolved = resolve_infra_refs(
        [str(infra_path)],
        anchor=tmp_path,
        workspace=WorkspaceConfig({}),
    )

    assert resolved.applications["weather-oracle"]["url"] == "http://127.0.0.1:9005"
    assert resolved.applications["weather-oracle"]["protocol"] == "a2a"
    endpoint = resolved.applications["weather-oracle"]
    assert application_endpoint_usage(endpoint) == "use-and-deploy"
    assert endpoint["a2a"]["listen"] == {"host": "0.0.0.0", "port": 9008}
    assert endpoint["a2a"]["grpc_port"] == 9007
    assert endpoint["a2a"]["grpc_url"] == "grpc://a2a.example.test:9007"
    assert endpoint["a2a"]["capabilities"]["streaming"] is False


@pytest.mark.parametrize(
    ("endpoint", "expected_usage", "used", "deployed"),
    [
        ({"usage": "use"}, "use", True, False),
        ({"usage": "deploy"}, "deploy", False, True),
        ({"usage": "use-and-deploy"}, "use-and-deploy", True, True),
        ({"expose": True}, "use-and-deploy", True, True),
        ({}, "use", True, False),
    ],
)
def test_application_endpoint_usage_modes(
    endpoint: dict[str, str | bool],
    expected_usage: str,
    used: bool,
    deployed: bool,
) -> None:
    assert application_endpoint_usage(endpoint) == expected_usage
    assert application_endpoint_is_used(endpoint) is used
    assert application_endpoint_is_deployed(endpoint) is deployed


def test_serve_runtime_handler_forwards_generic_turn_and_session_ids() -> None:
    calls: list[tuple[str, str, str, str, int | None]] = []

    class RuntimeInstance:
        def run_user_text(
            self,
            text: str,
            *,
            turn_id: str,
            session_id: str,
            parent_call_id: str,
            upstream_correlation_id: int | None,
        ) -> SimpleNamespace:
            calls.append(
                (text, turn_id, session_id, parent_call_id, upstream_correlation_id)
            )
            return SimpleNamespace(client_responses=[SimpleNamespace(content="answer")])

    handler = _make_runtime_handler(RuntimeInstance())

    assert handler(
        "question",
        turn_id="turn-1",
        session_id="session-1",
        parent_call_id="parent-1",
        upstream_correlation_id=42,
    ) == {"text": "answer"}
    assert calls == [("question", "turn-1", "session-1", "parent-1", 42)]


def test_serve_runtime_handler_preserves_structured_artifacts() -> None:
    class RuntimeInstance:
        def run_user_text(self, *_: Any, **__: Any) -> SimpleNamespace:
            return SimpleNamespace(
                client_responses=[
                    SimpleNamespace(
                        content="Generated output",
                        artifacts=(
                            {
                                "kind": "data",
                                "name": "result",
                                "data": {"value": 42},
                            },
                        ),
                    )
                ]
            )

    assert _make_runtime_handler(RuntimeInstance())("question") == {
        "text": "Generated output",
        "artifacts": [
            {
                "kind": "data",
                "name": "result",
                "data": {"value": 42},
            }
        ],
    }


def test_serve_runtime_handler_marks_pending_hitl_as_input_required() -> None:
    class RuntimeInstance:
        def run_user_text(self, *_: Any, **__: Any) -> SimpleNamespace:
            return SimpleNamespace(client_responses=[], awaiting_hitl=True)

    assert _make_runtime_handler(RuntimeInstance())("approve this tool call") == {
        "text": "",
        "task_state": "input_required",
    }


def test_a2a_exposed_runtime_delegates_outbound_through_agent_comm_in_same_process(
    tmp_path: Path,
) -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        peer_port = listener.getsockname()[1]
    peer_url = f"http://127.0.0.1:{peer_port}"
    peer_calls: list[str] = []
    peer_app = build_app(
        {
            "name": "remote-peer",
            "description": "Remote A2A peer",
            "url": peer_url,
            "version": "1.0.0",
            "defaultInputModes": ["text/plain"],
            "defaultOutputModes": ["text/plain"],
            "skills": [],
        },
        MasLabAgentExecutor(
            lambda prompt, **_: (peer_calls.append(prompt) or {"text": f"peer:{prompt}"})
        ),
    )
    peer_started = threading.Event()

    class ReadyServer(uvicorn.Server):
        async def startup(self, sockets: Any = None) -> None:
            await super().startup(sockets=sockets)
            peer_started.set()

    peer_server = ReadyServer(
        uvicorn.Config(
            peer_app,
            host="127.0.0.1",
            port=peer_port,
            log_level="critical",
            ws="none",
        )
    )
    peer_thread = threading.Thread(target=peer_server.run, daemon=True)
    peer_thread.start()

    class ScriptedProvider:
        def __init__(self) -> None:
            self.calls = 0
            self.saw_peer_result = False

        def chat_completion(self, **kwargs: Any) -> dict[str, Any]:
            self.calls += 1
            if self.calls == 1:
                return {
                    "tool_calls": [
                        {
                            "id": "delegate-call",
                            "type": "function",
                            "function": {
                                "name": "delegate_to_remote-peer",
                                "arguments": json.dumps({"task": "hello"}),
                            },
                        }
                    ]
                }
            tool_results = [
                str(message.get("content") or "")
                for message in kwargs["messages"]
                if message.get("role") == "tool"
            ]
            self.saw_peer_result = any("peer:hello" in result for result in tool_results)
            return {"content": f"received peer reply: {tool_results[-1]}"}

    provider = ScriptedProvider()
    manifest = {
        "metadata": {"name": "exposed-agent"},
        "spec": {
            "description": "A2A agent that delegates to a remote peer",
            "workflow": {
                "entry": "exposed-agent",
                "nodes": [{"id": "exposed-agent", "delegates_to": ["remote-peer"]}],
            },
        },
    }
    runtime_ctx = AutoCtxAssembler()
    engine = LiveLlmEngine(
        ctx=runtime_ctx,
        manifest=manifest,
        llm_provider=provider,
        use_cache=False,
        use_tool_loop=True,
    )
    agent_comm = A2AAgentComm(url=peer_url, timeout=10)

    class _UnusedLocal:
        def send(self, *args: object, **kwargs: object) -> str:
            return "unused local route"

    wire_entry_engine_delegation(
        engine,
        manifest,
        tmp_path,
        comm=_UnusedLocal(),
        entry_agent_id="exposed-agent",
        routes={
            "remote-peer": AgentCommRoute(
                agent_id="remote-peer",
                kind="a2a",
                handler=agent_comm,
            )
        },
    )
    instance = RuntimeInstance.from_parts(engine=engine, ctx=runtime_ctx)
    instance.capture_session_baseline()

    def run_runtime(prompt: str, **kwargs: Any) -> dict[str, str]:
        trace = instance.run_user_text(prompt, **kwargs)
        return {
            "text": "\n".join(
                response.content
                for response in trace.client_responses
                if getattr(response, "content", "")
            )
        }

    try:
        assert peer_started.wait(timeout=10)
        exposed_app = A2AExposure(
            endpoint={
                "protocol": "a2a",
                "url": "http://127.0.0.1:9004",
                "usage": "use-and-deploy",
            },
            webserver=object(),
        ).build_app(manifest, run_runtime)

        with TestClient(exposed_app) as client:
            response = client.post(
                "/",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "SendMessage",
                    "params": {
                        "message": {
                            "role": "ROLE_USER",
                            "parts": [{"text": "start outbound delegation"}],
                            "messageId": "outer-message",
                        }
                    },
                },
                headers={"A2A-Version": "1.0"},
            )

        assert response.status_code == 200
        assert peer_calls == ["hello"]
        assert provider.saw_peer_result
        assert "received peer reply: peer:hello" in response.text
    finally:
        agent_comm.close()
        peer_server.should_exit = True
        peer_thread.join(timeout=10)
        assert not peer_thread.is_alive()


def test_mas_overlay_rejects_legacy_transport_fields() -> None:
    mas = {
        "apiVersion": "mas/v1",
        "kind": "MAS",
        "spec": {
            "agency": {"agents": [{"id": "moderator", "ref": "moderator.yaml"}]},
            "workflow": {"entry": "moderator", "nodes": [{"id": "moderator"}]},
        },
    }
    overlay = {
        "apiVersion": "mas/v1",
        "kind": "Overlay",
        "spec": {
            "target": {"kind": "MAS"},
            "patch": {"agents": {"moderator": {"expose": {"kind": "a2a"}}}},
        },
    }

    with pytest.raises(OverlayTargetError, match="infra Application endpoint"):
        merge_mas_overlay(mas, overlay)
