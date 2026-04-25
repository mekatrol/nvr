from __future__ import annotations

from collections import deque
from copy import deepcopy
from datetime import datetime
from typing import Any

from nvr_common.pipeline import PipelineContext, PipelineGraph, PipelineInput
from nvr_common.pipeline.debug.stage_debug_record import StageDebugRecord
from nvr_common.pipeline.pipeline_stage_loader import PipelineStageLoader
from nvr_common.pipeline.pipeline_stage_result import PipelineStageResult


class PipelineDebugSession:
    def __init__(
        self,
        graph: PipelineGraph,
        stage_loader: PipelineStageLoader | None = None,
        max_records: int = 100,
    ) -> None:
        graph.validate()
        self.graph = graph
        self.stage_loader = stage_loader or PipelineStageLoader()
        self.max_records = max_records
        self.breakpoints: set[tuple[str, str | None]] = set()
        self.records: deque[StageDebugRecord] = deque(maxlen=max_records)
        self.status = "idle"
        self._steps: list[tuple[str, Any, Any]] = []
        self._cursor = 0
        self._stage_instances: dict[tuple[str, str], Any] = {}

    def load_frame(
        self,
        camera_id: str,
        frame_id: str,
        image: Any,
        frame_timestamp: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.records.clear()
        self._cursor = 0
        self._steps = self._build_steps(
            camera_id, frame_id, image, frame_timestamp, metadata or {}
        )
        self.status = "paused" if self._steps else "completed"

    def add_breakpoint(self, pipeline_id: str, stage_id: str | None = None) -> None:
        self.breakpoints.add((pipeline_id, stage_id))

    def clear_breakpoint(self, pipeline_id: str, stage_id: str | None = None) -> None:
        self.breakpoints.discard((pipeline_id, stage_id))

    def step(self) -> StageDebugRecord | None:
        if self._cursor >= len(self._steps):
            self.status = "completed"
            return None

        pipeline_id, stage_config, context = self._steps[self._cursor]
        self._cursor += 1
        record = self._execute_step(pipeline_id, stage_config, context)
        self.records.append(record)
        self.status = "completed" if self._cursor >= len(self._steps) else "paused"
        return record

    def step_over_pipeline(self) -> list[StageDebugRecord]:
        if self._cursor >= len(self._steps):
            self.status = "completed"
            return []

        pipeline_id = self._steps[self._cursor][0]
        records = []
        while self._cursor < len(self._steps) and self._steps[self._cursor][0] == pipeline_id:
            record = self.step()
            if record is not None:
                records.append(record)
        return records

    def run(self) -> list[StageDebugRecord]:
        self.status = "running"
        records = []
        while self._cursor < len(self._steps):
            pipeline_id, stage_config, _context = self._steps[self._cursor]
            if records and self._is_breakpoint(pipeline_id, stage_config.id):
                self.status = "paused"
                return records
            record = self.step()
            if record is not None:
                records.append(record)
        self.status = "completed"
        return records

    def snapshot(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "cursor": self._cursor,
            "total_steps": len(self._steps),
            "breakpoints": [
                {"pipeline_id": pipeline_id, "stage_id": stage_id}
                for pipeline_id, stage_id in sorted(self.breakpoints)
            ],
            "records": [record.__dict__ for record in self.records],
        }

    def _build_steps(
        self,
        camera_id: str,
        frame_id: str,
        image: Any,
        frame_timestamp: datetime | None,
        metadata: dict[str, Any],
    ) -> list[tuple[str, Any, PipelineContext]]:
        steps = []
        pending_inputs = {
            pipeline_id: {
                "__source__": PipelineInput(
                    original_image=image,
                    current_image=image,
                    metadata=deepcopy(metadata),
                    camera_id=camera_id,
                    frame_id=frame_id,
                    frame_timestamp=frame_timestamp,
                )
            }
            for pipeline_id in self.graph.source_pipeline_ids()
        }
        pipeline_by_id = self.graph.pipeline_by_id()

        for pipeline_id in self.graph.topological_pipeline_ids():
            pipeline = pipeline_by_id[pipeline_id]
            upstream_inputs = pending_inputs.get(pipeline_id, {})
            if not pipeline.enabled or not upstream_inputs:
                continue

            first_input = next(iter(upstream_inputs.values()))
            current_image = first_input.current_image
            branch_metadata = (
                deepcopy(first_input.metadata) if len(upstream_inputs) == 1 else {}
            )
            for stage_config in pipeline.stages:
                if not stage_config.enabled:
                    continue
                context = PipelineContext(
                    camera_id=camera_id,
                    frame_id=frame_id,
                    original_image=first_input.original_image,
                    current_image=current_image,
                    metadata=deepcopy(branch_metadata),
                    pipeline_id=pipeline_id,
                    stage_id=stage_config.id,
                    frame_timestamp=frame_timestamp,
                    upstream_inputs=deepcopy(upstream_inputs),
                    config=deepcopy(stage_config.config),
                )
                steps.append((pipeline_id, stage_config, context))

                result = self._run_stage(pipeline_id, stage_config, context)
                if result.output_image is not None:
                    current_image = result.output_image
                branch_metadata.update(deepcopy(result.metadata_updates))

            for downstream_id in self.graph.downstream_ids(pipeline_id):
                downstream_inputs = pending_inputs.setdefault(downstream_id, {})
                downstream_inputs[pipeline_id] = PipelineInput(
                    original_image=first_input.original_image,
                    current_image=current_image,
                    metadata=deepcopy(branch_metadata),
                    camera_id=camera_id,
                    frame_id=frame_id,
                    frame_timestamp=frame_timestamp,
                    source_pipeline_id=pipeline_id,
                )

        return steps

    def _execute_step(
        self, pipeline_id: str, stage_config: Any, context: PipelineContext
    ) -> StageDebugRecord:
        result = self._run_stage(pipeline_id, stage_config, context)
        metadata_after = deepcopy(context.metadata)
        metadata_after.update(deepcopy(result.metadata_updates))
        output_image = (
            result.output_image
            if result.output_image is not None
            else context.current_image
        )
        return StageDebugRecord(
            camera_id=context.camera_id,
            frame_id=context.frame_id,
            pipeline_id=pipeline_id,
            stage_id=stage_config.id,
            status="completed",
            metadata_before=deepcopy(context.metadata),
            metadata_after=metadata_after,
            input_shape=self._shape(context.current_image),
            output_shape=self._shape(output_image),
        )

    def _run_stage(
        self, pipeline_id: str, stage_config: Any, context: PipelineContext
    ) -> PipelineStageResult:
        stage = self._stage_instances.get((pipeline_id, stage_config.id))
        if stage is None:
            stage = self.stage_loader.load(stage_config)
            self._stage_instances[(pipeline_id, stage_config.id)] = stage
        result = stage.process(context)
        if not isinstance(result, PipelineStageResult):
            raise TypeError("debug stage returned an invalid result")
        return result

    def _is_breakpoint(self, pipeline_id: str, stage_id: str) -> bool:
        return (pipeline_id, None) in self.breakpoints or (
            pipeline_id,
            stage_id,
        ) in self.breakpoints

    @staticmethod
    def _shape(image: Any) -> tuple[int, ...] | None:
        shape = getattr(image, "shape", None)
        return tuple(shape) if shape is not None else None
