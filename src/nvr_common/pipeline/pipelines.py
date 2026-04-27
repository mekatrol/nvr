from __future__ import annotations

from dataclasses import dataclass, field

from nvr_common.pipeline.named_pipeline import NamedPipeline
from nvr_common.pipeline.pipeline_validation_error import PipelineValidationError


@dataclass(frozen=True)
class PipelineGraph:
    pipelines: tuple[NamedPipeline, ...] = field(default_factory=tuple)

    def pipeline_by_id(self) -> dict[str, NamedPipeline]:
        return {pipeline.id: pipeline for pipeline in self.pipelines}

    def validate(self) -> None:
        pipeline_ids: set[str] = set()
        for pipeline in self.pipelines:
            if pipeline.id in pipeline_ids:
                raise PipelineValidationError(f"duplicate pipeline id: {pipeline.id}")
            pipeline_ids.add(pipeline.id)
            self._validate_stage_ids(pipeline)

        for pipeline in self.pipelines:
            for stage in pipeline.stages:
                if not stage.pipeline:
                    continue
                if stage.pipeline not in pipeline_ids:
                    raise PipelineValidationError(
                        f"unknown pipeline reference: {stage.pipeline}"
                    )
                if stage.pipeline == pipeline.id:
                    raise PipelineValidationError(
                        f"pipeline cannot reference itself: {pipeline.id}"
                    )

        self._validate_reference_cycles()

    def source_pipeline_ids(self) -> tuple[str, ...]:
        referenced = {
            stage.pipeline
            for pipeline in self.pipelines
            for stage in pipeline.stages
            if stage.pipeline
        }
        return tuple(
            pipeline.id for pipeline in self.pipelines if pipeline.id not in referenced
        )

    def upstream_ids(self, pipeline_id: str) -> tuple[str, ...]:
        return ()

    def downstream_ids(self, pipeline_id: str) -> tuple[str, ...]:
        return ()

    def topological_pipeline_ids(self) -> tuple[str, ...]:
        self.validate()
        return tuple(pipeline.id for pipeline in self.pipelines)

    @staticmethod
    def _validate_stage_ids(pipeline: NamedPipeline) -> None:
        stage_ids: set[str] = set()
        for stage in pipeline.stages:
            if stage.id in stage_ids:
                raise PipelineValidationError(
                    f"duplicate stage id in pipeline {pipeline.id}: {stage.id}"
                )
            stage_ids.add(stage.id)

    def _validate_reference_cycles(self) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()
        pipeline_by_id = self.pipeline_by_id()

        def visit(pipeline_id: str) -> None:
            if pipeline_id in visiting:
                raise PipelineValidationError(
                    f"cycle detected at pipeline: {pipeline_id}"
                )
            if pipeline_id in visited:
                return

            visiting.add(pipeline_id)
            for stage in pipeline_by_id[pipeline_id].stages:
                if stage.pipeline:
                    visit(stage.pipeline)
            visiting.remove(pipeline_id)
            visited.add(pipeline_id)

        for pipeline in self.pipelines:
            visit(pipeline.id)
