#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from mas.library.eval.metrics.llm_json import complete_json, extract_json_object


def test_extract_json_object_from_fence() -> None:
    parsed = extract_json_object('```json\n{"ok": true}\n```')
    assert parsed == {"ok": True}


class _ScriptedHandler(BaseHTTPRequestHandler):
    script: list[object] = []
    calls = 0

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        type(self).calls += 1
        item = self.script[min(self.calls - 1, len(self.script) - 1)]
        if item == "error":
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'{"error":"boom"}')
            return
        if item == "malformed":
            content = "not-json"
        else:
            content = json.dumps(item)
        body = json.dumps({"choices": [{"message": {"content": content}}]}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def openai_server():
    server = HTTPServer(("127.0.0.1", 0), _ScriptedHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    yield f"http://127.0.0.1:{port}/v1", _ScriptedHandler
    server.shutdown()
    thread.join(timeout=2)


def test_complete_json_retries_malformed(openai_server, monkeypatch) -> None:
    from openai import OpenAI

    base_url, handler = openai_server
    handler.script = ["malformed", {"label": "ok"}]
    handler.calls = 0
    client = OpenAI(api_key="test-key", base_url=base_url)
    monkeypatch.setattr("mas.library.eval.mce.runner.get_openai_client", lambda: client)
    monkeypatch.setattr(
        "mas.library.eval.mce.runner.get_effective_judge_model",
        lambda: "test-model",
    )
    parsed = complete_json(
        [{"role": "user", "content": "return json"}],
        retries=2,
    )
    assert parsed == {"label": "ok"}
    assert handler.calls == 2
