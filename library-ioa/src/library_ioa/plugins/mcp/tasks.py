#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Production MCP Tasks extension for long-running tool calls."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from mcp.server.extension import Extension, MethodBinding
from mcp.shared.exceptions import MCPError
from mcp.types import (
    CallToolRequestParams,
    CancelTaskRequestParams,
    GetTaskRequestParams,
    InputRequiredResult,
    RequestParams,
)
from pydantic import ConfigDict, Field

TASKS_EXTENSION = "io.modelcontextprotocol/tasks"


class UpdateTaskParams(RequestParams):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    task_id: str = Field(alias="taskId")
    input_responses: dict[str, Any] = Field(alias="inputResponses")


@dataclass
class TaskRecord:
    task_id: str
    name: str
    arguments: dict[str, Any]
    status: str = "working"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z"))
    last_updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z"))
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    input_requests: dict[str, Any] | None = None
    runner: asyncio.Task[None] | None = None


def elicit_request(message: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "method": "elicitation/create",
        "params": {
            "message": message,
            "requestedSchema": {"type": "object", "properties": properties, "required": required},
        },
    }


def input_required(
    input_requests: dict[str, dict[str, Any]], request_state: dict[str, Any] | None = None
) -> InputRequiredResult:
    payload: dict[str, Any] = {"resultType": "input_required", "inputRequests": input_requests}
    if request_state is not None:
        import json

        payload["requestState"] = json.dumps(request_state, separators=(",", ":"))
    return InputRequiredResult.model_validate(payload)


class MCPTasksExtension(Extension):
    """Implement the MCP Tasks extension for configured tool names.

    The extension owns task lifecycle state and delegates task completion to an
    optional callback. The callback receives ``(record, delay)`` and may fill
    ``record.result`` or ``record.error`` before marking it complete.
    """

    identifier = TASKS_EXTENSION

    def __init__(
        self,
        task_tools: dict[str, str],
        *,
        finish: Any | None = None,
        input_requests: Any | None = None,
    ) -> None:
        self.task_tools = dict(task_tools)
        self._finish_callback = finish
        self._input_requests_callback = input_requests
        self._tasks: dict[str, TaskRecord] = {}

    def methods(self) -> tuple[MethodBinding, ...]:
        versions = frozenset({"2026-07-28"})
        return (
            MethodBinding("tasks/get", GetTaskRequestParams, self._get, versions),
            MethodBinding("tasks/update", UpdateTaskParams, self._update, versions),
            MethodBinding("tasks/cancel", CancelTaskRequestParams, self._cancel, versions),
        )

    @staticmethod
    def _negotiated(ctx: Any) -> bool:
        capabilities = ctx.session.client_capabilities
        return bool(capabilities and capabilities.extensions and TASKS_EXTENSION in capabilities.extensions)

    @staticmethod
    def _ack() -> dict[str, Any]:
        return {"resultType": "complete"}

    @staticmethod
    def _task_fields(record: TaskRecord) -> dict[str, Any]:
        return {
            "taskId": record.task_id,
            "status": record.status,
            "createdAt": record.created_at,
            "lastUpdatedAt": record.last_updated_at,
            "ttlMs": 60_000,
            "pollIntervalMs": 50,
        }

    def _detailed(self, record: TaskRecord) -> dict[str, Any]:
        response = {"resultType": "complete", **self._task_fields(record)}
        if record.result is not None:
            response["result"] = record.result
        if record.error is not None:
            response["error"] = record.error
        if record.input_requests is not None:
            response["inputRequests"] = record.input_requests
        return response

    def _require_tasks(self, ctx: Any) -> None:
        if not self._negotiated(ctx):
            raise MCPError(
                code=-32021,
                message="Missing required client capability",
                data={"requiredCapabilities": {"extensions": {TASKS_EXTENSION: {}}}},
            )

    def _record(self, task_id: str) -> TaskRecord:
        try:
            return self._tasks[task_id]
        except KeyError:
            raise MCPError(code=-32602, message="Unknown taskId", data={"taskId": task_id}) from None

    async def _finish(self, record: TaskRecord, delay: float) -> None:
        try:
            await asyncio.sleep(min(delay, 0.2))
            if record.status == "cancelled":
                return
            if self._finish_callback is not None:
                await self._finish_callback(record, delay)
            if record.status == "working":
                label = str(record.arguments.get("label") or record.arguments.get("user_name") or "result")
                record.status = "completed"
                record.result = {
                    "resultType": "complete",
                    "content": [{"type": "text", "text": f"Computed {label}"}],
                    "isError": False,
                }
            record.last_updated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        except asyncio.CancelledError:
            record.status = "cancelled"
            record.last_updated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")

    async def intercept_tool_call(self, params: CallToolRequestParams, ctx: Any, call_next: Any) -> Any:
        task_support = self.task_tools.get(params.name)
        if task_support is None:
            return await call_next(ctx)
        if not self._negotiated(ctx):
            if task_support == "required":
                self._require_tasks(ctx)
            return await call_next(ctx)

        arguments = params.arguments or {}
        if self._input_requests_callback is not None:
            pending = self._input_requests_callback(params, arguments)
            if pending is not None:
                return pending
        record = TaskRecord(task_id=str(uuid4()), name=params.name, arguments=arguments)
        self._tasks[record.task_id] = record
        if params.name == "confirm_delete":
            record.status = "input_required"
            record.input_requests = {
                "confirm": elicit_request(
                    f"Confirm deletion of {record.arguments.get('filename', 'file')}",
                    {"confirm": {"type": "boolean"}},
                    ["confirm"],
                )
            }
        elif params.name == "multi_input":
            record.status = "input_required"
            record.input_requests = {
                "first": elicit_request("First input", {"name": {"type": "string"}}, ["name"]),
                "second": elicit_request("Second input", {"confirm": {"type": "boolean"}}, ["confirm"]),
            }
        else:
            delay = float(record.arguments.get("seconds", 0.05))
            record.runner = asyncio.create_task(self._finish(record, delay))
        return {"resultType": "task", "content": [], **self._task_fields(record)}

    async def _get(self, ctx: Any, params: GetTaskRequestParams) -> dict[str, Any]:
        self._require_tasks(ctx)
        return self._detailed(self._record(params.task_id))

    async def _update(self, ctx: Any, params: UpdateTaskParams) -> dict[str, Any]:
        self._require_tasks(ctx)
        record = self._record(params.task_id)
        if record.status == "input_required" and record.input_requests is not None:
            for key in params.input_responses:
                record.input_requests.pop(key, None)
            if not record.input_requests:
                record.input_requests = None
                record.status = "completed"
                record.result = {
                    "resultType": "complete",
                    "content": [{"type": "text", "text": "Input accepted"}],
                    "isError": False,
                }
            record.last_updated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        return self._ack()

    async def _cancel(self, ctx: Any, params: CancelTaskRequestParams) -> dict[str, Any]:
        self._require_tasks(ctx)
        record = self._record(params.task_id)
        if record.status not in {"completed", "failed", "cancelled"}:
            record.status = "cancelled"
            record.last_updated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            if record.runner is not None:
                record.runner.cancel()
        return self._ack()
