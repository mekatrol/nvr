from __future__ import annotations

from typing import Any

import numpy as np

from nvr_common.config import Config
from nvr_common.pipeline.debug import PipelineDebugSession


class DebugApiState:
    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()
        self.sessions: dict[str, PipelineDebugSession] = {}

    def list_cameras(self) -> list[dict[str, Any]]:
        cameras = []
        for camera in self.config.get(Config.KEY_CAMERAS, []):
            if isinstance(camera, dict):
                cameras.append(
                    {
                        "id": camera.get(Config.KEY_CAMERA_ID),
                        "name": camera.get(Config.KEY_CAMERA_NAME),
                        "enabled": camera.get(Config.KEY_CAMERA_ENABLED, False),
                        "pipeline_enabled": self.config.get_pipeline_graph(
                            camera.get(Config.KEY_CAMERA_ID, "")
                        )
                        is not None,
                    }
                )
        return cameras

    def graph(self, camera_id: str | None = None) -> dict[str, Any]:
        graph = self.config.get_pipeline_graph(camera_id)
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
                        }
                        for stage in pipeline.stages
                    ],
                }
                for pipeline in graph.pipelines
            ],
            "edges": [
                {"from": edge.source, "to": edge.target} for edge in graph.edges
            ],
        }

    def session(self, camera_id: str) -> PipelineDebugSession | None:
        if camera_id in self.sessions:
            return self.sessions[camera_id]
        graph = self.config.get_pipeline_graph(camera_id)
        if graph is None:
            return None
        session = PipelineDebugSession(graph)
        image = np.zeros((120, 160, 3), dtype=np.uint8)
        session.load_frame(camera_id=camera_id, frame_id="debug-frame", image=image)
        self.sessions[camera_id] = session
        return session
