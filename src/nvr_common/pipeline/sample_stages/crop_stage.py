from __future__ import annotations

from typing import Any

from nvr_common.pipeline import PipelineContext, PipelineStageResult


class CropStage:
    def __init__(self, config: dict[str, Any]) -> None:
        self.x = self._read_int(config, "x")
        self.y = self._read_int(config, "y")
        self.width = self._read_int(config, "width", minimum=1)
        self.height = self._read_int(config, "height", minimum=1)

    def process(self, context: PipelineContext) -> PipelineStageResult:
        image = context.current_image
        image_height, image_width = image.shape[:2]
        x2 = min(self.x + self.width, image_width)
        y2 = min(self.y + self.height, image_height)

        if self.x >= image_width or self.y >= image_height:
            raise ValueError(
                f"crop origin ({self.x}, {self.y}) is outside image "
                f"{image_width}x{image_height}"
            )

        cropped = image[self.y : y2, self.x : x2].copy()
        return PipelineStageResult(
            output_image=cropped,
            metadata_updates={
                "crop": {
                    "x": self.x,
                    "y": self.y,
                    "width": x2 - self.x,
                    "height": y2 - self.y,
                }
            },
        )

    @staticmethod
    def _read_int(
        config: dict[str, Any], key: str, minimum: int = 0
    ) -> int:
        value = config.get(key)
        if not isinstance(value, int) or value < minimum:
            raise ValueError(f"crop config '{key}' must be an integer >= {minimum}")
        return value
