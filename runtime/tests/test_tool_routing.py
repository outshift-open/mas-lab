#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import pytest
from mas.runtime.engine.tool_routing import (
    ProviderClaim,
    ToolRouteConflictError,
    UnclaimedToolError,
    build_tool_routes,
    is_star_claim,
)


def test_no_external_implicit_local():
    routes = build_tool_routes(["web-search", "calc"], [])
    assert routes["web-search"].provider_name == "local"
    assert routes["calc"].via == "local"


def test_star_claim_is_discovery():
    assert is_star_claim("*")
    assert is_star_claim(("*",))
    assert not is_star_claim(("web-search",))


def test_external_star_without_local_overlay_errors_on_leftover():
    with pytest.raises(UnclaimedToolError, match="not claimed by any provider"):
        build_tool_routes(
            ["web-search", "calc"],
            [ProviderClaim("search", ("web-search",), "*", object())],
        )


def test_external_star_plus_local_star_keeps_leftover_in_process():
    ext = object()
    routes = build_tool_routes(
        ["web-search", "calc"],
        [
            ProviderClaim("search", ("web-search",), "*", ext),
            ProviderClaim("in-process", ("web-search", "calc"), "*", None, origin="local"),
        ],
    )
    assert routes["web-search"].provider_name == "search"
    assert routes["web-search"].via == "discover"
    assert routes["calc"].provider_name == "in-process"
    assert routes["calc"].via == "local"
    assert routes["calc"].handler is None


def test_system_tools_stay_implicit_local_when_external_present():
    ext = object()
    routes = build_tool_routes(
        ["web-search", "request_human_input", "inform_user"],
        [ProviderClaim("search", ("web-search",), "*", ext)],
    )
    assert routes["web-search"].handler is ext
    assert routes["request_human_input"].provider_name == "local"
    assert routes["inform_user"].via == "local"


def test_explicit_claim_beats_star():
    a, b = object(), object()
    routes = build_tool_routes(
        ["web-search"],
        [
            ProviderClaim("star", ("web-search", "other"), "*", a),
            ProviderClaim("named", ("web-search",), ("web-search",), b),
        ],
    )
    assert routes["web-search"].provider_name == "named"
    assert routes["web-search"].via == "explicit"
    assert routes["other"].provider_name == "star"


def test_two_stars_same_name_conflict():
    with pytest.raises(ToolRouteConflictError, match="advertised by both"):
        build_tool_routes(
            [],
            [
                ProviderClaim("a", ("web-search",), "*", object()),
                ProviderClaim("b", ("web-search",), "*", object()),
            ],
        )


def test_two_explicit_same_name_conflict():
    with pytest.raises(ToolRouteConflictError, match="claimed explicitly"):
        build_tool_routes(
            [],
            [
                ProviderClaim("a", ("web-search",), ("web-search",), object()),
                ProviderClaim("b", ("web-search",), ("web-search",), object()),
            ],
        )


def test_two_providers_different_tools():
    a, b = object(), object()
    routes = build_tool_routes(
        ["web-search", "lookup-schedule"],
        [
            ProviderClaim("search", ("web-search",), ("web-search",), a),
            ProviderClaim("sched", ("lookup-schedule",), "*", b),
        ],
    )
    assert routes["web-search"].provider_name == "search"
    assert routes["lookup-schedule"].provider_name == "sched"


def test_star_with_empty_advertisement_claims_nothing():
    with pytest.raises(UnclaimedToolError, match="web-search"):
        build_tool_routes(
            ["web-search"],
            [ProviderClaim("empty", (), "*", object())],
        )
