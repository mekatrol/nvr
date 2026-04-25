from __future__ import annotations

from datetime import datetime, timezone
import threading
from typing import Any

from nvr_background.pipeline.opencv_frame_source import OpenCvFrameSource
from nvr_common.config import Config
from nvr_common.pipeline import PipelineGraphRunner


class CameraPipelineWorker(threading.Thread):
    def __init__(
        self,
        camera_id: str,
        frame_source: Any | None = None,
        logger: Any = None,
    ) -> None:
        super().__init__(daemon=True)
        self.camera_id = camera_id
        self.config = Config()
        self.camera_config = self.config.get_camera(camera_id)
        self.graph = self.config.get_pipeline_graph(camera_id)
        self.interval_seconds = (
            self.config.get_pipeline_frame_interval_seconds(camera_id) or 1.0
        )
        self.frame_source = frame_source or OpenCvFrameSource(
            self.camera_config[Config.KEY_CAMERA_RTSP_URL]
        )
        self.logger = logger
        self.stop_event = threading.Event()
        self.runner = PipelineGraphRunner(self.graph, logger=logger) if self.graph else None
        self.last_outputs = None

    def stop(self) -> None:
        self.stop_event.set()

    def run_once(self) -> dict[str, Any]:
        if self.runner is None:
            return {}

        frame = self.frame_source.read()
        frame_timestamp = datetime.now(timezone.utc)
        outputs = self.runner.run(
            camera_id=self.camera_id,
            frame_id=str(int(frame_timestamp.timestamp() * 1000)),
            frame_timestamp=frame_timestamp,
            image=frame,
        )
        self.last_outputs = outputs
        return outputs

    def run(self) -> None:
        if self.runner is None:
            if self.logger:
                self.logger.info(
                    "[%s] Pipeline graph disabled; skipping pipeline worker",
                    self.camera_id,
                )
            return

        try:
            self.frame_source.open()
            while not self.stop_event.is_set():
                try:
                    self.run_once()
                except Exception as ex:
                    if self.logger:
                        self.logger.error(
                            "[%s] Pipeline worker error: %r", self.camera_id, ex
                        )
                self.stop_event.wait(self.interval_seconds)
        finally:
            self.frame_source.close()
