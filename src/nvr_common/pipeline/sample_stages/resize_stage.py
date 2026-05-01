from __future__ import annotations

from typing import Any

import cv2

from nvr_common.pipeline import PipelineContext, PipelineStageResult
from nvr_common.pipeline.pipeline_stage import PipelineStage


class ResizeStage(PipelineStage):
    def __init__(self, config: dict[str, Any]) -> None:
        self.width = self._read_int(config, "width", minimum=1)
        height = config.get("height")
        self.height = self._read_optional_int(height, "height")

    def process(self, context: PipelineContext) -> PipelineStageResult:
        image = context.current_image
        source_height, source_width = image.shape[:2]
        height = self.height
        if height is None:
            height = max(1, round(source_height * (self.width / source_width)))

        resized = cv2.resize(image, (self.width, height), interpolation=cv2.INTER_AREA)
        return PipelineStageResult(
            output_image=resized,
            metadata_updates={
                "resize": {
                    "width": self.width,
                    "height": height,
                }
            },
        )

    @staticmethod
    def _read_int(
        config: dict[str, Any], key: str, minimum: int = 0
    ) -> int:
        value = config.get(key)
        if not isinstance(value, int) or value < minimum:
            raise ValueError(f"resize config '{key}' must be an integer >= {minimum}")
        return value

    @staticmethod
    def _read_optional_int(value: Any, key: str) -> int | None:
        if value is None:
            return None
        if not isinstance(value, int) or value < 1:
            raise ValueError(f"resize config '{key}' must be an integer >= 1")
        return value
