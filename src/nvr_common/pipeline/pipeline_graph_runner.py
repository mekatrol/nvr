from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from time import perf_counter
from typing import Any

from nvr_common.pipeline.pipeline_context import PipelineContext
from nvr_common.pipeline.pipeline_graph import PipelineGraph
from nvr_common.pipeline.pipeline_input import PipelineInput
from nvr_common.pipeline.pipeline_output import PipelineOutput
from nvr_common.pipeline.pipeline_stage_loader import PipelineStageLoader
from nvr_common.pipeline.pipeline_stage_result import PipelineStageResult


class PipelineGraphRunner:
    def __init__(
        self,
        graph: PipelineGraph,
        stage_loader: PipelineStageLoader | None = None,
        logger: Any = None,
    ) -> None:
        graph.validate()
        self.graph = graph
        self.stage_loader = stage_loader or PipelineStageLoader()
        self.logger = logger
        self._stage_instances: dict[tuple[str, str], Any] = {}

    def run(
        self,
        camera_id: str,
        frame_id: str,
        image: Any,
        frame_timestamp: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, PipelineOutput]:
        pipeline_by_id = self.graph.pipeline_by_id()
        pending_inputs: dict[str, dict[str, PipelineInput]] = {}
        outputs: dict[str, PipelineOutput] = {}

        source_metadata = deepcopy(metadata or {})
        for pipeline_id in self.graph.source_pipeline_ids():
            pending_inputs[pipeline_id] = {
                "__source__": PipelineInput(
                    original_image=image,
                    current_image=image,
                    metadata=deepcopy(source_metadata),
                    camera_id=camera_id,
                    frame_id=frame_id,
                    frame_timestamp=frame_timestamp,
                )
            }

        for pipeline_id in self.graph.topological_pipeline_ids():
            pipeline = pipeline_by_id[pipeline_id]
            upstream_inputs = pending_inputs.get(pipeline_id, {})
            if not pipeline.enabled or not upstream_inputs:
                continue

            required_inputs = pipeline.required_inputs or self.graph.upstream_ids(
                pipeline_id
            )
            if required_inputs and not all(
                upstream_id in upstream_inputs for upstream_id in required_inputs
            ):
                continue

            output = self._run_pipeline(pipeline_id, upstream_inputs)
            outputs[pipeline_id] = output

            for downstream_id in self.graph.downstream_ids(pipeline_id):
                downstream_inputs = pending_inputs.setdefault(downstream_id, {})
                downstream_inputs[pipeline_id] = PipelineInput(
                    original_image=image,
                    current_image=output.output_image,
                    metadata=deepcopy(output.metadata),
                    camera_id=camera_id,
                    frame_id=frame_id,
                    frame_timestamp=frame_timestamp,
                    source_pipeline_id=pipeline_id,
                )

        return outputs

    def _run_pipeline(
        self, pipeline_id: str, upstream_inputs: dict[str, PipelineInput]
    ) -> PipelineOutput:
        pipeline = self.graph.pipeline_by_id()[pipeline_id]
        first_input = next(iter(upstream_inputs.values()))
        current_image = first_input.current_image
        metadata = self._initial_metadata(upstream_inputs)
        debug_artifacts: dict[str, Any] = {}
        events: list[Any] = []
        start_time = perf_counter()

        for stage_config in pipeline.stages:
            if not stage_config.enabled:
                continue

            stage = self._load_stage(pipeline_id, stage_config)
            context = PipelineContext(
                camera_id=first_input.camera_id,
                frame_id=first_input.frame_id,
                original_image=first_input.original_image,
                current_image=current_image,
                metadata=deepcopy(metadata),
                pipeline_id=pipeline_id,
                stage_id=stage_config.id,
                frame_timestamp=first_input.frame_timestamp,
                upstream_inputs=deepcopy(upstream_inputs),
                config=deepcopy(stage_config.config),
                logger=self.logger,
            )

            result = stage.process(context)
            if not isinstance(result, PipelineStageResult):
                raise TypeError(
                    f"stage {stage_config.id} returned {type(result).__name__}, "
                    "expected PipelineStageResult"
                )
            if result.output_image is not None:
                current_image = result.output_image
            metadata.update(deepcopy(result.metadata_updates))
            debug_artifacts.update(deepcopy(result.debug_artifacts))
            events.extend(result.events)

        return PipelineOutput(
            pipeline_id=pipeline_id,
            output_image=current_image,
            metadata=metadata,
            debug_artifacts=debug_artifacts,
            events=tuple(events),
            elapsed_seconds=perf_counter() - start_time,
            camera_id=first_input.camera_id,
            frame_id=first_input.frame_id,
            frame_timestamp=first_input.frame_timestamp,
        )

    @staticmethod
    def _initial_metadata(upstream_inputs: dict[str, PipelineInput]) -> dict[str, Any]:
        if len(upstream_inputs) == 1:
            first_input = next(iter(upstream_inputs.values()))
            return deepcopy(first_input.metadata)

        return {}

    def _load_stage(self, pipeline_id: str, stage_config: Any) -> Any:
        cache_key = (pipeline_id, stage_config.id)
        if cache_key not in self._stage_instances:
            self._stage_instances[cache_key] = self.stage_loader.load(stage_config)
        return self._stage_instances[cache_key]
