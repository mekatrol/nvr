from __future__ import annotations

import json
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from nvr_web.debug_api_state import DebugApiState


class DebugApiHandler(SimpleHTTPRequestHandler):
    api_state: DebugApiState | None = None

    def __init__(self, *args: Any, directory: str | None = None, **kwargs: Any) -> None:
        static_dir = directory or str(Path(__file__).with_name("web"))
        super().__init__(*args, directory=static_dir, **kwargs)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        api_state = self._api_state()

        if parsed.path == "/api/cameras":
            self._json({"cameras": api_state.list_cameras()})
            return
        if parsed.path == "/api/pipelines":
            camera_id = self._query_value(query, "camera_id")
            pipeline_config_path = self._query_value(query, "pipeline_config_path")
            try:
                self._json(api_state.pipelines(camera_id, pipeline_config_path))
            except ValueError as ex:
                self._json({"error": str(ex)}, status=400)
            return
        if parsed.path == "/api/pipeline_config/pipelines":
            pipeline_config_path = self._query_value(query, "pipeline_config_path")
            try:
                self._json(api_state.pipeline_config_pipelines(pipeline_config_path))
            except ValueError as ex:
                self._json({"error": str(ex)}, status=400)
            return
        if parsed.path == "/api/logs":
            limit = self._query_int(query, "limit", 500)
            self._json({"entries": api_state.log_entries(limit)})
            return
        if parsed.path == "/api/debug/state":
            camera_id = self._query_value(query, "camera_id")
            pipeline_config_path = self._query_value(query, "pipeline_config_path")
            try:
                self._json(self._session_snapshot(camera_id, pipeline_config_path))
            except ValueError as ex:
                self._json({"error": str(ex)}, status=400)
            return
        if parsed.path == "/api/debug/metadata":
            camera_id = self._query_value(query, "camera_id")
            pipeline_config_path = self._query_value(query, "pipeline_config_path")
            try:
                snapshot = self._session_snapshot(camera_id, pipeline_config_path)
            except ValueError as ex:
                self._json({"error": str(ex)}, status=400)
                return
            records = snapshot.get("records", [])
            self._json({"metadata": records[-1]["metadata_after"] if records else {}})
            return
        if parsed.path == "/api/debug/preview":
            self._json({"preview": None})
            return

        if not Path(parsed.path).suffix:
            self.path = "/index.html"

        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        api_state = self._api_state()
        if parsed.path == "/api/pipeline_config/pipelines":
            body = self._read_json()
            raw_pipelines = body.get("pipelines_config", body)
            if not isinstance(raw_pipelines, dict):
                self._json({"error": "pipelines config is required"}, status=400)
                return
            try:
                self._json(api_state.save_pipeline_config_pipelines(raw_pipelines))
            except ValueError as ex:
                self._json({"error": str(ex)}, status=400)
            return

        if parsed.path == "/api/pipeline_config/pipelines/deploy":
            try:
                self._json(api_state.deploy_pipeline_config_pipelines())
            except ValueError as ex:
                self._json({"error": str(ex)}, status=400)
            return

        if parsed.path == "/api/pipelines/examples/resize":
            try:
                self._json(api_state.generate_example_resize_pipeline())
            except ValueError as ex:
                self._json({"error": str(ex)}, status=400)
            return

        if parsed.path == "/api/pipelines/reload":
            self._json(api_state.reload_pipelines())
            return

        if parsed.path == "/api/logs/clear":
            api_state.clear_logs()
            self._json({"entries": []})
            return

        if parsed.path == "/api/debug/breakpoints":
            body = self._read_json()
            try:
                session = api_state.session(
                    body.get("camera_id", ""),
                    self._body_string(body, "pipeline_config_path"),
                )
            except ValueError as ex:
                self._json({"error": str(ex)}, status=400)
                return
            if session is None:
                self._json({"error": self._no_deployed_pipeline_error()}, status=404)
                return
            pipeline_id = body.get("pipeline_id")
            stage_id = body.get("stage_id")
            if not isinstance(pipeline_id, str):
                self._json({"error": "pipeline_id is required"}, status=400)
                return
            if body.get("enabled", True):
                session.add_breakpoint(pipeline_id, stage_id)
            else:
                session.clear_breakpoint(pipeline_id, stage_id)
            self._json(session.snapshot())
            return

        if parsed.path == "/api/debug/command":
            body = self._read_json()
            pipeline_config_path = self._body_string(body, "pipeline_config_path")
            try:
                session = api_state.session(body.get("camera_id", ""), pipeline_config_path)
            except ValueError as ex:
                self._json({"error": str(ex)}, status=400)
                return
            if session is None:
                self._json({"error": self._no_deployed_pipeline_error()}, status=404)
                return
            command = body.get("command")
            if command == "run":
                try:
                    session = api_state.load_camera_frame(
                        body.get("camera_id", ""), pipeline_config_path
                    )
                except RuntimeError as ex:
                    self._json({"error": str(ex)}, status=502)
                    return
                if session is None:
                    self._json({"error": self._no_deployed_pipeline_error()}, status=404)
                    return
                session.run()
            elif command == "pause":
                session.status = "paused"
            elif command == "step":
                session.step()
            elif command == "step_over_stage":
                session.step()
            elif command == "step_over_pipeline":
                session.step_over_pipeline()
            else:
                self._json({"error": "unknown command"}, status=400)
                return
            self._json(session.snapshot())
            return

        self._json({"error": "not found"}, status=404)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _session_snapshot(
        self, camera_id: str | None, pipeline_config_path: str | None = None
    ) -> dict[str, Any]:
        if not camera_id:
            return {"status": "disabled", "records": []}
        session = self._api_state().session(camera_id, pipeline_config_path)
        if session is None:
            return {"status": "disabled", "records": []}
        return session.snapshot()

    @classmethod
    def _api_state(cls) -> DebugApiState:
        if cls.api_state is None:
            cls.api_state = DebugApiState()
        return cls.api_state

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _json(self, payload: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(payload, default=list).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    @staticmethod
    def _query_value(query: dict[str, list[str]], key: str) -> str | None:
        values = query.get(key)
        return values[0] if values else None

    @staticmethod
    def _body_string(body: dict[str, Any], key: str) -> str | None:
        value = body.get(key)
        return value if isinstance(value, str) and value else None

    @staticmethod
    def _query_int(query: dict[str, list[str]], key: str, default: int) -> int:
        values = query.get(key)
        if not values:
            return default
        try:
            return max(1, min(int(values[0]), 2000))
        except ValueError:
            return default

    @staticmethod
    def _no_deployed_pipeline_error() -> str:
        return "No pipeline configuration is available. Generate or save pipelines before running it."
