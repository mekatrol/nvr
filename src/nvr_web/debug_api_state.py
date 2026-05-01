from __future__ import annotations

from datetime import datetime, timezone
import inspect
from math import isfinite
from pathlib import Path
import re
import shutil
import uuid
from typing import Any

import cv2

from nvr_background.pipeline.opencv_frame_source import OpenCvFrameSource
from nvr_common.config import Config
from nvr_common.logging.log_reader import LogReader
from nvr_common.logging.logger import Logger
from nvr_common.logging.rtsp_sanitizing_filter import sanitize_rtsp_url
from nvr_common.pipeline.frame_validation import bad_frame_reason
from nvr_common.pipeline.debug import PipelineDebugSession
from nvr_web.pipelines_store import PipelinesStore


class DebugApiState:
    def __init__(
        self,
        config: Config | None = None,
        frame_source_factory: Any = None,
        logger: Any = None,
    ) -> None:
        self.config = config or Config()
        self.frame_source_factory = frame_source_factory or OpenCvFrameSource
        self.logger = logger
        self.sessions: dict[tuple[str, str], PipelineDebugSession] = {}
        self.frame_sources: dict[str, Any] = {}
        self.debug_source_files: dict[str, dict[str, Any]] = {}
        self.pipelines_store = PipelinesStore(self.config, logger=self.logger)
        self.debug_uploads_dir = self.pipelines_store.storage_path / "debug_uploads"
        self.debug_uploads_dir.mkdir(parents=True, exist_ok=True)

    def list_cameras(self) -> list[dict[str, Any]]:
        cameras = []
        for camera in self.config.get(Config.KEY_CAMERAS, []):
            if isinstance(camera, dict):
                cameras.append(
                    {
                        "id": camera.get(Config.KEY_CAMERA_ID),
                        "name": camera.get(Config.KEY_CAMERA_NAME),
                        "enabled": camera.get(Config.KEY_CAMERA_ENABLED, False),
                        "pipeline_enabled": self.pipelines_store.pipeline_config_graph()
                        is not None,
                    }
                )
        return cameras

    def pipelines(
        self, camera_id: str | None = None, pipeline_config_path: str | None = None
    ) -> dict[str, Any]:
        integrity = self.pipelines_store.pipeline_integrity(pipeline_config_path)
        graph = self.pipelines_store.pipeline_config_graph(pipeline_config_path)
        if graph is None:
            return {
                "enabled": False,
                "integrity": integrity,
                "pipelines": [],
            }
        return {
            "enabled": True,
            "integrity": integrity,
            "pipelines": [
                {
                    "id": pipeline.id,
                    "name": getattr(pipeline, "name", pipeline.id),
                    "enabled": pipeline.enabled,
                    "stages": [
                        {
                            "id": stage.id,
                            "enabled": stage.enabled,
                            "module": stage.module,
                            "class_name": stage.class_name,
                            "filename": stage.filename,
                            "pipeline": stage.pipeline,
                            "config": stage.config,
                        }
                        for stage in pipeline.stages
                    ],
                }
                for pipeline in graph.pipelines
            ],
        }

    def session(
        self,
        camera_id: str,
        pipeline_config_path: str | None = None,
        debug_source_id: str | None = None,
    ) -> PipelineDebugSession | None:
        session_key = self._session_key(camera_id, pipeline_config_path, debug_source_id)
        integrity = self.pipelines_store.pipeline_integrity(pipeline_config_path)
        if not integrity.get("ok", False):
            self.sessions.pop(session_key, None)
            if self.logger is not None:
                self.logger.warning(
                    "Pipeline debug session blocked because integrity check failed"
                )
            return None
        if session_key in self.sessions:
            return self.sessions[session_key]
        graph = self.pipelines_store.pipeline_config_graph(pipeline_config_path)
        if graph is None:
            return None
        session = PipelineDebugSession(graph)
        self.sessions[session_key] = session
        return session

    def pipeline_config_pipelines(
        self, pipeline_config_path: str | None = None
    ) -> dict[str, Any]:
        return self.pipelines_store.pipeline_config_response(pipeline_config_path)

    def reload_pipelines(self) -> dict[str, Any]:
        self.pipelines_store = PipelinesStore(self.config, logger=self.logger)
        self.sessions.clear()
        self.close_frame_sources()
        return self.pipelines(None)

    def save_debug_source_file(self, filename: str, source: Any) -> dict[str, Any]:
        safe_filename = self._safe_debug_source_filename(filename)
        source_id = uuid.uuid4().hex
        target_path = self.debug_uploads_dir / f"{source_id}_{safe_filename}"
        with target_path.open("wb") as target:
            shutil.copyfileobj(source, target)
        frame_interval_seconds = self._debug_source_frame_interval_seconds(target_path)
        debug_source = {
            "id": source_id,
            "name": safe_filename,
            "path": str(target_path),
            "frame_interval_seconds": frame_interval_seconds,
        }
        self.debug_source_files[source_id] = debug_source
        return {
            "id": source_id,
            "name": safe_filename,
            "frame_interval_seconds": frame_interval_seconds,
        }

    def log_entries(self, limit: int = 500) -> list[dict[str, Any]]:
        return LogReader(Logger().log_file_path).entries(limit)

    def clear_logs(self) -> None:
        LogReader(Logger().log_file_path).clear()
        Logger().logger.debug("Logs cleared")

    def save_pipeline_config_pipelines(
        self, raw_pipelines: dict[str, Any], pipeline_config_path: str | None = None
    ) -> dict[str, Any]:
        response = self.pipelines_store.save_pipeline_config_pipelines(
            raw_pipelines, pipeline_config_path
        )
        self.sessions.clear()
        return response

    def deploy_pipeline_config_pipelines(self) -> dict[str, Any]:
        response = self.pipelines_store.deploy_pipeline_config_pipelines()
        self.reload_config()
        return response

    def generate_example_resize_pipeline(self) -> dict[str, Any]:
        response = self.pipelines_store.generate_example_resize_pipeline()
        self.sessions.clear()
        return response

    def reload_config(self) -> None:
        self.config = Config()
        self.pipelines_store = PipelinesStore(self.config, logger=self.logger)
        self.sessions.clear()
        self.close_frame_sources()

    def load_camera_frame(
        self,
        camera_id: str,
        pipeline_config_path: str | None = None,
        debug_source_id: str | None = None,
    ) -> PipelineDebugSession | None:
        session = self.session(camera_id, pipeline_config_path, debug_source_id)
        if session is None:
            return None

        frame_source_key = debug_source_id or camera_id
        frame_source = self.frame_source(camera_id, debug_source_id)
        try:
            frame = frame_source.read()
        except Exception as ex:
            self.close_frame_source(frame_source_key)
            message = sanitize_rtsp_url(str(ex))
            self._log_bad_frame(frame_source_key, message)
            session.drop_frame()
            return session

        reason = bad_frame_reason(frame)
        if reason is not None:
            self._log_bad_frame(frame_source_key, reason)
            session.drop_frame()
            return session

        frame_timestamp = datetime.now(timezone.utc)
        context_camera_id = self._debug_source_camera_id(debug_source_id) or camera_id
        session.load_frame(
            camera_id=context_camera_id,
            frame_id=str(int(frame_timestamp.timestamp() * 1000)),
            frame_timestamp=frame_timestamp,
            image=frame,
        )
        return session

    def frame_source(self, camera_id: str, debug_source_id: str | None = None) -> Any:
        frame_source_key = debug_source_id or camera_id
        frame_source = self.frame_sources.get(frame_source_key)
        if frame_source is not None:
            return frame_source

        if debug_source_id:
            debug_source = self.debug_source_files.get(debug_source_id)
            if debug_source is None:
                raise RuntimeError("debug source file is not available")
            if self._frame_source_accepts_parameter("warmup_frames"):
                frame_source = self.frame_source_factory(
                    debug_source["path"],
                    warmup_frames=0,
                    read_drain_frames=1,
                    clean_read_attempts=1,
                )
            else:
                frame_source = self.frame_source_factory(debug_source["path"])
            self.frame_sources[frame_source_key] = frame_source
            return frame_source

        camera_config = self.config.get_camera(camera_id)
        if self._frame_source_accepts_ffmpeg_binary():
            frame_source = self.frame_source_factory(
                camera_config[Config.KEY_CAMERA_RTSP_URL],
                ffmpeg_binary=self.config.get(Config.KEY_FFMPEG_BINARY, "ffmpeg"),
            )
        else:
            frame_source = self.frame_source_factory(
                camera_config[Config.KEY_CAMERA_RTSP_URL]
            )
        self.frame_sources[frame_source_key] = frame_source
        return frame_source

    def _frame_source_accepts_ffmpeg_binary(self) -> bool:
        return self._frame_source_accepts_parameter("ffmpeg_binary")

    def _frame_source_accepts_parameter(self, name: str) -> bool:
        try:
            parameters = inspect.signature(self.frame_source_factory).parameters
        except (TypeError, ValueError):
            return False
        return name in parameters

    def close_frame_sources(self) -> None:
        for frame_source in self.frame_sources.values():
            close = getattr(frame_source, "close", None)
            if callable(close):
                close()
        self.frame_sources.clear()

    def close_frame_source(self, camera_id: str) -> None:
        frame_source = self.frame_sources.pop(camera_id, None)
        if frame_source is None:
            return
        close = getattr(frame_source, "close", None)
        if callable(close):
            close()

    def _log_bad_frame(self, camera_id: str, reason: str) -> None:
        if self.logger is not None:
            self.logger.warning("[%s] Dropping bad pipeline frame: %s", camera_id, reason)

    @staticmethod
    def _session_key(
        camera_id: str,
        pipeline_config_path: str | None = None,
        debug_source_id: str | None = None,
    ) -> tuple[str, str]:
        return (camera_id, f"{pipeline_config_path or ''}\0{debug_source_id or ''}")

    def _debug_source_camera_id(self, debug_source_id: str | None) -> str | None:
        if not debug_source_id:
            return None
        debug_source = self.debug_source_files.get(debug_source_id)
        if debug_source is None:
            return None
        return f"file:{debug_source['name']}"

    @staticmethod
    def _safe_debug_source_filename(filename: str) -> str:
        safe_name = Path(filename).name
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", safe_name).strip("._")
        if not safe_name:
            safe_name = "debug-source.mp4"
        if Path(safe_name).suffix.lower() != ".mp4":
            raise ValueError("debug source file must be an MP4")
        return safe_name

    @staticmethod
    def _debug_source_frame_interval_seconds(path: Path) -> float:
        capture = cv2.VideoCapture(str(path))
        try:
            fps = capture.get(cv2.CAP_PROP_FPS)
        finally:
            capture.release()
        if not isfinite(fps) or fps <= 0:
            return 0.0
        return 1.0 / fps
