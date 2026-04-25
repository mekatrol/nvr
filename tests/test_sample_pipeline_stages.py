import unittest

import numpy as np

from nvr_common.pipeline import (
    NamedPipeline,
    PipelineEdge,
    PipelineGraph,
    PipelineGraphRunner,
    PipelineStageConfig,
)


class SamplePipelineStagesTest(unittest.TestCase):
    def test_crop_stage_clips_generated_image(self):
        image = self._image(width=10, height=8)
        graph = PipelineGraph(
            pipelines=(
                NamedPipeline(
                    id="preprocessing",
                    stages=(
                        PipelineStageConfig(
                            id="crop",
                            module="nvr_common.pipeline.sample_stages.crop_stage",
                            class_name="CropStage",
                            config={"x": 2, "y": 1, "width": 4, "height": 3},
                        ),
                    ),
                ),
            )
        )

        outputs = PipelineGraphRunner(graph).run(
            camera_id="driveway", frame_id="frame-1", image=image
        )

        output = outputs["preprocessing"]
        self.assertEqual((3, 4, 3), output.output_image.shape)
        np.testing.assert_array_equal(output.output_image, image[1:4, 2:6])
        self.assertEqual(
            {"x": 2, "y": 1, "width": 4, "height": 3},
            output.metadata["crop"],
        )

    def test_resize_stage_preserves_aspect_ratio_when_height_is_missing(self):
        image = self._image(width=10, height=6)
        graph = PipelineGraph(
            pipelines=(
                NamedPipeline(
                    id="thumbnail",
                    stages=(
                        PipelineStageConfig(
                            id="resize",
                            module="nvr_common.pipeline.sample_stages.resize_stage",
                            class_name="ResizeStage",
                            config={"width": 5},
                        ),
                    ),
                ),
            )
        )

        outputs = PipelineGraphRunner(graph).run(
            camera_id="driveway", frame_id="frame-1", image=image
        )

        output = outputs["thumbnail"]
        self.assertEqual((3, 5, 3), output.output_image.shape)
        self.assertEqual({"width": 5, "height": 3}, output.metadata["resize"])

    def test_sample_graph_fans_out_fans_in_and_skips_disabled_stage(self):
        image = self._image(width=10, height=8)
        graph = PipelineGraph(
            pipelines=(
                NamedPipeline(
                    id="preprocessing",
                    stages=(
                        PipelineStageConfig(
                            id="crop",
                            module="nvr_common.pipeline.sample_stages.crop_stage",
                            class_name="CropStage",
                            config={"x": 1, "y": 2, "width": 6, "height": 4},
                        ),
                        PipelineStageConfig(
                            id="disabled-resize",
                            module="nvr_common.pipeline.sample_stages.resize_stage",
                            class_name="ResizeStage",
                            enabled=False,
                            config={"width": 1, "height": 1},
                        ),
                    ),
                ),
                NamedPipeline(
                    id="object_detection",
                    stages=(
                        PipelineStageConfig(
                            id="detect-metadata",
                            module=(
                                "nvr_common.pipeline.sample_stages."
                                "metadata_annotation_stage"
                            ),
                            class_name="MetadataAnnotationStage",
                            config={"metadata": {"detected": "person"}},
                        ),
                    ),
                ),
                NamedPipeline(
                    id="thumbnail",
                    stages=(
                        PipelineStageConfig(
                            id="thumbnail-resize",
                            module="nvr_common.pipeline.sample_stages.resize_stage",
                            class_name="ResizeStage",
                            config={"width": 3, "height": 2},
                        ),
                    ),
                ),
                NamedPipeline(
                    id="post_processing",
                    required_inputs=("object_detection", "thumbnail"),
                    stages=(
                        PipelineStageConfig(
                            id="combine-metadata",
                            module=(
                                "nvr_common.pipeline.sample_stages."
                                "metadata_annotation_stage"
                            ),
                            class_name="MetadataAnnotationStage",
                            config={"metadata": {"combined": True}},
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
            camera_id="driveway", frame_id="frame-1", image=image
        )

        self.assertEqual((4, 6, 3), outputs["preprocessing"].output_image.shape)
        self.assertNotEqual((1, 1, 3), outputs["preprocessing"].output_image.shape)
        self.assertEqual((4, 6, 3), outputs["object_detection"].output_image.shape)
        self.assertEqual((2, 3, 3), outputs["thumbnail"].output_image.shape)

        self.assertEqual("person", outputs["object_detection"].metadata["detected"])
        self.assertTrue(outputs["post_processing"].metadata["combined"])
        self.assertEqual(
            ("object_detection", "thumbnail"),
            outputs["post_processing"].metadata["combine-metadata.upstream_ids"],
        )

    @staticmethod
    def _image(width, height):
        return np.arange(width * height * 3, dtype=np.uint8).reshape(
            height, width, 3
        )


if __name__ == "__main__":
    unittest.main()
