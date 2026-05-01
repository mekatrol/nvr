from __future__ import annotations

from typing import Any

from nvr_common.pipeline import PipelineContext, PipelineStageResult
from nvr_common.pipeline.pipeline_stage import PipelineStage


class MovementTrackerStage(PipelineStage):
    def __init__(self, config: dict[str, Any]) -> None:
        self.default_track_id = config.get("default_track_id", "person-0")
        if not isinstance(self.default_track_id, str):
            raise ValueError("tracker config 'default_track_id' must be a string")
        self._previous_centers: dict[str, tuple[float, float]] = {}

    def process(self, context: PipelineContext) -> PipelineStageResult:
        detections = context.metadata.get("detections", [])
        if not isinstance(detections, list):
            raise ValueError("detections metadata must be a list")

        tracks = []
        for index, detection in enumerate(detections):
            if not isinstance(detection, dict):
                continue

            track_id = detection.get("track_id") or f"{self.default_track_id}-{index}"
            bbox = detection.get("bbox")
            if not self._is_bbox(bbox):
                continue

            center = self._center(bbox)
            previous_center = self._previous_centers.get(track_id)
            dx = 0.0
            dy = 0.0
            if previous_center is not None:
                dx = center[0] - previous_center[0]
                dy = center[1] - previous_center[1]

            self._previous_centers[track_id] = center
            tracks.append(
                {
                    "track_id": track_id,
                    "class": detection.get("class", "person"),
                    "confidence": detection.get("confidence", 0.0),
                    "bbox": tuple(bbox),
                    "center": center,
                    "previous_center": previous_center,
                    "movement": {"dx": dx, "dy": dy},
                }
            )

        return PipelineStageResult(metadata_updates={"tracks": tracks})

    @staticmethod
    def _is_bbox(value: Any) -> bool:
        return (
            isinstance(value, (list, tuple))
            and len(value) == 4
            and all(isinstance(part, (int, float)) for part in value)
        )

    @staticmethod
    def _center(bbox: Any) -> tuple[float, float]:
        x, y, width, height = bbox
        return (float(x) + float(width) / 2, float(y) + float(height) / 2)
