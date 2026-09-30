from __future__ import annotations

from typing import Any

from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentProvider, AgentSkill


def agent_card_from_manifest(
    manifest: dict[str, Any],
    *,
    url: str,
    grpc_url: str | None = None,
    capabilities: dict[str, Any] | None = None,
) -> AgentCard:
    metadata = manifest.get("metadata") or {}
    spec = manifest.get("spec") or {}
    description = str(spec.get("description") or metadata.get("description") or metadata.get("name") or "MAS agent")
    name = str(metadata.get("name") or "mas-agent")
    version = str(metadata.get("version") or "0.1.0")
    skills: list[AgentSkill] = []
    for index, raw_skill in enumerate(spec.get("skills") or []):
        if isinstance(raw_skill, str):
            skill_name = raw_skill
            skill_description = raw_skill
        elif isinstance(raw_skill, dict):
            skill_name = str(raw_skill.get("name") or raw_skill.get("id") or f"skill-{index + 1}")
            skill_description = str(raw_skill.get("description") or skill_name)
        else:
            continue
        skills.append(
            AgentSkill(
                id=skill_name,
                name=skill_name,
                description=skill_description,
                tags=[skill_name],
                input_modes=["text/plain"],
                output_modes=["text/plain"],
            )
        )
    if not skills:
        skills.append(
            AgentSkill(
                id=name,
                name=name,
                description=description,
                tags=["general"],
                input_modes=["text/plain"],
                output_modes=["text/plain"],
            )
        )
    provider_spec = spec.get("provider") or {}
    organization = str(provider_spec.get("organization") or "MAS Lab")
    capability_spec = capabilities or {}
    interfaces = [
        AgentInterface(url=url, protocol_binding="JSONRPC", protocol_version="1.0"),
        AgentInterface(
            url=f"{url.rstrip('/')}/a2a/rest",
            protocol_binding="HTTP+JSON",
            protocol_version="1.0",
        ),
    ]
    if grpc_url:
        interfaces.append(
            AgentInterface(
                url=grpc_url,
                protocol_binding="GRPC",
                protocol_version="1.0",
            )
        )

    return AgentCard(
        name=name,
        description=description,
        version=version,
        supported_interfaces=interfaces,
        provider=AgentProvider(
            url=str(provider_spec.get("url") or ""),
            organization=organization,
        ),
        capabilities=AgentCapabilities(
            streaming=bool(capability_spec.get("streaming", False)),
            push_notifications=bool(capability_spec.get("pushNotifications", False)),
            extended_agent_card=bool(capability_spec.get("extendedAgentCard", False)),
            extensions=list(capability_spec.get("extensions") or []),
        ),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=skills,
    )
