#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""File-backed session directory for the control-protocol plugin.

The directory is the trust boundary: anyone who can read it can present
the attach token. This is not a consensus service and not A2A.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


@dataclass(frozen=True)
class SessionAdvertisement:
    session_id: str
    rpc: str
    persist_path: str = ""
    pid: int = 0
    heartbeat_at: str = ""
    token: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionAdvertisement:
        return cls(
            session_id=str(data.get("session_id") or ""),
            rpc=str(data.get("rpc") or ""),
            persist_path=str(data.get("persist_path") or ""),
            pid=int(data.get("pid") or 0),
            heartbeat_at=str(data.get("heartbeat_at") or ""),
            token=str(data.get("token") or ""),
        )


@dataclass
class FileSessionDirectory:
    root: Path
    ttl: timedelta = field(default_factory=lambda: timedelta(seconds=5))

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)

    def advertise(self, advertisement: SessionAdvertisement) -> SessionAdvertisement:
        if not advertisement.session_id:
            raise ValueError("session_id is required")
        if not advertisement.rpc:
            raise ValueError("rpc endpoint is required")
        payload = advertisement.as_dict()
        if not payload["heartbeat_at"]:
            payload["heartbeat_at"] = _utc_now().isoformat()
        if not payload["pid"]:
            payload["pid"] = os.getpid()
        written = SessionAdvertisement.from_dict(payload)
        path = self._path(written.session_id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(written.as_dict(), indent=2), encoding="utf-8")
        tmp.replace(path)
        return written

    def heartbeat(self, session_id: str) -> SessionAdvertisement:
        current = self.lookup(session_id)
        if current is None:
            raise KeyError(f"unknown session {session_id!r}")
        return self.advertise(
            SessionAdvertisement(
                session_id=current.session_id,
                rpc=current.rpc,
                persist_path=current.persist_path,
                pid=current.pid or os.getpid(),
                heartbeat_at=_utc_now().isoformat(),
                token=current.token,
            )
        )

    def lookup(self, session_id: str) -> SessionAdvertisement | None:
        path = self._path(session_id)
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        return SessionAdvertisement.from_dict(data)

    def unadvertise(self, session_id: str) -> None:
        path = self._path(session_id)
        if path.exists():
            path.unlink()

    def is_live(self, session_id: str) -> bool:
        advertisement = self.lookup(session_id)
        if advertisement is None:
            return False
        if not self._heartbeat_fresh(advertisement):
            return False
        return pid_alive(advertisement.pid)

    def _heartbeat_fresh(self, advertisement: SessionAdvertisement) -> bool:
        if not advertisement.heartbeat_at:
            return False
        try:
            stamped = _parse_time(advertisement.heartbeat_at)
        except ValueError:
            return False
        if stamped.tzinfo is None:
            stamped = stamped.replace(tzinfo=UTC)
        return (_utc_now() - stamped) <= self.ttl

    def _path(self, session_id: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_." else "-" for c in session_id)
        if not safe or safe.startswith("."):
            raise ValueError(f"invalid session_id {session_id!r}")
        return self.root / f"{safe}.json"
