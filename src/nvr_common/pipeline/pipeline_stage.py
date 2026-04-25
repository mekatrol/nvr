from __future__ import annotations

from typing import Protocol

from nvr_common.pipeline.pipeline_context import PipelineContext
from nvr_common.pipeline.pipeline_stage_result import PipelineStageResult


class PipelineStage(Protocol):
    def process(self, context: PipelineContext) -> PipelineStageResult: ...
