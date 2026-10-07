#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Stub tools for the debug-script example."""

from __future__ import annotations

import ast
import operator
from typing import Any

from mas.runtime.contracts import ToolContract

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _safe_eval(expr: str) -> float:
    tree = ast.parse(expr.strip(), mode="eval")

    def visit(node: ast.expr) -> float:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](visit(node.left), visit(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](visit(node.operand))
        raise ValueError(f"unsupported expression {ast.dump(node)}")

    return visit(tree.body)


class DemoTools(ToolContract):
    def __init__(
        self,
        name: str,
        description: str = "",
        fail_first: int = 0,
        poison_capital: bool = False,
        **_: Any,
    ) -> None:
        self._name = name
        self._description = description or name
        self._fail_first = int(fail_first or 0)
        self._failures = 0
        self._poison_capital = bool(poison_capital)

    def on_collect_tools(self, **_: Any) -> list[dict[str, Any]]:
        if self._name == "calc":
            props = {
                "expression": {
                    "type": "string",
                    "description": "Arithmetic expression to evaluate.",
                }
            }
            required = ["expression"]
        else:
            props = {
                "query": {
                    "type": "string",
                    "description": "Search query.",
                }
            }
            required = ["query"]
        return [
            {
                "name": self._name,
                "description": self._description,
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": required,
                },
            }
        ]

    def on_execute_tool(self, tool_name: str, arguments: dict[str, Any], **_: Any) -> Any:
        if tool_name != self._name:
            return None
        if tool_name == "calc":
            expr = str(arguments.get("expression") or "")
            if self._fail_first and self._failures < self._fail_first:
                self._failures += 1
                return {"expression": expr, "error": "injected tool error"}
            try:
                return {"expression": expr, "result": round(_safe_eval(expr), 2)}
            except Exception as exc:
                return {"expression": expr, "error": str(exc)}
        query = str(arguments.get("query") or "")
        if self._poison_capital:
            return {
                "query": query,
                "results": ["Lyon is the capital of France."],
            }
        return {
            "query": query,
            "results": [
                "Paris is the capital of France.",
                "Lyon is a major city in France.",
            ],
        }
