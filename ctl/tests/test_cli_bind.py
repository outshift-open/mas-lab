# Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
# SPDX-License-Identifier: Apache-2.0
"""URI launch-wiring shorthand expands into infra CLI overrides."""

from __future__ import annotations

from mas.ctl.overrides import apply_cli_overrides, expand_binds
from mas.ctl.overrides.bind import combine_overrides
from mas.ctl.session.flavour import resolve_flavour


def test_expand_binds_a2a_is_infra_use_not_a_flavour_switch() -> None:
    overrides = expand_binds(
        (
            "banking_assistant=a2a://127.0.0.1:8080/agents/banking_assistant/",
            "fraud_adjudicator=a2a://127.0.0.1:8080/agents/fraud_adjudicator/",
        )
    )
    document = {
        "apiVersion": "infra/v1",
        "kind": "InfraBundle",
        "metadata": {"name": "merged"},
        "spec": {"endpoints": {}, "tool_servers": []},
    }

    result = apply_cli_overrides(document, overrides, root="infra")

    assert result["spec"]["endpoints"]["banking_assistant"] == {
        "protocol": "a2a",
        "usage": "use",
        "url": "http://127.0.0.1:8080/agents/banking_assistant/",
    }
    assert result["spec"]["endpoints"]["fraud_adjudicator"]["usage"] == "use"
    assert all(item.startswith("infra:") for item in overrides)
    flavour = resolve_flavour("local", overrides=overrides)
    assert flavour.get("agent_comm", {}).get("protocol") == "agent-local"


def test_expand_binds_mcp_collapses_same_origin_into_one_tool_server() -> None:
    overrides = expand_binds(
        (
            "analyze_transaction_risk=mcp://127.0.0.1:8080/mcp#analyze_transaction_risk",
            "calculate_fraud_score=mcp://127.0.0.1:8080/mcp#calculate_fraud_score",
        )
    )

    assert len(overrides) == 1
    assert overrides[0].startswith("infra:spec.tool_servers[id=mcp-127.0.0.1-8080-mcp]=")
    assert "analyze_transaction_risk" in overrides[0]
    assert "calculate_fraud_score" in overrides[0]
    flavour = resolve_flavour("local", overrides=overrides)
    assert flavour.get("agent_comm", {}).get("protocol") == "agent-local"
    assert flavour.get("tools", {}).get("remote_tools_enabled") is False


def test_explicit_override_wins_over_bind() -> None:
    combined = combine_overrides(
        binds=("greeter=a2a://127.0.0.1:9002/",),
        overrides=("infra:spec.endpoints['greeter'].url=http://127.0.0.1:9009",),
    )
    document = {
        "apiVersion": "infra/v1",
        "kind": "InfraBundle",
        "metadata": {"name": "merged"},
        "spec": {"endpoints": {}, "tool_servers": []},
    }

    result = apply_cli_overrides(document, combined, root="infra")

    assert result["spec"]["endpoints"]["greeter"]["url"] == "http://127.0.0.1:9009"
    assert result["spec"]["endpoints"]["greeter"]["protocol"] == "a2a"
    assert result["spec"]["endpoints"]["greeter"]["usage"] == "use"


def test_bind_creates_missing_mcp_tool_server() -> None:
    overrides = expand_binds(("lookup=mcp://127.0.0.1:9001/mcp#lookup",))
    document = {
        "apiVersion": "infra/v1",
        "kind": "InfraBundle",
        "metadata": {"name": "merged"},
        "spec": {"endpoints": {}, "tool_servers": [{"id": "local", "protocol": "local"}]},
    }

    result = apply_cli_overrides(
        document,
        overrides,
        root="infra",
    )

    servers = {item["id"]: item for item in result["spec"]["tool_servers"]}
    assert "local" in servers
    assert servers["mcp-127.0.0.1-9001-mcp"]["url"] == "http://127.0.0.1:9001/mcp"
    assert servers["mcp-127.0.0.1-9001-mcp"]["tools"] == ["lookup"]
    assert servers["mcp-127.0.0.1-9001-mcp"]["usage"] == "use"


def test_public_live_commands_expose_bind_option() -> None:
    import importlib

    from click.testing import CliRunner

    for module_name, attr in (
        ("mas.ctl.cli.commands.chat", "chat_cmd"),
        ("mas.ctl.cli.commands.compose", "compose_cmd"),
        ("mas.ctl.cli.commands.run_mas", "run_mas_cmd"),
        ("mas.ctl.cli.commands.serve", "serve_agent_cmd"),
        ("mas.ctl.cli.commands.tui", "tui_cmd"),
    ):
        result = CliRunner().invoke(getattr(importlib.import_module(module_name), attr), ["--help"])
        assert result.exit_code == 0, result.output
        assert "--bind NAME=URI" in result.output
