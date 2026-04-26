from __future__ import annotations

from dataclasses import dataclass, field

from nvr_common.pipeline.named_pipeline import NamedPipeline
from nvr_common.pipeline.pipeline_edge import PipelineEdge
from nvr_common.pipeline.pipeline_validation_error import PipelineValidationError


@dataclass(frozen=True)
class PipelineGraph:
    pipelines: tuple[NamedPipeline, ...] = field(default_factory=tuple)
    edges: tuple[PipelineEdge, ...] = field(default_factory=tuple)

    def pipeline_by_id(self) -> dict[str, NamedPipeline]:
        return {pipeline.id: pipeline for pipeline in self.pipelines}

    def validate(self) -> None:
        pipeline_ids: set[str] = set()
        for pipeline in self.pipelines:
            if pipeline.id in pipeline_ids:
                raise PipelineValidationError(f"duplicate pipeline id: {pipeline.id}")
            pipeline_ids.add(pipeline.id)
            self._validate_stage_ids(pipeline)

        for edge in self.edges:
            if edge.source not in pipeline_ids:
                raise PipelineValidationError(f"unknown edge source: {edge.source}")
            if edge.target not in pipeline_ids:
                raise PipelineValidationError(f"unknown edge target: {edge.target}")
            if edge.source == edge.target:
                raise PipelineValidationError(
                    f"pipeline cannot link to itself: {edge.source}"
                )

        self._validate_cycles(pipeline_ids)

    def source_pipeline_ids(self) -> tuple[str, ...]:
        targets = {edge.target for edge in self.edges}
        return tuple(
            pipeline.id for pipeline in self.pipelines if pipeline.id not in targets
        )

    def upstream_ids(self, pipeline_id: str) -> tuple[str, ...]:
        return tuple(edge.source for edge in self.edges if edge.target == pipeline_id)

    def downstream_ids(self, pipeline_id: str) -> tuple[str, ...]:
        return tuple(edge.target for edge in self.edges if edge.source == pipeline_id)

    def topological_pipeline_ids(self) -> tuple[str, ...]:
        self.validate()
        indegree = {pipeline.id: 0 for pipeline in self.pipelines}
        downstream: dict[str, list[str]] = {
            pipeline.id: [] for pipeline in self.pipelines
        }
        for edge in self.edges:
            indegree[edge.target] += 1
            downstream[edge.source].append(edge.target)

        ready = [
            pipeline.id for pipeline in self.pipelines if indegree[pipeline.id] == 0
        ]
        ordered: list[str] = []
        while ready:
            pipeline_id = ready.pop(0)
            ordered.append(pipeline_id)
            for target_id in downstream[pipeline_id]:
                indegree[target_id] -= 1
                if indegree[target_id] == 0:
                    ready.append(target_id)

        return tuple(ordered)

    @staticmethod
    def _validate_stage_ids(pipeline: NamedPipeline) -> None:
        stage_ids: set[str] = set()
        for stage in pipeline.stages:
            if stage.id in stage_ids:
                raise PipelineValidationError(
                    f"duplicate stage id in pipeline {pipeline.id}: {stage.id}"
                )
            stage_ids.add(stage.id)

    def _validate_cycles(self, pipeline_ids: set[str]) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(pipeline_id: str) -> None:
            if pipeline_id in visiting:
                raise PipelineValidationError(
                    f"cycle detected at pipeline: {pipeline_id}"
                )
            if pipeline_id in visited:
                return

            visiting.add(pipeline_id)
            for downstream_id in self.downstream_ids(pipeline_id):
                visit(downstream_id)
            visiting.remove(pipeline_id)
            visited.add(pipeline_id)

        for pipeline_id in pipeline_ids:
            visit(pipeline_id)
