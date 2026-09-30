from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass

from mas.runtime.boundary.agentcomm.protocol import AgentCommContract


@dataclass(frozen=True)
class AgentCommRoute:
    agent_id: str
    kind: str
    handler: AgentCommContract


class UnknownDelegationPeerError(ValueError):
    """A delegates_to target has no local or configured remote route."""


def build_agent_comm_routes(
    local_agent_ids: Collection[str],
    local_handler: AgentCommContract,
    peer_routes: Mapping[str, AgentCommRoute],
    *,
    delegated_names: Collection[str],
) -> dict[str, AgentCommRoute]:
    routes = {
        agent_id: AgentCommRoute(agent_id=agent_id, kind="local", handler=local_handler)
        for agent_id in local_agent_ids
    }
    routes.update(peer_routes)
    missing = set(delegated_names).difference(routes)
    if missing:
        raise UnknownDelegationPeerError(
            "delegates_to references unknown agent(s): " + ", ".join(sorted(missing))
        )
    return routes