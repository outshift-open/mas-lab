#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""EvalFixtureStep — generic fixture-driven evaluation for benchmark runs.

This step scores each per-run trace against a supplied fixture document.
The scoring mechanics are intentionally generic:
- completion: did the run reach an accepted terminal response?
- verification gate: was a verifier tool called and approved?
- primary action: did the selected ``run_action`` match the fixture's
  expected service/action pair?
- secondary action: did the trace contain an optional bonus action?

The concrete semantics are driven entirely by configuration and fixture
content; no SRE-specific paths are baked into the implementation.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from mas.lab.benchmark.pipeline import PipelineStep, StepOutput
from mas.lab.benchmark.pipeline.executor import ExecutionContext

logger = logging.getLogger(__name__)

_DEFAULT_OUTPUT_FILENAME = "fixture_eval.json"
_DEFAULT_FIXTURE_ACTION_KEY = "correct_action"
_DEFAULT_SECONDARY_ACTION_KEY = "secondary_action"
_DEFAULT_ACTION_TOOL_NAME = "run_action"
_DEFAULT_VERIFIER_TOOL_NAME = "delegate_to_verifier"
_DEFAULT_COMPLETION_EVENT_KINDS = ("user_response", "execution_end")
_DEFAULT_VERIFICATION_MARKERS = ("verification: approved", "verification approved")


