from __future__ import annotations

import json
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from nvr_web.debug_api_state import DebugApiState


class DebugApiHandler(SimpleHTTPRequestHandler):
    api_state = DebugApiState()

    def __init__(self, *args: Any, directory: str | None = None, **kwargs: Any) -> None:
        static_dir = directory or str(Path(__file__).with_name("web"))
        super().__init__(*args, directory=static_dir, **kwargs)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        if parsed.path == "/api/cameras":
            self._json({"cameras": self.api_state.list_cameras()})
            return
        if parsed.path == "/api/pipeline-graph":
            camera_id = self._query_value(query, "camera_id")
            self._json(self.api_state.graph(camera_id))
            return
        if parsed.path == "/api/debug/state":
            camera_id = self._query_value(query, "camera_id")
            self._json(self._session_snapshot(camera_id))
            return
        if parsed.path == "/api/debug/metadata":
            camera_id = self._query_value(query, "camera_id")
            snapshot = self._session_snapshot(camera_id)
            records = snapshot.get("records", [])
            self._json({"metadata": records[-1]["metadata_after"] if records else {}})
            return
        if parsed.path == "/api/debug/preview":
            self._json({"preview": None})
            return

        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/debug/breakpoints":
            body = self._read_json()
            session = self.api_state.session(body.get("camera_id", ""))
            if session is None:
                self._json({"error": "pipeline graph disabled"}, status=404)
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
            session = self.api_state.session(body.get("camera_id", ""))
            if session is None:
                self._json({"error": "pipeline graph disabled"}, status=404)
                return
            command = body.get("command")
            if command == "run":
                try:
                    session = self.api_state.load_camera_frame(
                        body.get("camera_id", "")
                    )
                except RuntimeError as ex:
                    self._json({"error": str(ex)}, status=502)
                    return
                if session is None:
                    self._json({"error": "pipeline graph disabled"}, status=404)
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

    def _session_snapshot(self, camera_id: str | None) -> dict[str, Any]:
        if not camera_id:
            return {"status": "disabled", "records": []}
        session = self.api_state.session(camera_id)
        if session is None:
            return {"status": "disabled", "records": []}
        return session.snapshot()

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
