#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""System tool: request_human_input — agent-initiated HITL via side channel."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from mas.runtime.contracts.tool_contract import ToolContract


class RequestHumanInputTool(ToolContract):
    """Ask the user a question and wait for their response.

    This is a **system tool** that enables agents to explicitly request user input
    during their turn, without relying on governance-triggered HITL gates.

    Unlike `hitl_on_tool`, which is policy-driven, this tool gives the agent
    direct control over when and what to ask the user.

    **Architecture**: 
    - The tool emits an `EmitHitlRequest` to the kernel
    - The kernel pauses the agent's turn (but not the whole MAS round)
    - External systems (e.g., Webex bot) resolve the HITL via a side channel
    - The resolution flows back via `submit_hitl()` to this agent
    - The tool returns the user's response as its result

    **Distributed MAS compatibility**:
    - Works across delegation boundaries
    - HITL state propagates via dedicated side channel
    - Other agents can continue while one awaits user input

    Example usage in agent context:
    ```
    You can ask the user for approval by calling:
    request_human_input(
        question="Approve 20% discount for Acme renewal?",
        question_type="CONFIRM",
        choices=["approve", "reject"],
        context_data={"account": "Acme Corp", "discount": "20%"}
    )
    ```
    """

    class Input(BaseModel):
        question: str = Field(
            ...,
            description="The question to ask the user",
            min_length=1,
            max_length=2000,
        )
        question_type: str = Field(
            default="CONFIRM",
            description=(
                "Type of question: CONFIRM (yes/no), FREE_FORM (text), "
                "MULTIPLE_CHOICE (pick one), MULTI_SELECT (pick many), FORM (structured)"
            ),
        )
        choices: list[str] = Field(
            default_factory=list,
            description="Available choices for MULTIPLE_CHOICE or MULTI_SELECT questions",
        )
        context_data: dict[str, Any] = Field(
            default_factory=dict,
            description=(
                "Contextual data to display with the question "
                "(e.g., account details, proposed values)"
            ),
        )
        timeout: float | None = Field(
            default=None,
            description=(
                "Seconds to wait for the user's response before raising "
                "TimeoutError. Overrides the deployment's configured default "
                "for this one call. Omit (or the manifest default, if any is "
                "set) to wait indefinitely."
            ),
            ge=0,
        )

    def get_name(self) -> str:
        return "request_human_input"

    def get_description(self) -> str:
        return (
            "Ask the user a question and wait for their response. "
            "Use this when you need explicit user approval, feedback, or input "
            "before proceeding with an action. "
            "The question will be presented to the user in a structured way, "
            "and their response will be returned as the tool result."
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Execute the HITL request by emitting it to the kernel.

        The actual execution flow:
        1. Validate arguments via Input model
        2. Emit EmitHitlRequest to kernel (side channel, not tool return)
        3. Kernel pauses agent's turn and returns DriverTrace with awaiting_hitl=True
        4. External resolver (Webex bot) detects pending HITL and posts question
        5. User responds via UI action (adaptive card button click)
        6. Resolver calls session.resolve_hitl(choice, steering)
        7. Kernel resumes agent's turn
        8. This tool "returns" the user's response

        For now, we raise a sentinel exception that the kernel will catch
        and convert to EmitHitlRequest. The actual response will come from
        the HITL resolution flow.
        """
        args = self.Input(**kwargs)

        # Map question_type string to HitlQuestionType enum
        from mas.runtime.schema.hitl import HitlQuestionType

        question_type_map = {
            "CONFIRM": HitlQuestionType.CONFIRM,
            "FREE_FORM": HitlQuestionType.FREE_FORM,
            "MULTIPLE_CHOICE": HitlQuestionType.MULTIPLE_CHOICE,
            "MULTI_SELECT": HitlQuestionType.MULTI_SELECT,
            "FORM": HitlQuestionType.FORM,
        }
        qt = question_type_map.get(args.question_type.upper(), HitlQuestionType.CONFIRM)

        # Build HITL request payload
        # This will be caught by the tool execution layer and converted to EmitHitlRequest
        from mas.runtime.system_tools.signal import RequestHitlSignal

        raise RequestHitlSignal(
            question=args.question,
            question_type=qt,
            choices=list(args.choices) if args.choices else [],
            context_data=dict(args.context_data) if args.context_data else {},
            timeout=args.timeout,
        )
