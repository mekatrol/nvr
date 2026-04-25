from __future__ import annotations

from typing import Any

from nvr_common.pipeline import PipelineContext, PipelineStageResult


class MetadataAnnotationStage:
    def __init__(self, config: dict[str, Any]) -> None:
        metadata = config.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ValueError("metadata annotation config 'metadata' must be a mapping")

        self.metadata = metadata
        self.include_image_shape = config.get("include_image_shape", True)
        self.include_upstream_ids = config.get("include_upstream_ids", True)

        if not isinstance(self.include_image_shape, bool):
            raise ValueError(
                "metadata annotation config 'include_image_shape' must be true/false"
            )
        if not isinstance(self.include_upstream_ids, bool):
            raise ValueError(
                "metadata annotation config 'include_upstream_ids' must be true/false"
            )

    def process(self, context: PipelineContext) -> PipelineStageResult:
        metadata_updates = dict(self.metadata)
        if self.include_image_shape:
            metadata_updates[f"{context.stage_id}.image_shape"] = tuple(
                context.current_image.shape
            )
        if self.include_upstream_ids:
            metadata_updates[f"{context.stage_id}.upstream_ids"] = tuple(
                sorted(context.upstream_inputs.keys())
            )

        return PipelineStageResult(metadata_updates=metadata_updates)
