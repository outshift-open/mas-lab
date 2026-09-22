"""Scene loader — resolves the active incident fixture at module import time.

Resolution order:
1. ``artifacts/scene.yaml`` — sidecar written by the runner before each
   invocation (gitignored, never committed).  Format::

       incident_fixture: datasets/incidents/payment-async-timeout.yaml

   Path is relative to the ``sre-triage/`` root.

2. Built-in default: ``datasets/incidents/payment-async-timeout.yaml``.

How the runner sets the active incident
---------------------------------------
Each overlay declares the incident fixture in ``spec.params``::

    # overlays/baseline.yaml
    spec:
      params:
        incident_fixture: datasets/incidents/my-incident.yaml
      capabilities:
        ...

The demo server (``mas-lab demo``) extracts ``spec.params`` when loading the
overlay and writes ``artifacts/scene.yaml`` before launching agents.  This
propagation is implemented in ``_write_overlay_sidecar()`` in server.py.

The ``lab.yaml`` manifest is intentionally free of domain-specific fields —
``incident_fixture`` is overlay-owned, not lab-owned.

Tool usage
----------
Every tool in this package imports the singleton ``scene`` at the top level::

    from ._scene import scene

    svc = scene.match(kwargs["service"])   # None if not in this incident
    if svc:
        return scene.services[svc].metrics
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
except ImportError:  # yaml not available — fall back to JSON-only mode
    yaml = None  # type: ignore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
_TOOLS_DIR = Path(__file__).parent  # tools/
_SRE_ROOT = _TOOLS_DIR.parent  # app root
_SIDECAR = _SRE_ROOT / "scene.yaml"  # legacy runner location
_ARTIFACT_SIDECAR = _SRE_ROOT / "artifacts" / "scene.yaml"  # current runner location
_DEFAULT_FIXTURE = _SRE_ROOT / "datasets" / "incidents" / "payment-async-timeout.yaml"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
class ServiceScene:
    """Typed view of a single service entry in the incident fixture."""

    def __init__(self, key: str, data: Dict[str, Any], incident_time: datetime) -> None:
        self._key = key
        self._data = data
        self._t = incident_time
        self.rolled_back = False

    # --- alias matching --------------------------------------------------

    def matches(self, name: str) -> bool:
        """Return True if *name* matches the canonical key or any alias."""
        n = name.lower().replace("-", "_")
        k = self._key.lower().replace("-", "_")
        if n == k:
            return True
        for alias in self._data.get("aliases", []):
            if n == alias.lower().replace("-", "_"):
                return True
        return False

    # --- metric accessors ------------------------------------------------

    @property
    def metrics(self) -> Dict[str, Any]:
        return dict(self._data.get("metrics", {}))

    def named_metric(self, metric_name: str) -> Optional[Dict[str, Any]]:
        """Return a specific named metric from ``metrics.named``, or None."""
        named = self._data.get("metrics", {}).get("named", {})
        return named.get(metric_name)

    # --- health ----------------------------------------------------------

    @property
    def health(self) -> Dict[str, Any]:
        return dict(self._data.get("health", {}))

    # --- deployments (timestamps resolved from offsets) ------------------

    @property
    def deployments(self) -> List[Dict[str, Any]]:
        result = []
        for raw in self._data.get("deployments", []):
            d = dict(raw)
            d["deployed_at"] = self._resolve_ts(d)
            # clean up offset keys
            for k in (
                "deployed_minutes_before_incident",
                "deployed_hours_before_incident",
                "deployed_days_before_incident",
            ):
                d.pop(k, None)
            result.append(d)
        return result

    def _resolve_ts(self, d: Dict[str, Any]) -> str:
        if "deployed_minutes_before_incident" in d:
            return (
                self._t - timedelta(minutes=d["deployed_minutes_before_incident"])
            ).isoformat()
        if "deployed_hours_before_incident" in d:
            return (
                self._t - timedelta(hours=d["deployed_hours_before_incident"])
            ).isoformat()
        if "deployed_days_before_incident" in d:
            return (
                self._t - timedelta(days=d["deployed_days_before_incident"])
            ).isoformat()
        return self._t.isoformat()

    # --- logs ------------------------------------------------------------

    @property
    def logs(self) -> List[Dict[str, Any]]:
        entries = []
        for i, raw in enumerate(self._data.get("logs", [])):
            entries.append(
                {
                    "timestamp": (self._t - timedelta(seconds=i * 8)).isoformat(),
                    **raw,
                }
            )
        return entries

    # --- DB-specific -----------------------------------------------------

    @property
    def pg_stat_activity(self) -> Dict[str, Any]:
        return dict(self._data.get("pg_stat_activity", {}))

    @property
    def blocking(self) -> Dict[str, Any]:
        return dict(self._data.get("blocking", {}))

    @property
    def connection_pool(self) -> Dict[str, Any]:
        return dict(self._data.get("connection_pool", {}))

    # --- action results --------------------------------------------------

    @property
    def rollback(self) -> Dict[str, Any]:
        return dict(self._data.get("rollback", {}))

    def do_rollback(self) -> bool:
        if self.rolled_back:
            return False
        self.rolled_back = True
        return True


def _hash_float(service_name: str, field: str, lo: float, hi: float) -> float:
    """Return a deterministic float in [lo, hi) seeded from service name + field."""
    key = f"{service_name}:{field}".encode()
    seed = int(hashlib.md5(key).hexdigest()[:8], 16) / 0xFFFFFFFF
    return lo + seed * (hi - lo)


class NominalServiceScene:
    """Plausible nominal (healthy) data for a service NOT in the incident fixture.

    Returned by tools when they are called with an unknown service name.
    Data is deterministic (seeded from the service name hash) and deliberately
    shows a healthy, unimpacted service — no anomaly, no recent incident-correlated
    deployment, no errors.

    This is the correct fallback for fault-injection experiments: a fault that
    redirects an agent to query the wrong service should yield convincing
    "all-clear" data, not an error message that guides the agent back to the
    right service.
    """

    _INCIDENT_TIME = datetime.fromisoformat("2025-01-15T14:30:00")

    def __init__(self, service_name: str) -> None:
        self._name = service_name

    def _f(self, field: str, lo: float, hi: float) -> float:
        return _hash_float(self._name, field, lo, hi)

    @property
    def metrics(self) -> Dict[str, Any]:
        return {
            "latency_ms": {
                "p50": round(self._f("lat_p50", 18.0, 52.0), 1),
                "p95": round(self._f("lat_p95", 55.0, 98.0), 1),
                "p99": round(self._f("lat_p99", 78.0, 140.0), 1),
            },
            "error_rate": round(self._f("err_rate", 0.0002, 0.0018), 4),
            "requests_per_second": round(self._f("rps", 40.0, 120.0), 1),
        }

    @property
    def health(self) -> Dict[str, Any]:
        return {
            "status": "healthy",
            "uptime_percent": round(self._f("uptime", 99.90, 99.99), 3),
            "error_rate_percent": round(self._f("health_err", 0.02, 0.12), 3),
            "dependencies": {},
        }

    @property
    def deployments(self) -> List[Dict[str, Any]]:
        days_ago = 3 + int(self._f("deploy_age", 0, 10))
        ts = (self._INCIDENT_TIME - timedelta(days=days_ago)).isoformat()
        ver_minor = int(self._f("ver_minor", 0, 9))
        ver_patch = int(self._f("ver_patch", 0, 19))
        sha = hex(int(self._f("sha", 0, 0xFFFFFF)))[2:9]
        dur = int(self._f("deploy_dur", 60, 150))
        return [
            {
                "version": f"2.{ver_minor}.{ver_patch}",
                "status": "success",
                "deployed_at": ts,
                "deployed_by": "ci/cd-pipeline",
                "commit_sha": sha,
                "commit_message": "chore: dependency updates and maintenance",
                "duration_seconds": dur,
                "overlap_with_incident": False,
            }
        ]

    @property
    def logs(self) -> List[Dict[str, Any]]:
        t = self._INCIDENT_TIME
        return [
            {
                "timestamp": (t - timedelta(minutes=i * 5)).isoformat(),
                "level": "INFO",
                "message": f"[{self._name}] Health check passed. Latency nominal.",
            }
            for i in range(3)
        ]

    def query_db(self, query_type: str = "pg_stat_activity") -> Dict[str, Any]:
        """Return healthy database diagnostic data for any query_type."""
        total = int(self._f("db_total_conn", 15, 45))
        active = int(self._f("db_active", 3, 12))
        idle = total - active
        if query_type in ("blocking_queries", "deadlocks"):
            return {
                "blocking_pids": [],
                "blocked_pids": [],
                "deadlocks_last_hour": 0,
                "lock_wait_count_last_hour": 0,
                "conclusion": "No blocking chain detected.",
            }
        if query_type == "connection_pool":
            return {
                "pool_size": 100,
                "active": active,
                "idle": 100 - active,
                "waiting": 0,
                "utilisation_pct": round(active, 1),
                "status": "healthy",
                "note": "Connection pool within normal range.",
            }
        # default: pg_stat_activity
        return {
            "total_connections": total,
            "max_connections": 200,
            "active_queries": active,
            "idle_connections": idle,
            "waiting_queries": 0,
            "blocking_queries": [],
            "longest_running_query_seconds": round(
                self._f("db_longest_q", 0.05, 0.4), 2
            ),
            "max_lock_wait_ms": round(self._f("db_lock_wait", 0.5, 5.0), 1),
            "conclusion": "No blocking queries detected. Database is healthy.",
        }

    def named_metric(self, metric_name: str) -> Optional[Dict[str, Any]]:
        """Return a plausible nominal value for any named metric."""
        val = round(self._f(f"named_{metric_name}", 1.0, 8.0), 1)
        return {"value": val, "unit": "count", "status": "normal"}


class IncidentScene:
    """Top-level incident fixture, loaded once at import time."""

    def __init__(self, fixture_path: Path) -> None:
        raw = _load_yaml(fixture_path)
        self.id: str = raw.get("id", "unknown")
        self.description: str = raw.get("description", "")
        self.correct_action: Dict[str, Any] = raw.get("correct_action", {})

        ts_str: str = raw.get("timestamp", "2025-01-15T14:30:00")
        self._incident_time = datetime.fromisoformat(ts_str)

        self.services: Dict[str, ServiceScene] = {
            key: ServiceScene(key, svc_data, self._incident_time)
            for key, svc_data in raw.get("services", {}).items()
        }
        logger.debug("Scene loaded: %s (%d services)", self.id, len(self.services))

    @property
    def incident_time(self) -> datetime:
        return self._incident_time

    def match(self, service_name: str) -> Optional[str]:
        """Return the canonical service key that matches *service_name*, or None."""
        for key, svc in self.services.items():
            if svc.matches(service_name):
                return key
        return None


# ---------------------------------------------------------------------------
# YAML loader (handles missing yaml gracefully)
# ---------------------------------------------------------------------------
def _load_yaml(path: Path) -> Dict[str, Any]:
    if yaml is None:
        raise ImportError(
            "PyYAML is required for scene loading. "
            "Install with: uv pip install pyyaml"
        )
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


# ---------------------------------------------------------------------------
# Fixture resolution
# ---------------------------------------------------------------------------
def _sidecar_candidates() -> list[Path]:
    """Return scene sidecar paths in priority order.

    Preference is for run-scoped sidecars. App-local sidecars are included
    only as a last resort because they are easy to leave stale across runs.
    """
    candidates: list[Path] = []

    # Primary runtime contract: explicit artifact root from runner.
    artifacts_root = os.environ.get("MAS_RUNTIME_ARTIFACTS_DIR")
    if artifacts_root:
        root = Path(artifacts_root)
        candidates.append(root / "artifacts" / "scene.yaml")
        candidates.append(root / "scene.yaml")

    # Alternate runtime hints used by different executors.
    for env_name in ("MAS_TRACE_DIR", "MAS_RUNTIME_DIR", "MAS_ARTIFACTS_DIR"):
        hinted = os.environ.get(env_name)
        if not hinted:
            continue
        root = Path(hinted)
        candidates.append(root / "artifacts" / "scene.yaml")
        candidates.append(root / "scene.yaml")

    # Run-local discovery: walk cwd -> parents for run layouts.
    for base in [Path.cwd(), *Path.cwd().parents]:
        candidates.append(base / "artifacts" / "scene.yaml")
        candidates.append(base / "scene.yaml")
        traces_link = base / "traces"
        if traces_link.exists():
            try:
                trace_root = traces_link.resolve().parent
                candidates.append(trace_root / "artifacts" / "scene.yaml")
                candidates.append(trace_root / "scene.yaml")
            except Exception:  # noqa: BLE001
                pass

    # Last resort: app-level sidecars.
    candidates.extend([_ARTIFACT_SIDECAR, _SIDECAR])

    # De-duplicate while preserving order.
    seen: set[Path] = set()
    ordered: list[Path] = []
    for p in candidates:
        rp = p.resolve() if p.is_absolute() else (Path.cwd() / p).resolve()
        if rp in seen:
            continue
        seen.add(rp)
        ordered.append(rp)
    return ordered


def _resolve_fixture_path() -> Path:
    """Return the path to the active incident fixture.

    1. Read the runner sidecar for ``incident_fixture:`` key.
    2. If no sidecar can be resolved, optionally fall back to default fixture
       only when MAS_ALLOW_DEFAULT_FIXTURE=true.
    """
    searched: list[str] = []
    for sidecar_path in _sidecar_candidates():
        searched.append(str(sidecar_path))
        if not sidecar_path.exists():
            continue
        try:
            sidecar = _load_yaml(sidecar_path)
            rel = sidecar.get("incident_fixture")
            if rel:
                candidate = (_SRE_ROOT / rel).resolve()
                if candidate.exists():
                    logger.debug(
                        "Scene fixture from sidecar %s: %s", sidecar_path, candidate
                    )
                    return candidate
                logger.warning("Scene sidecar points to missing file: %s", candidate)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to read scene sidecar %s: %s", sidecar_path, exc)

    if os.environ.get("MAS_ALLOW_DEFAULT_FIXTURE", "").lower() in {"1", "true", "yes"}:
        logger.warning(
            "Scene fixture sidecar unresolved; using default fixture %s (MAS_ALLOW_DEFAULT_FIXTURE=true)",
            _DEFAULT_FIXTURE,
        )
        return _DEFAULT_FIXTURE

    raise FileNotFoundError(
        "Unable to resolve incident fixture sidecar. "
        "Set MAS_RUNTIME_ARTIFACTS_DIR (recommended), or set MAS_ALLOW_DEFAULT_FIXTURE=true "
        "to allow fallback. Searched: " + "; ".join(searched)
    )
