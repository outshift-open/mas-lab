#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""HTTP client helpers for live LLM calls — TLS verification and error classification."""

from __future__ import annotations

import logging
import os
import ssl
import sys
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _macos_install_certificates_hint() -> str:
    for base in (Path(sys.prefix), Path(sys.base_prefix)):
        cmd = base / "Install Certificates.command"
        if cmd.is_file():
            return f"Run: {cmd}"
    return "Run Install Certificates.command from your Python folder."


def _system_ssl_context() -> ssl.SSLContext | None:
    """Use OS trust store (macOS Keychain, Windows cert store) when available."""
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return None


def _default_ca_bundle() -> str | None:
    """Prefer certifi PEM path; fall back to common platform bundle locations."""
    for env_key in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "MAS_LLM_CA_BUNDLE"):
        raw = os.environ.get(env_key, "").strip()
        if raw and Path(raw).is_file():
            return raw
    try:
        import certifi

        path = certifi.where()
        if Path(path).is_file():
            return path
    except ImportError:
        pass
    if sys.platform == "darwin":
        for candidate in (
            "/etc/ssl/cert.pem",
            "/private/etc/ssl/cert.pem",
            "/usr/local/etc/openssl@3/cert.pem",
        ):
            if Path(candidate).is_file():
                return candidate
    return None


def resolve_ssl_verify(llm_proxy: dict[str, Any] | None = None) -> bool | str | ssl.SSLContext:
    """Return httpx ``verify`` argument: SSLContext, CA bundle path, or False."""
    env = os.environ.get("MAS_LLM_VERIFY_SSL", "").strip().lower()
    if env in ("0", "false", "no", "off"):
        logger.warning("MAS_LLM_VERIFY_SSL disables TLS certificate verification (dev only)")
        return False

    proxy = llm_proxy or {}
    if proxy.get("verify_ssl") is False:
        logger.warning("infra llm_proxy.verify_ssl=false — TLS verification disabled")
        return False

    for key in ("ca_bundle",):
        raw = proxy.get(key)
        if raw:
            path = str(raw)
            ctx = _system_ssl_context()
            if ctx is not None:
                ctx.load_verify_locations(cafile=path)
                return ctx
            return path

    ctx = _system_ssl_context()
    if ctx is not None:
        return ctx

    bundle = _default_ca_bundle()
    if bundle:
        return bundle

    logger.warning(
        "No CA bundle found (install truststore + certifi). "
        "Falling back to httpx default verification."
    )
    return True


def _extract_api_error_message(response: Any) -> str:
    """Best-effort parse of OpenAI/LiteLLM JSON error bodies."""
    with __import__("contextlib").suppress(Exception):
        data = response.json()
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict):
                msg = err.get("message")
                if isinstance(msg, str) and msg.strip():
                    return msg.strip()
            msg = data.get("message")
            if isinstance(msg, str) and msg.strip():
                return msg.strip()
    with __import__("contextlib").suppress(Exception):
        text = response.text.strip()
        if text:
            return text[:500]
    return ""


def classify_llm_http_error(exc: BaseException) -> str:
    """Map transport/HTTP failures to a short, actionable operator message."""
    import httpx

    if is_tls_verify_failure(exc):
        return (
            "LLM request failed: TLS certificate verification failed. "
            "Use the repo .venv (`task install-dev`, `direnv allow`). "
            "For corporate proxies set SSL_CERT_FILE or spec.infra llm_proxy.ca_bundle. "
            f"On macOS CPython you may also { _macos_install_certificates_hint()}. "
            "Dev-only escape hatch: MAS_LLM_VERIFY_SSL=0."
        )

    if isinstance(exc, ssl.SSLError) or any(
        marker in str(exc) for marker in _TRANSIENT_MARKERS
    ):
        return (
            "LLM request failed: TLS/connection dropped "
            f"({exc}). This is a transient socket error, not a certificate failure."
        )

    if isinstance(exc, httpx.ConnectError):
        exc_text = str(exc)
        if "Connection refused" in exc_text or "Name or service not known" in exc_text:
            return f"LLM request failed: cannot reach API ({exc}). Check api_base and network."
        return f"LLM request failed: connection error ({exc})."

    if isinstance(exc, httpx.TimeoutException):
        return "LLM request failed: request timed out. Retry or increase the client timeout."

    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        detail = _extract_api_error_message(exc.response)
        detail_hint = f": {detail}" if detail else ""

        if status in (401, 403):
            return (
                f"LLM request failed: HTTP {status} (authentication/authorization){detail_hint}. "
                "Check the API key env var named in your infra manifest (api_key_env). "
                "Ensure config.yaml infra_refs selects the correct bundle "
                "(e.g. standard:llm-proxy vs standard:production)."
            )
        if status == 429:
            return f"LLM request failed: HTTP 429 rate limit{detail_hint}."
        if status >= 500:
            return f"LLM request failed: HTTP {status} from LLM provider{detail_hint}."
        if "ExceededBudget" in detail or "budget_exceeded" in detail.lower():
            return (
                f"LLM request failed: proxy budget exceeded{detail_hint}. "
                "Contact your LLM proxy admin or use another infra bundle "
                "(e.g. mas-ctl chat --infra-ref standard:openai with OPENAI_API_KEY, "
                "or llm_cache replay with raise_on_miss for offline testing)."
            )
        return f"LLM request failed: HTTP {status}{detail_hint}"

    return f"LLM request failed: {exc}"


