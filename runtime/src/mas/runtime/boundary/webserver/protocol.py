from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


class WebServerHandle(Protocol):
    def close(self) -> None: ...


@runtime_checkable
class WebServerContract(Protocol):
    """Serve an application through a runtime-selected webserver plugin."""

    def serve_blocking(self, app: Any, *, host: str, port: int) -> None: ...

    def serve_background(self, app: Any, *, host: str, port: int) -> WebServerHandle: ...
