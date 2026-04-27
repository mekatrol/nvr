from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from nvr_background.pipeline.opencv_frame_source import OpenCvFrameSource
from nvr_common.config import Config
from nvr_common.logging.rtsp_sanitizing_filter import sanitize_rtsp_url
from nvr_common.pipeline.debug import PipelineDebugSession
from nvr_web.pipelines_store import PipelinesStore


class DebugApiState:
    def __init__(
        self, config: Config | None = None, frame_source_factory: Any = None
    ) -> None:
        self.config = config or Config()
        self.frame_source_factory = frame_source_factory or OpenCvFrameSource
        self.sessions: dict[str, PipelineDebugSession] = {}
        self.pipelines_store = PipelinesStore(self.config)

    def list_cameras(self) -> list[dict[str, Any]]:
        cameras = []
        for camera in self.config.get(Config.KEY_CAMERAS, []):
            if isinstance(camera, dict):
                cameras.append(
                    {
                        "id": camera.get(Config.KEY_CAMERA_ID),
                        "name": camera.get(Config.KEY_CAMERA_NAME),
                        "enabled": camera.get(Config.KEY_CAMERA_ENABLED, False),
                        "pipeline_enabled": self.config.get_pipelines(
                            camera.get(Config.KEY_CAMERA_ID, "")
                        )
                        is not None,
                    }
                )
        return cameras

    def pipelines(self, camera_id: str | None = None) -> dict[str, Any]:
        graph = self.config.get_pipelines(camera_id)
        if graph is None:
            return {"enabled": False, "pipelines": [], "edges": []}
        return {
            "enabled": True,
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
        if camera_id in self.sessions:
            return self.sessions[camera_id]
        graph = self.config.get_pipelines(camera_id)
        if graph is None:
            return None
        session = PipelineDebugSession(graph)
        self.sessions[camera_id] = session
        return session

    def draft_pipelines(self) -> dict[str, Any]:
        return self.pipelines_store.draft_response()

    def save_draft_pipelines(self, raw_pipelines: dict[str, Any]) -> dict[str, Any]:
        return self.pipelines_store.save_draft_pipelines(raw_pipelines)

    def deploy_draft_pipelines(self) -> dict[str, Any]:
        response = self.pipelines_store.deploy_draft_pipelines()
        self.reload_config()
        return response

    def generate_example_resize_pipeline(self) -> dict[str, Any]:
        return self.pipelines_store.generate_example_resize_pipeline()

    def reload_config(self) -> None:
        self.config = Config()
        self.pipelines_store = PipelinesStore(self.config)
        self.sessions.clear()

    def load_camera_frame(self, camera_id: str) -> PipelineDebugSession | None:
        session = self.session(camera_id)
        if session is None:
            return None

        camera_config = self.config.get_camera(camera_id)
        frame_source = self.frame_source_factory(
            camera_config[Config.KEY_CAMERA_RTSP_URL]
        )
        try:
            frame = frame_source.read()
        except Exception as ex:
            message = sanitize_rtsp_url(str(ex))
            raise RuntimeError(message) from ex
        finally:
            self._close_frame_source(frame_source)

        frame_timestamp = datetime.now(timezone.utc)
        session.load_frame(
            camera_id=camera_id,
            frame_id=str(int(frame_timestamp.timestamp() * 1000)),
            frame_timestamp=frame_timestamp,
            image=frame,
        )
        return session

    @staticmethod
    def _close_frame_source(frame_source: Any) -> None:
        close = getattr(frame_source, "close", None)
        if callable(close):
            close()
