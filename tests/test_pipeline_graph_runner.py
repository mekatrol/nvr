import unittest

from nvr_common.pipeline import (
    NamedPipeline,
    PipelineEdge,
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

    def test_fans_out_with_isolated_branch_metadata(self):
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
            edges=(
                PipelineEdge(source="preprocessing", target="object_detection"),
                PipelineEdge(source="preprocessing", target="thumbnail"),
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
        self.assertEqual("done", outputs["object_detection"].metadata["pre"])
        self.assertEqual("done", outputs["thumbnail"].metadata["pre"])

    def test_fan_in_receives_required_upstream_inputs(self):
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
                    id="object_detection",
                    stages=(
                        PipelineStageConfig(
                            id="detect",
                            module="tests.pipeline.append_stage",
                            class_name="AppendStage",
                            config={"suffix": "-detect"},
                        ),
                    ),
                ),
                NamedPipeline(
                    id="thumbnail",
                    stages=(
                        PipelineStageConfig(
                            id="thumb",
                            module="tests.pipeline.append_stage",
                            class_name="AppendStage",
                            config={"suffix": "-thumb"},
                        ),
                    ),
                ),
                NamedPipeline(
                    id="post_processing",
                    required_inputs=("object_detection", "thumbnail"),
                    stages=(
                        PipelineStageConfig(
                            id="combine",
                            module="tests.pipeline.context_capture_stage",
                            class_name="ContextCaptureStage",
                            config={"value": "configured"},
                        ),
                    ),
                ),
            ),
            edges=(
                PipelineEdge(source="preprocessing", target="object_detection"),
                PipelineEdge(source="preprocessing", target="thumbnail"),
                PipelineEdge(source="object_detection", target="post_processing"),
                PipelineEdge(source="thumbnail", target="post_processing"),
            ),
        )

        outputs = PipelineGraphRunner(graph).run(
            camera_id="driveway", frame_id="frame-1", image="original"
        )

        metadata = outputs["post_processing"].metadata
        self.assertEqual("original", metadata["original"])
        self.assertEqual(("object_detection", "thumbnail"), metadata["upstream_ids"])
        self.assertEqual("configured", metadata["config_value"])
        self.assertNotIn("detect", metadata)
        self.assertNotIn("thumb", metadata)


if __name__ == "__main__":
    unittest.main()
