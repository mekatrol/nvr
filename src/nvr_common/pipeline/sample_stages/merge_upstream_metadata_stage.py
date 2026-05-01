from __future__ import annotations

from copy import deepcopy
from typing import Any

from nvr_common.pipeline import PipelineContext, PipelineStageResult
from nvr_common.pipeline.pipeline_stage import PipelineStage


class MergeUpstreamMetadataStage(PipelineStage):
    def __init__(self, config: dict[str, Any]) -> None:
        metadata_keys = config.get("metadata_keys")
        if metadata_keys is not None and (
            not isinstance(metadata_keys, list)
            or not all(isinstance(key, str) for key in metadata_keys)
        ):
            raise ValueError("merge metadata config 'metadata_keys' must be a string list")
        self.metadata_keys = tuple(metadata_keys) if metadata_keys is not None else None
        self.include_upstream_metadata = bool(config.get("include_upstream_metadata", True))

    def process(self, context: PipelineContext) -> PipelineStageResult:
        metadata_updates: dict[str, Any] = {}
        upstream_metadata: dict[str, dict[str, Any]] = {}

        for upstream_id, upstream_input in sorted(context.upstream_inputs.items()):
            upstream_metadata[upstream_id] = deepcopy(upstream_input.metadata)
            keys = self.metadata_keys or tuple(upstream_input.metadata.keys())
            for key in keys:
                if key in upstream_input.metadata:
                    metadata_updates[key] = deepcopy(upstream_input.metadata[key])

        if self.include_upstream_metadata:
            metadata_updates["upstream_metadata"] = upstream_metadata
            metadata_updates["merged_upstream_ids"] = tuple(upstream_metadata.keys())

        return PipelineStageResult(metadata_updates=metadata_updates)
