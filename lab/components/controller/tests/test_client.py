#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Extended client tests with mocked socket."""
from __future__ import annotations

import json

import pytest

from mas.lab.controller.client import ControllerClient, start_daemon, wait_for_worker


class _FakeSocket:
    def __init__(self, response: dict):
        self._response = json.dumps(response).encode() + b"\n"
        self._sent = False

    def connect(self, _path):
        return None

    def settimeout(self, _t):
        return None

    def sendall(self, _data):
        self._sent = True

    def recv(self, _n):
        if not self._sent:
            return b""
        self._sent = False
        return self._response

    def close(self):
        return None


def test_client_call_success(temp_mas_home, monkeypatch):
    monkeypatch.setattr(
        "mas.lab.controller.client.socket.socket",
        lambda *a, **k: _FakeSocket({"result": {"status": "ok"}}),
    )
    client = ControllerClient()
    monkeypatch.setattr(client, "is_running", lambda: True)
    assert client.call("ping")["status"] == "ok"


def test_client_call_error(temp_mas_home, monkeypatch):
    monkeypatch.setattr(
        "mas.lab.controller.client.socket.socket",
        lambda *a, **k: _FakeSocket({"error": "boom"}),
    )
    client = ControllerClient()
    with pytest.raises(RuntimeError, match="boom"):
        client.call("status")


def test_client_is_running_true(temp_mas_home, monkeypatch):
    from mas.lab.controller import config as cfg

    sock = cfg.socket_path()
    sock.parent.mkdir(parents=True, exist_ok=True)
    sock.touch()
    monkeypatch.setattr(
        "mas.lab.controller.client.socket.socket",
        lambda *a, **k: _FakeSocket({"result": {"status": "ok"}}),
    )
    client = ControllerClient()
    assert client.is_running() is True


def test_start_daemon_foreground(temp_mas_home, monkeypatch):
    import mas.lab.controller.client as client_mod

    monkeypatch.setattr(client_mod.subprocess, "run", lambda *a, **k: None)
    start_daemon(foreground=True)


def test_ensure_running_auto_start(temp_mas_home, monkeypatch):
    import mas.lab.controller.client as client_mod

    started = {"v": False}

    def fake_start(**kw):
        started["v"] = True

    monkeypatch.setattr(client_mod, "start_daemon", fake_start)

    def fake_call(self, method, params=None, timeout=30.0):
        if method == "acquire_session":
            return {"ok": True}
        return {"status": "ok"} if method == "ping" else {}

    monkeypatch.setattr(client_mod.ControllerClient, "call", fake_call)
    monkeypatch.setattr(
        client_mod.ControllerClient,
        "is_running",
        lambda self: started["v"],
    )
    client = client_mod.ControllerClient()
    client.ensure_running(auto_start=True)
    assert started["v"]


def test_wait_for_worker_completes(temp_mas_home, monkeypatch):
    calls = {"n": 0}

    def fake_call(self, method, params=None, timeout=30.0):
        if method == "acquire_session":
            return {"ok": True}
        if method == "ping":
            return {"status": "ok"}
        calls["n"] += 1
        if calls["n"] > 1:
            return {"status": "completed", "exit_code": 0}
        return {"status": "running"}

    client = ControllerClient()
    monkeypatch.setattr(client, "ensure_running", lambda **kw: None)
    monkeypatch.setattr(client, "call", fake_call)
    monkeypatch.setattr("mas.lab.controller.client.ControllerClient", lambda: client)
    detail = wait_for_worker("w-1", timeout=5, poll=0.01)
    assert detail["status"] == "completed"


def test_client_is_running_false(temp_mas_home):
    client = ControllerClient()
    assert client.is_running() is False


def test_client_call_empty_response(temp_mas_home, monkeypatch):
    class _EmptySocket:
        def connect(self, _p):
            return None

        def settimeout(self, _t):
            return None

        def sendall(self, _d):
            return None

        def recv(self, _n):
            return b""

        def close(self):
            return None

    monkeypatch.setattr("mas.lab.controller.client.socket.socket", lambda *a, **k: _EmptySocket())
    client = ControllerClient()
    with pytest.raises(json.JSONDecodeError):
        client.call("ping")


def test_stop_daemon_not_running(temp_mas_home):
    import mas.lab.controller.client as client_mod

    assert client_mod.stop_daemon() is True


def test_stop_daemon_running(temp_mas_home, monkeypatch):
    import mas.lab.controller.client as client_mod
    from mas.lab.controller import config as cfg

    sock = cfg.socket_path()
    sock.parent.mkdir(parents=True, exist_ok=True)
    sock.touch()
    monkeypatch.setattr(
        client_mod.ControllerClient,
        "is_running",
        lambda self: True,
    )
    monkeypatch.setattr(client_mod.ControllerClient, "call", lambda self, *a, **k: None)
    assert client_mod.stop_daemon() is True


def test_start_daemon_detach(temp_mas_home, monkeypatch):
    import mas.lab.controller.client as client_mod

    called = {}

    def fake_popen(cmd, **kw):
        called["cmd"] = cmd
        return None

    monkeypatch.setattr(client_mod.subprocess, "Popen", fake_popen)
    start_daemon(detach=True)
    assert "mas.lab.controller.daemon" in called["cmd"]


def test_ensure_running_failure(temp_mas_home, monkeypatch):
    import mas.lab.controller.client as client_mod

    monkeypatch.setattr(client_mod, "start_daemon", lambda **kw: None)
    monkeypatch.setattr(client_mod.ControllerClient, "is_running", lambda self: False)
    client = ControllerClient()
    with pytest.raises(RuntimeError, match="failed to start"):
        client.ensure_running(auto_start=True)
