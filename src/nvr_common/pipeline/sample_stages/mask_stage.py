from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from nvr_common.pipeline import PipelineContext, PipelineStageResult


class MaskStage:
    def __init__(self, config: dict[str, Any]) -> None:
        self.polygons = self._read_polygons(config)

    def process(self, context: PipelineContext) -> PipelineStageResult:
        image = context.current_image
        if not isinstance(image, np.ndarray):
            raise TypeError("mask stage requires a numpy image")

        masked = image.copy()
        image_height, image_width = masked.shape[:2]
        clipped_polygons = [
            self._clip_polygon(polygon, image_width, image_height)
            for polygon in self.polygons
        ]
        drawable_polygons = [
            polygon for polygon in clipped_polygons if len(polygon) >= 3
        ]
        if drawable_polygons:
            cv2.fillPoly(
                masked,
                [np.array(polygon, dtype=np.int32) for polygon in drawable_polygons],
                color=0,
            )

        return PipelineStageResult(
            output_image=masked,
            metadata_updates={
                "mask": {
                    "polygons": [
                        [{"x": x, "y": y} for x, y in polygon]
                        for polygon in drawable_polygons
                    ]
                }
            },
        )

    @classmethod
    def _read_polygons(cls, config: dict[str, Any]) -> list[list[tuple[int, int]]]:
        raw_polygons = config.get("polygons", [])
        if not isinstance(raw_polygons, list):
            raise ValueError("mask config 'polygons' must be a list")

        polygons: list[list[tuple[int, int]]] = []
        for polygon in raw_polygons:
            if not isinstance(polygon, list):
                raise ValueError("each mask polygon must be a list")
            points = [cls._read_point(point) for point in polygon]
            if len(points) < 3:
                raise ValueError("each mask polygon must contain at least 3 points")
            polygons.append(points)
        return polygons

    @staticmethod
    def _read_point(point: Any) -> tuple[int, int]:
        if isinstance(point, dict):
            x = point.get("x")
            y = point.get("y")
        elif isinstance(point, list | tuple) and len(point) == 2:
            x, y = point
        else:
            raise ValueError("mask polygon points must be {x, y} objects")

        if not isinstance(x, int) or not isinstance(y, int):
            raise ValueError("mask polygon point coordinates must be integers")
        if x < 0 or y < 0:
            raise ValueError("mask polygon point coordinates must be >= 0")
        return x, y

    @staticmethod
    def _clip_polygon(
        polygon: list[tuple[int, int]], image_width: int, image_height: int
    ) -> list[tuple[int, int]]:
        max_x = max(0, image_width - 1)
        max_y = max(0, image_height - 1)
        return [(min(max(x, 0), max_x), min(max(y, 0), max_y)) for x, y in polygon]
