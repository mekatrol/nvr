from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

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
        self.sessions: dict[str, PipelineDebugSession] = {}
        self.frame_sources: dict[str, Any] = {}
        self.pipelines_store = PipelinesStore(self.config, logger=self.logger)

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

    def pipelines(self, camera_id: str | None = None) -> dict[str, Any]:
        integrity = self.pipelines_store.pipeline_integrity()
        graph = self.pipelines_store.pipeline_config_graph()
        if graph is None:
            return {
                "enabled": False,
                "integrity": integrity,
                "pipelines": [],
                "edges": [],
            }
        return {
            "enabled": True,
            "integrity": integrity,
            "pipelines": [
                {
                    "id": pipeline.id,
                    "enabled": pipeline.enabled,
                    "required_inputs": pipeline.required_inputs,
                    "stages": [
                        {
                            "id": stage.id,
                            "enabled": stage.enabled,
                            "module": stage.module,
                            "class_name": stage.class_name,
                            "config": stage.config,
                        }
                        for stage in pipeline.stages
                    ],
                }
                for pipeline in graph.pipelines
            ],
            "edges": [{"from": edge.source, "to": edge.target} for edge in graph.edges],
        }

    def session(self, camera_id: str) -> PipelineDebugSession | None:
        integrity = self.pipelines_store.pipeline_integrity()
        if not integrity.get("ok", False):
            self.sessions.pop(camera_id, None)
            if self.logger is not None:
                self.logger.warning(
                    "Pipeline debug session blocked because integrity check failed"
                )
            return None
        if camera_id in self.sessions:
            return self.sessions[camera_id]
        graph = self.pipelines_store.pipeline_config_graph()
        if graph is None:
            return None
        session = PipelineDebugSession(graph)
        self.sessions[camera_id] = session
        return session

    def pipeline_config_pipelines(self) -> dict[str, Any]:
        return self.pipelines_store.pipeline_config_response()

    def reload_pipelines(self) -> dict[str, Any]:
        self.pipelines_store = PipelinesStore(self.config, logger=self.logger)
        self.sessions.clear()
        self.close_frame_sources()
        return self.pipelines(None)

    def log_entries(self, limit: int = 500) -> list[dict[str, Any]]:
        return LogReader(Logger().log_file_path).entries(limit)

    def clear_logs(self) -> None:
        LogReader(Logger().log_file_path).clear()
        Logger().logger.debug("Logs cleared")

    def save_pipeline_config_pipelines(self, raw_pipelines: dict[str, Any]) -> dict[str, Any]:
        response = self.pipelines_store.save_pipeline_config_pipelines(raw_pipelines)
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

    def load_camera_frame(self, camera_id: str) -> PipelineDebugSession | None:
        session = self.session(camera_id)
        if session is None:
            return None

        frame_source = self.frame_source(camera_id)
        try:
            frame = frame_source.read()
        except Exception as ex:
            self.close_frame_source(camera_id)
            message = sanitize_rtsp_url(str(ex))
            self._log_bad_frame(camera_id, message)
            session.drop_frame()
            return session

        reason = bad_frame_reason(frame)
        if reason is not None:
            self._log_bad_frame(camera_id, reason)
            session.drop_frame()
            return session

        frame_timestamp = datetime.now(timezone.utc)
        session.load_frame(
            camera_id=camera_id,
            frame_id=str(int(frame_timestamp.timestamp() * 1000)),
            frame_timestamp=frame_timestamp,
            image=frame,
        )
        return session

    def frame_source(self, camera_id: str) -> Any:
        frame_source = self.frame_sources.get(camera_id)
        if frame_source is not None:
            return frame_source

        camera_config = self.config.get_camera(camera_id)
        frame_source = self.frame_source_factory(
            camera_config[Config.KEY_CAMERA_RTSP_URL]
        )
        self.frame_sources[camera_id] = frame_source
        return frame_source

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
