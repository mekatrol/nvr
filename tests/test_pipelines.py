import unittest

from nvr_common.pipeline import (
    NamedPipeline,
    PipelineEdge,
    PipelineGraph,
    PipelineStageConfig,
    PipelineValidationError,
)


class PipelineGraphTest(unittest.TestCase):
    def test_rejects_duplicate_pipeline_ids(self):
        graph = PipelineGraph(
            pipelines=(
                NamedPipeline(id="preprocessing"),
                NamedPipeline(id="preprocessing"),
            )
        )

        with self.assertRaisesRegex(
            PipelineValidationError, "duplicate pipeline id: preprocessing"
        ):
            graph.validate()

    def test_rejects_unknown_edge_reference(self):
        graph = PipelineGraph(
            pipelines=(NamedPipeline(id="preprocessing"),),
            edges=(PipelineEdge(source="preprocessing", target="missing"),),
        )

        with self.assertRaisesRegex(PipelineValidationError, "unknown edge target"):
            graph.validate()

    def test_rejects_cycles(self):
        graph = PipelineGraph(
            pipelines=(NamedPipeline(id="a"), NamedPipeline(id="b")),
            edges=(
                PipelineEdge(source="a", target="b"),
                PipelineEdge(source="b", target="a"),
            ),
        )

        with self.assertRaisesRegex(PipelineValidationError, "cycle detected"):
            graph.validate()

    def test_rejects_duplicate_stage_ids(self):
        graph = PipelineGraph(
            pipelines=(
                NamedPipeline(
                    id="preprocessing",
                    stages=(
                        PipelineStageConfig(
                            id="clip",
                            module="tests.pipeline.append_stage",
                            class_name="AppendStage",
                        ),
                        PipelineStageConfig(
                            id="clip",
                            module="tests.pipeline.append_stage",
                            class_name="AppendStage",
                        ),
                    ),
                ),
            )
        )

        with self.assertRaisesRegex(PipelineValidationError, "duplicate stage id"):
            graph.validate()


if __name__ == "__main__":
    unittest.main()
