from __future__ import annotations

from copy import deepcopy
from typing import Any

from nvr_common.pipeline import PipelineContext, PipelineStageResult


class SyntheticPersonDetectorStage:
    def __init__(self, config: dict[str, Any]) -> None:
        self.configured_detections = config.get("detections")
        self.model_path = config.get("model_path")
        if self.configured_detections is not None and not isinstance(
            self.configured_detections, list
        ):
            raise ValueError("synthetic detector config 'detections' must be a list")
        if self.model_path is not None and not isinstance(self.model_path, str):
            raise ValueError("synthetic detector config 'model_path' must be a string")

    def process(self, context: PipelineContext) -> PipelineStageResult:
        raw_detections = context.metadata.get("detections")
        if raw_detections is None:
            raw_detections = self.configured_detections or []
        if not isinstance(raw_detections, list):
            raise ValueError("detections metadata must be a list")

        detections = []
        for index, detection in enumerate(raw_detections):
            if not isinstance(detection, dict):
                raise ValueError("each detection must be a mapping")
            detections.append(
                {
                    "class": detection.get("class", "person"),
                    "confidence": float(detection.get("confidence", 1.0)),
                    "bbox": tuple(detection.get("bbox", (0, 0, 1, 1))),
                    "timestamp": context.frame_timestamp.isoformat()
                    if context.frame_timestamp
                    else None,
                    "track_id": detection.get("track_id", f"person-{index}"),
                }
            )

        return PipelineStageResult(
            metadata_updates={
                "detections": deepcopy(detections),
                "detector": {
                    "strategy": "synthetic",
                    "model_path": self.model_path,
                },
            }
        )
