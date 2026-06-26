#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mas.library.standard.mock_llm import load_cache, lookup_response, resolve_cache_path


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: Dict[str, Any]) -> None:
    data = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


class MockLLMHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            _json_response(self, 200, {"status": "ok"})
            return
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            payload = {}
        model = str(payload.get("model", "mock"))
        messages = payload.get("messages") if isinstance(payload.get("messages"), list) else []

        cache_path = resolve_cache_path()
        cache = load_cache(cache_path)
        content, usage, source = lookup_response(cache, model, messages)
        if not content:
            content = "Mock response missing from cache."
        usage_payload = usage if isinstance(usage, dict) else {}

        response = {
            "id": "mock-llm",
            "object": "chat.completion",
            "created": int(os.path.getmtime(cache_path)) if cache_path.exists() else 0,
            "model": model if source == model else "mock",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": usage_payload,
        }
        _json_response(self, 200, response)


def main() -> None:
    host = os.getenv("MOCK_LLM_HOST", "0.0.0.0")
    port = int(os.getenv("MOCK_LLM_PORT", "12000"))
    server = ThreadingHTTPServer((host, port), MockLLMHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