def _load_events(path: Path) -> List[Dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _tool_name(event: Dict[str, Any]) -> str:
    return str(event.get("tool_name") or event.get("tool") or "")


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _to_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _tool_args(event: Dict[str, Any]) -> Dict[str, Any]:
    for key in ("arguments", "args", "input", "params"):
        maybe = _to_dict(event.get(key))
        if maybe:
            return maybe

    payload = _to_dict(event.get("payload"))
    if payload:
        for key in ("arguments", "args", "input", "params"):
            maybe = _to_dict(payload.get(key))
            if maybe:
                return maybe
        if any(k in payload for k in ("service", "action", "reason", "to_version")):
            return payload

    return {}


def _is_success_event(event: Dict[str, Any]) -> Optional[bool]:
    status_val = event.get("status")
    if status_val is not None:
        status = _norm(status_val)
        if status in ("ok", "success", "succeeded", "done", "completed"):
            return True
        if status in ("error", "failed", "failure", "denied", "rejected"):
            return False

    success_val = event.get("success")
    if isinstance(success_val, bool):
        return success_val

    result = _to_dict(event.get("result"))
    if result:
        status = _norm(result.get("status"))
        if status in ("ok", "success", "succeeded", "done", "completed"):
            return True
        if status in ("error", "failed", "failure", "denied", "rejected"):
            return False
        if isinstance(result.get("success"), bool):
            return bool(result.get("success"))

    return None


def _deterministic_match(args: Dict[str, Any], expected: Dict[str, Any]) -> Dict[str, Any]:
    service_match = _norm(args.get("service")) == _norm(expected.get("service"))
    action_match = _norm(args.get("action")) == _norm(expected.get("action"))
    expected_version = expected.get("to_version")
    version_match: Optional[bool] = (
        _norm(args.get("to_version")) == _norm(expected_version)
        if expected_version
        else None
    )
    return {
        "service": service_match,
        "action": action_match,
        "to_version": version_match,
        "overall": service_match and action_match,
    }


def _collect_action_candidates(
    events: List[Dict[str, Any]],
    action_tool_name: str,
) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for idx, event in enumerate(events):
        if _norm(_tool_name(event)) != _norm(action_tool_name):
            continue
        args = _tool_args(event)
        candidates.append(
            {
                "index": idx,
                "kind": str(event.get("kind") or ""),
                "call_id": str(event.get("call_id") or ""),
                "args": args,
                "success": _is_success_event(event),
            }
        )
    return candidates


def _select_primary_action(
    candidates: List[Dict[str, Any]],
    expected: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if not candidates:
        return None

    exp_service = _norm(expected.get("service"))
    exp_action = _norm(expected.get("action"))

    def score(candidate: Dict[str, Any]) -> tuple[int, int]:
        args = candidate.get("args", {})
        service = _norm(args.get("service"))
        action = _norm(args.get("action"))
        has_both = bool(service and action)
        exact = bool(
            exp_service
            and exp_action
            and service == exp_service
            and action == exp_action
        )

        points = 0
        if exact:
            points += 1000
        if has_both:
            points += 200
        elif service or action:
            points += 50
        if candidate.get("success") is True:
            points += 25

        return points, int(candidate.get("index", -1))

    return max(candidates, key=score)


def _resolve_path(raw: str, pipeline_config_path: Optional[Path], env_ws: Optional[str]) -> Path:
    p = Path(raw)
    if p.is_absolute():
        return p
    if pipeline_config_path is not None:
        candidate = (pipeline_config_path.parent / raw).resolve()
        if candidate.exists():
            return candidate
    if env_ws:
        candidate = (Path(env_ws) / raw).resolve()
        if candidate.exists():
            return candidate
    return p


def _load_known_actions(schema_path: Path) -> Optional[frozenset[str]]:
    try:
        import yaml

        doc = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Cannot load action schema at %s: %s", schema_path, exc)
        return None

    parameters = doc.get("spec", {}).get("parameters") or doc.get("parameters") or []
    for param in parameters:
        if isinstance(param, dict) and param.get("name") == "action":
            enum = param.get("enum")
            if isinstance(enum, list):
                return frozenset(str(v).strip().lower() for v in enum)

    logger.warning("Action schema at %s has no 'action' parameter enum", schema_path)
    return None


def _all_text(events: Sequence[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for event in events:
        for key in ("output", "content", "message", "result"):
            value = event.get(key)
            if isinstance(value, str):
                parts.append(value)
    return " ".join(parts).lower()


class EvalFixtureStep(PipelineStep):
    """Score a single run against generic fixture expectations."""

    type = "eval_fixture"

    async def execute(self, ctx: ExecutionContext) -> StepOutput:
        config = self.config

        fixture_path_raw = config.get("fixture_path")
        if not fixture_path_raw:
            raise ValueError(
                f"Step '{self.name}': fixture_path is required for eval_fixture."
            )

        run_dir_raw = config.get("run_dir")
        if not run_dir_raw:
            raise ValueError(
                f"Step '{self.name}': run_dir not in config. "
                "Ensure the step is declared with 'per_run: true'."
            )
        run_dir = Path(str(run_dir_raw)).expanduser().resolve()

        events_path = run_dir / "traces" / "events.jsonl"
        if not events_path.exists():
            logger.warning(
                "Step '%s': events.jsonl not found at %s - skipping",
                self.name,
                events_path,
            )
            return StepOutput(
                data={"skipped": True, "reason": "events.jsonl missing"},
                files=[],
                metadata={},
            )

        events = _load_events(events_path)
        logger.info("Step '%s': loaded %d events from %s", self.name, len(events), events_path)

        pipeline_config_path: Optional[Path] = (
            getattr(ctx.pipeline, "config_path", None) if ctx.pipeline else None
        )
        env_ws: Optional[str] = os.environ.get("MAS_WORKSPACE_ROOT")

        fixture_path = _resolve_path(str(fixture_path_raw), pipeline_config_path, env_ws)

        try:
            import yaml

            fixture = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error("Step '%s': cannot load fixture at %s: %s", self.name, fixture_path, exc)
            return StepOutput(data={"error": str(exc)}, files=[], metadata={})

        if not isinstance(fixture, dict):
            return StepOutput(
                data={"error": f"Fixture at {fixture_path} is not a mapping"},
                files=[],
                metadata={},
            )

        fixture_action_key = str(config.get("fixture_action_key", _DEFAULT_FIXTURE_ACTION_KEY))
        secondary_action_key = str(config.get("secondary_action_key", _DEFAULT_SECONDARY_ACTION_KEY))
        action_tool_name = str(config.get("action_tool_name", _DEFAULT_ACTION_TOOL_NAME))
        verifier_tool_name = str(config.get("verification_tool_name", _DEFAULT_VERIFIER_TOOL_NAME))
        completion_event_kinds = tuple(
            config.get("completion_event_kinds") or _DEFAULT_COMPLETION_EVENT_KINDS
        )
        verification_markers = tuple(
            config.get("verification_approved_markers") or _DEFAULT_VERIFICATION_MARKERS
        )
        output_filename = str(config.get("output_filename", _DEFAULT_OUTPUT_FILENAME))

        expected = fixture.get(fixture_action_key, {})
        if not isinstance(expected, dict):
            return StepOutput(
                data={"error": f"Fixture key {fixture_action_key!r} is not a mapping"},
                files=[],
                metadata={},
            )
        secondary = expected.get(secondary_action_key) or {}
        if secondary and not isinstance(secondary, dict):
            secondary = {}

        schema_path_raw = config.get("run_action_schema_path")
        known_actions: Optional[frozenset[str]] = None
        if schema_path_raw:
            schema_path = _resolve_path(str(schema_path_raw), pipeline_config_path, env_ws)
            known_actions = _load_known_actions(schema_path)
            fixture_action = _norm(expected.get("action", ""))
            if known_actions is not None and fixture_action and fixture_action not in known_actions:
                logger.warning(
                    "Step '%s': fixture action %r is not in action schema enum %s (schema: %s)",
                    self.name,
                    fixture_action,
                    sorted(known_actions),
                    schema_path,
                )

        tool_events = [event for event in events if event.get("kind") == "tool_call_start"]
        action_candidates = _collect_action_candidates(events, action_tool_name)
        selected_action = _select_primary_action(action_candidates, expected)
        text = _all_text(events)

        c1 = any(event.get("kind") in completion_event_kinds for event in events)

        verifier_called = any(_tool_name(event) == verifier_tool_name for event in tool_events)
        c2 = verifier_called and any(marker in text for marker in verification_markers)

        c3_match: Dict[str, Any] = {
            "service": False,
            "action": False,
            "to_version": None,
            "overall": False,
        }
        c3_actual: Dict[str, Any] = {}
        if selected_action is not None:
            args = selected_action.get("args", {})
            c3_actual = {
                "service": args.get("service"),
                "action": args.get("action"),
                "to_version": args.get("to_version"),
            }
            c3_match = _deterministic_match(args, expected)
        c3 = c3_match["overall"]
        c3_semantic_result: Optional[str] = None if c3 else "Dummy"

        c4 = False
        if secondary:
            for candidate in action_candidates:
                args = candidate.get("args", {})
                if _norm(args.get("service")) == _norm(secondary.get("service")) and _norm(
                    args.get("action")
                ) == _norm(secondary.get("action")):
                    c4 = True
                    break

        result = {
            "run_dir": str(run_dir),
            "c1_completion": c1,
            "c2_verification_gate": c2,
            "c3_primary_action_correct": c3,
            "c3_match_service": c3_match["service"],
            "c3_match_action": c3_match["action"],
            "c3_match_to_version": c3_match["to_version"],
            "c3_actual": c3_actual,
            "c3_match_mode": "deterministic",
            "c3_semantic_result": c3_semantic_result,
            "c3_selection_policy": "exact_match > complete_args > success_hint > recency",
            "c3_selected_event_index": selected_action.get("index") if selected_action else None,
            "c3_selected_event_kind": selected_action.get("kind") if selected_action else None,
            "c3_selected_event_call_id": selected_action.get("call_id") if selected_action else None,
            "c3_expected": {k: expected.get(k) for k in ("service", "action", "to_version")},
            "c4_secondary_action": c4,
            "c4_expected": (
                {k: secondary.get(k) for k in ("service", "action")}
                if secondary
                else None
            ),
            "run_action_candidates": len(action_candidates),
            "run_action_candidates_with_args": len(
                [candidate for candidate in action_candidates if candidate.get("args")]
            ),
            "total_run_actions": len(action_candidates),
        }

        out_file = run_dir / output_filename
        out_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info(
            "Step '%s': %s - c1=%s c2=%s c3=%s c4=%s -> %s",
            self.name,
            run_dir.name,
            c1,
            c2,
            c3,
            c4,
            out_file,
        )

        return StepOutput(data=result, files=[out_file], metadata=result)
