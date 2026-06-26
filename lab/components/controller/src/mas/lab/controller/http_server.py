#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""HTTP API for mas-lab-ui (stdlib ThreadingHTTPServer)."""
from __future__ import annotations

import json
import logging
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, unquote, urlparse

from mas.lab.controller.api import ControllerAPI

logger = logging.getLogger(__name__)

_CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


class ControllerHTTPHandler(BaseHTTPRequestHandler):
    api: ControllerAPI | None = None

    def log_message(self, fmt: str, *args: Any) -> None:
        logger.debug(fmt, *args)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _send(self, status: int, payload: Any) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for key, value in _CORS.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, detail: str) -> None:
        self._send(status, {"detail": detail})

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        for key, value in _CORS.items():
            self.send_header(key, value)
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        api = self.api
        if api is None:
            return self._error(500, "API not initialized")
        path = urlparse(self.path).path
        query = parse_qs(urlparse(self.path).query)

        if path == "/api/health":
            return self._send(200, {"status": "ok"})
        if path == "/api/libraries":
            return self._send(200, {"libraries": api.list_libraries()})
        if path == "/api/jobs":
            status = (query.get("status") or [None])[0]
            return self._send(200, {"jobs": api.list_jobs(status=status)})
        if path.startswith("/api/jobs/"):
            job_id = path.split("/", 3)[-1]
            job = api.get_job(job_id)
            if job is None:
                return self._error(404, f"Job {job_id} not found")
            return self._send(200, job)
        if path == "/api/pipeline-step-types":
            return self._send(200, api.pipeline_step_types())
        if path == "/api/metrics/eval":
            return self._send(200, {})
        if path == "/api/metrics/mce":
            return self._send(200, {})

        m = re.match(r"^/api/libraries/([^/]+)/tools$", path)
        if m:
            return self._send(200, {"tools": api.list_tools(unquote(m.group(1)))})
        m = re.match(r"^/api/libraries/([^/]+)/skills$", path)
        if m:
            return self._send(200, {"skills": api.list_skills(unquote(m.group(1)))})
        m = re.match(r"^/api/libraries/([^/]+)/experiments$", path)
        if m:
            return self._send(200, {"experiments": api.list_experiments(unquote(m.group(1)))})
        m = re.match(r"^/api/libraries/([^/]+)/experiments/([^/]+)$", path)
        if m:
            library, name = unquote(m.group(1)), unquote(m.group(2))
            try:
                return self._send(200, api.get_experiment_content(library, name))
            except FileNotFoundError:
                return self._error(404, "experiment not found")
        m = re.match(r"^/api/libraries/([^/]+)/pipelines$", path)
        if m:
            return self._send(200, {"pipelines": api.list_pipelines(unquote(m.group(1)))})
        m = re.match(r"^/api/libraries/([^/]+)/pipelines/([^/]+)$", path)
        if m:
            library, name = unquote(m.group(1)), unquote(m.group(2))
            try:
                return self._send(200, api.get_pipeline_content(library, name))
            except FileNotFoundError:
                return self._error(404, "pipeline not found")
        m = re.match(r"^/api/libraries/([^/]+)/overlays$", path)
        if m:
            return self._send(200, {"overlays": api.list_overlays(unquote(m.group(1)))})
        m = re.match(r"^/api/libraries/([^/]+)/overlays/([^/]+)$", path)
        if m:
            library, name = unquote(m.group(1)), unquote(m.group(2))
            try:
                return self._send(200, api.get_overlay_content(library, name))
            except FileNotFoundError:
                return self._error(404, "overlay not found")
        m = re.match(r"^/api/libraries/([^/]+)/datasets$", path)
        if m:
            return self._send(200, {"datasets": api.list_datasets(unquote(m.group(1)))})
        m = re.match(r"^/api/libraries/([^/]+)/datasets/([^/]+)$", path)
        if m:
            library, name = unquote(m.group(1)), unquote(m.group(2))
            try:
                return self._send(200, api.get_dataset_content(library, name))
            except FileNotFoundError:
                return self._error(404, "dataset not found")
        m = re.match(r"^/api/libraries/([^/]+)/scenarios$", path)
        if m:
            return self._send(200, {"scenarios": api.list_scenarios(unquote(m.group(1)))})
        m = re.match(r"^/api/libraries/([^/]+)/config-files$", path)
        if m:
            return self._send(200, api.config_files(unquote(m.group(1))))
        m = re.match(r"^/api/libraries/([^/]+)/apps$", path)
        if m:
            return self._send(200, {"mas_resources": {}})

        self._error(404, "not found")

    def do_POST(self) -> None:  # noqa: N802
        return self._dispatch_write("POST")

    def do_PUT(self) -> None:  # noqa: N802
        return self._dispatch_write("PUT")

    def do_DELETE(self) -> None:  # noqa: N802
        api = self.api
        if api is None:
            return self._error(500, "API not initialized")
        path = urlparse(self.path).path
        m = re.match(r"^/api/libraries/([^/]+)/experiments/([^/]+)$", path)
        if m:
            api.delete_experiment(unquote(m.group(1)), unquote(m.group(2)))
            return self._send(200, {"ok": True})
        m = re.match(r"^/api/libraries/([^/]+)/pipelines/([^/]+)$", path)
        if m:
            api.delete_pipeline(unquote(m.group(1)), unquote(m.group(2)))
            return self._send(200, {"ok": True})
        m = re.match(r"^/api/libraries/([^/]+)/overlays/([^/]+)$", path)
        if m:
            api.delete_overlay(unquote(m.group(1)), unquote(m.group(2)))
            return self._send(200, {"ok": True})
        m = re.match(r"^/api/libraries/([^/]+)/datasets/([^/]+)$", path)
        if m:
            api.delete_dataset(unquote(m.group(1)), unquote(m.group(2)))
            return self._send(200, {"ok": True})
        self._error(404, "not found")

    def _dispatch_write(self, method: str) -> None:
        api = self.api
        if api is None:
            return self._error(500, "API not initialized")
        path = urlparse(self.path).path
        body = self._read_json()

        m = re.match(r"^/api/libraries/([^/]+)/validate$", path)
        if m and method == "POST":
            return self._send(200, api.validate_manifest_yaml(body.get("manifest_yaml") or ""))
        m = re.match(r"^/api/libraries/([^/]+)/run$", path)
        if m and method == "POST":
            return self._send(200, api.run_agent_job(unquote(m.group(1)), body))
        m = re.match(r"^/api/libraries/([^/]+)/run-mas$", path)
        if m and method == "POST":
            return self._send(200, api.run_mas_job(unquote(m.group(1)), body))
        m = re.match(r"^/api/libraries/([^/]+)/benchmark/run$", path)
        if m and method == "POST":
            return self._send(200, api.run_benchmark_job(unquote(m.group(1)), body))
        m = re.match(r"^/api/libraries/([^/]+)/pipeline/run$", path)
        if m and method == "POST":
            return self._send(200, api.run_pipeline_job(unquote(m.group(1)), body))
        m = re.match(r"^/api/libraries/([^/]+)/experiments$", path)
        if m and method == "POST":
            api.save_experiment(unquote(m.group(1)), body["name"], body["content"])
            return self._send(200, {"ok": True})
        m = re.match(r"^/api/libraries/([^/]+)/experiments/([^/]+)$", path)
        if m and method == "PUT":
            library = unquote(m.group(1))
            api.save_experiment(library, body.get("name") or unquote(m.group(2)), body["content"])
            return self._send(200, {"ok": True})
        m = re.match(r"^/api/libraries/([^/]+)/pipelines$", path)
        if m and method == "POST":
            api.save_pipeline(unquote(m.group(1)), body["name"], body["content"])
            return self._send(200, {"ok": True})
        m = re.match(r"^/api/libraries/([^/]+)/pipelines/([^/]+)$", path)
        if m and method == "PUT":
            library = unquote(m.group(1))
            api.save_pipeline(library, body.get("name") or unquote(m.group(2)), body["content"])
            return self._send(200, {"ok": True})
        m = re.match(r"^/api/libraries/([^/]+)/overlays/validate$", path)
        if m and method == "POST":
            return self._send(200, {"status": "ok", "errors": []})
        m = re.match(r"^/api/libraries/([^/]+)/overlays$", path)
        if m and method == "POST":
            api.save_overlay(unquote(m.group(1)), body["name"], body["content"])
            return self._send(200, {"ok": True})
        m = re.match(r"^/api/libraries/([^/]+)/overlays/([^/]+)$", path)
        if m and method == "PUT":
            library = unquote(m.group(1))
            api.save_overlay(library, body.get("name") or unquote(m.group(2)), body["content"])
            return self._send(200, {"ok": True})
        m = re.match(r"^/api/libraries/([^/]+)/pipelines/validate$", path)
        if m and method == "POST":
            return self._send(200, {"status": "ok"})
        m = re.match(r"^/api/libraries/([^/]+)/datasets$", path)
        if m and method == "POST":
            api.save_dataset(unquote(m.group(1)), body["name"], body["content"])
            return self._send(200, {"ok": True})
        m = re.match(r"^/api/libraries/([^/]+)/datasets/([^/]+)$", path)
        if m and method == "PUT":
            library = unquote(m.group(1))
            api.save_dataset(library, body.get("name") or unquote(m.group(2)), body["content"])
            return self._send(200, {"ok": True})

        self._error(404, "not found")


def start_http_server(*, api: ControllerAPI, host: str = "127.0.0.1", port: int = 9000) -> None:
    class _Bound(ControllerHTTPHandler):
        api = api

    server = ThreadingHTTPServer((host, port), _Bound)
    logger.info("Controller HTTP listening on http://%s:%s", host, port)
    server.serve_forever()