_RETRYABLE_STATUS = frozenset({429, 502, 503, 504})
_TRANSIENT_MARKERS = (
    "UNEXPECTED_EOF",
    "UNEXPECTED_EOF_WHILE_READING",
    "Connection reset",
    "Connection aborted",
    "ECONNRESET",
    "Server disconnected",
    "Remote end closed connection",
    "broken pipe",
)


def _iter_exception_chain(exc: BaseException) -> list[BaseException]:
    seen: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and current not in seen:
        seen.append(current)
        current = current.__cause__ or current.__context__
    return seen


def is_tls_verify_failure(exc: BaseException) -> bool:
    """True only for certificate verification failures, not dropped TLS sockets."""
    for err in _iter_exception_chain(exc):
        if isinstance(err, ssl.SSLCertVerificationError):
            return True
        text = str(err)
        if any(
            marker in text
            for marker in (
                "CERTIFICATE_VERIFY_FAILED",
                "certificate verify failed",
                "SSL: CERTIFICATE",
            )
        ):
            return True
    return False


def is_retryable_llm_http_error(exc: BaseException) -> bool:
    """Transient transport / overload errors that a second POST can recover from.

    Certificate verification failures are never retried — they will not heal
    without a config change.
    """
    import httpx

    if is_tls_verify_failure(exc):
        return False
    if isinstance(
        exc,
        (
            httpx.ConnectError,
            httpx.TimeoutException,
            httpx.RemoteProtocolError,
            httpx.ReadError,
            httpx.WriteError,
            httpx.PoolTimeout,
        ),
    ):
        return True
    if isinstance(exc, ssl.SSLError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS
    text = str(exc)
    return any(marker in text for marker in _TRANSIENT_MARKERS)


def _retry_budget() -> tuple[int, float]:
    retries = int(os.environ.get("MAS_LLM_HTTP_RETRIES", "3") or "3")
    backoff = float(os.environ.get("MAS_LLM_HTTP_RETRY_BACKOFF", "0.5") or "0.5")
    return max(0, retries), max(0.05, backoff)


def request_with_retries(client: Any, method: str, url: str, **kwargs: Any) -> Any:
    """POST/GET with retries on dropped TLS sockets, timeouts, and 429/5xx."""
    retries, backoff = _retry_budget()
    last_exc: BaseException | None = None
    for attempt in range(retries + 1):
        try:
            resp = client.request(method, url, **kwargs)
            if resp.status_code in _RETRYABLE_STATUS and attempt < retries:
                logger.warning(
                    "LLM HTTP %s %s → %s; retry %s/%s",
                    method,
                    url,
                    resp.status_code,
                    attempt + 1,
                    retries,
                )
                time.sleep(backoff * (2**attempt))
                continue
            return resp
        except Exception as exc:
            last_exc = exc
            if attempt >= retries or not is_retryable_llm_http_error(exc):
                raise
            logger.warning(
                "LLM HTTP %s %s failed (%s); retry %s/%s",
                method,
                url,
                exc,
                attempt + 1,
                retries,
            )
            time.sleep(backoff * (2**attempt))
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("LLM HTTP retry exhausted")
