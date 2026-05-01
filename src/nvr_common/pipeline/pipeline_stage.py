from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum

from nvr_common.pipeline.pipeline_context import PipelineContext
from nvr_common.pipeline.pipeline_stage_result import PipelineStageResult


class PipelineStageFeature(Enum):
    ALLOW_POLYGONS = "AllowPolygons"


class PipelineStage(ABC):
    def get_features(self) -> set[PipelineStageFeature]:
        return set()

    @abstractmethod
    def process(self, context: PipelineContext) -> PipelineStageResult:
        raise NotImplementedError
