#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for LLM HTTP retry classification and the retrying request helper.

NOTE: is_retryable_llm_http_error()/request_with_retries() are not yet called
from the live LLM call path (mas.runtime.engine.llm_live._chat_completion goes
through an LLMProvider plugin, not an httpx client directly) -- this covers
the helpers' own boundary behavior in isolation.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
from mas.runtime.engine.llm_http import (
    is_retryable_llm_http_error,
    is_tls_verify_failure,
    request_with_retries,
)


def test_is_retryable_for_connect_and_timeout_errors():
    assert is_retryable_llm_http_error(httpx.ConnectError("boom")) is True
    assert is_retryable_llm_http_error(httpx.TimeoutException("boom")) is True


def test_is_retryable_for_5xx_and_429_status():
    for status in (429, 502, 503, 504):
        response = httpx.Response(status, request=httpx.Request("POST", "https://x"))
        exc = httpx.HTTPStatusError("boom", request=response.request, response=response)
        assert is_retryable_llm_http_error(exc) is True


def test_not_retryable_for_4xx_status():
    response = httpx.Response(400, request=httpx.Request("POST", "https://x"))
    exc = httpx.HTTPStatusError("boom", request=response.request, response=response)
    assert is_retryable_llm_http_error(exc) is False


def test_not_retryable_for_tls_verify_failure():
    exc = ssl_cert_error()
    assert is_tls_verify_failure(exc) is True
    assert is_retryable_llm_http_error(exc) is False


def test_retryable_for_transient_socket_markers():
    assert is_retryable_llm_http_error(RuntimeError("Connection reset by peer")) is True
    assert is_retryable_llm_http_error(RuntimeError("totally unrelated")) is False


def ssl_cert_error() -> Exception:
    import ssl

    return ssl.SSLCertVerificationError("certificate verify failed")


def test_request_with_retries_succeeds_after_transient_failures(monkeypatch):
    monkeypatch.setenv("MAS_LLM_HTTP_RETRIES", "3")
    monkeypatch.setenv("MAS_LLM_HTTP_RETRY_BACKOFF", "0.001")
    ok_response = MagicMock(status_code=200)
    client = MagicMock()
    client.request.side_effect = [httpx.ConnectError("boom"), httpx.ConnectError("boom"), ok_response]

    result = request_with_retries(client, "POST", "https://x")

    assert result is ok_response
    assert client.request.call_count == 3


def test_request_with_retries_gives_up_on_non_retryable_error(monkeypatch):
    monkeypatch.setenv("MAS_LLM_HTTP_RETRIES", "3")
    monkeypatch.setenv("MAS_LLM_HTTP_RETRY_BACKOFF", "0.001")
    client = MagicMock()
    client.request.side_effect = ValueError("not retryable")

    with pytest.raises(ValueError):
        request_with_retries(client, "POST", "https://x")

    assert client.request.call_count == 1


def test_request_with_retries_exhausts_budget_and_raises_last_error(monkeypatch):
    monkeypatch.setenv("MAS_LLM_HTTP_RETRIES", "2")
    monkeypatch.setenv("MAS_LLM_HTTP_RETRY_BACKOFF", "0.001")
    client = MagicMock()
    client.request.side_effect = httpx.TimeoutException("boom")

    with pytest.raises(httpx.TimeoutException):
        request_with_retries(client, "POST", "https://x")

    assert client.request.call_count == 3
