import unittest

from nvr_common.pipeline import (
    NamedPipeline,
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
