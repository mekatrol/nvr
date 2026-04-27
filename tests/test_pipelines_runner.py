import unittest

from nvr_common.pipeline import (
    NamedPipeline,
    PipelineGraph,
    PipelineGraphRunner,
    PipelineStageConfig,
)


class PipelineGraphRunnerTest(unittest.TestCase):
    def test_runs_linear_pipeline_and_skips_disabled_stage(self):
        graph = PipelineGraph(
            pipelines=(
                NamedPipeline(
                    id="preprocessing",
                    stages=(
                        PipelineStageConfig(
                            id="enabled",
                            module="tests.pipeline.append_stage",
                            class_name="AppendStage",
                            config={"suffix": "-enabled"},
                        ),
                        PipelineStageConfig(
                            id="disabled",
                            module="tests.pipeline.append_stage",
                            class_name="AppendStage",
                            enabled=False,
                            config={"suffix": "-disabled"},
                        ),
                    ),
                ),
            )
        )

        outputs = PipelineGraphRunner(graph).run(
            camera_id="driveway", frame_id="frame-1", image="image"
        )

        output = outputs["preprocessing"]
        self.assertEqual("image-enabled", output.output_image)
        self.assertEqual("image", output.metadata["enabled"])
        self.assertNotIn("disabled", output.metadata)

    def test_runs_multiple_pipelines_independently_in_config_order(self):
        graph = PipelineGraph(
            pipelines=(
                NamedPipeline(
                    id="preprocessing",
                    stages=(
                        PipelineStageConfig(
                            id="pre",
                            module="tests.pipeline.metadata_stage",
                            class_name="MetadataStage",
                            config={"key": "pre", "value": "done"},
                        ),
                    ),
                ),
                NamedPipeline(
                    id="object_detection",
                    stages=(
                        PipelineStageConfig(
                            id="detect",
                            module="tests.pipeline.metadata_stage",
                            class_name="MetadataStage",
                            config={"key": "branch", "value": "detect"},
                        ),
                    ),
                ),
                NamedPipeline(
                    id="thumbnail",
                    stages=(
                        PipelineStageConfig(
                            id="thumb",
                            module="tests.pipeline.metadata_stage",
                            class_name="MetadataStage",
                            config={"key": "branch", "value": "thumb"},
                        ),
                    ),
                ),
            ),
        )

        outputs = PipelineGraphRunner(graph).run(
            camera_id="driveway",
            frame_id="frame-1",
            image="image",
            metadata={"existing": "source"},
        )

        self.assertEqual("detect", outputs["object_detection"].metadata["branch"])
        self.assertEqual("thumb", outputs["thumbnail"].metadata["branch"])
        self.assertNotIn("pre", outputs["object_detection"].metadata)
        self.assertNotIn("pre", outputs["thumbnail"].metadata)

    def test_pipeline_reference_runs_inline_as_ordered_stage(self):
        graph = PipelineGraph(
            pipelines=(
                NamedPipeline(
                    id="preprocessing",
                    stages=(
                        PipelineStageConfig(
                            id="pre",
                            module="tests.pipeline.append_stage",
                            class_name="AppendStage",
                            config={"suffix": "-pre"},
                        ),
                    ),
                ),
                NamedPipeline(
                    id="child",
                    stages=(
                        PipelineStageConfig(
                            id="child-stage",
                            module="tests.pipeline.append_stage",
                            class_name="AppendStage",
                            config={"suffix": "-child"},
                        ),
                    ),
                ),
                NamedPipeline(
                    id="parent",
                    stages=(
                        PipelineStageConfig(
                            id="start",
                            module="tests.pipeline.append_stage",
                            class_name="AppendStage",
                            config={"suffix": "-start"},
                        ),
                        PipelineStageConfig(
                            id="child",
                            pipeline="child",
                        ),
                        PipelineStageConfig(
                            id="end",
                            module="tests.pipeline.append_stage",
                            class_name="AppendStage",
                            config={"suffix": "-end"},
                        ),
                    ),
                ),
            )
        )

        outputs = PipelineGraphRunner(graph).run(
            camera_id="driveway", frame_id="frame-1", image="original"
        )

        self.assertEqual("original-start-child-end", outputs["parent"].output_image)


if __name__ == "__main__":
    unittest.main()
