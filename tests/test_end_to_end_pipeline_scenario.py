import unittest

import numpy as np

from nvr_common.pipeline import (
    NamedPipeline,
    PipelineEdge,
    PipelineGraph,
    PipelineGraphRunner,
    PipelineStageConfig,
)
from nvr_common.pipeline.debug import PipelineDebugSession
from tests.pipeline.fake_mqtt_client import FakeMqttClient


class EndToEndPipelineScenarioTest(unittest.TestCase):
    def test_person_approach_scenario_publishes_one_mqtt_event(self):
        clients = []
        graph = self._scenario_graph(lambda: self._client_factory(clients))
        runner = PipelineGraphRunner(graph)
        image = np.zeros((40, 60, 3), dtype=np.uint8)

        first_outputs = runner.run(
            "driveway",
            "frame-1",
            image,
            metadata={"detections": [{"bbox": (10, 5, 8, 8), "track_id": "person-1"}]},
        )
        second_outputs = runner.run(
            "driveway",
            "frame-2",
            image,
            metadata={"detections": [{"bbox": (10, 18, 8, 8), "track_id": "person-1"}]},
        )
        third_outputs = runner.run(
            "driveway",
            "frame-3",
            image,
            metadata={"detections": [{"bbox": (22, 18, 8, 8), "track_id": "person-1"}]},
        )

        self.assertNotIn("mqtt", first_outputs)
        self.assertEqual((20, 30, 3), second_outputs["preprocessing"].output_image.shape)
        self.assertEqual((10, 15, 3), second_outputs["thumbnail"].output_image.shape)
        self.assertEqual(
            ("object_detection", "thumbnail"),
            second_outputs["post_processing"].metadata["merged_upstream_ids"],
        )
        self.assertTrue(second_outputs["approach_detection"].metadata["person_approaching"]["active"])
        self.assertTrue(second_outputs["mqtt_events"].metadata["mqtt"]["published"])
        self.assertNotIn("mqtt", third_outputs["mqtt_events"].metadata)
        self.assertEqual(1, len(clients))
        self.assertEqual("nvr/driveway/person-approaching", clients[0].published_topic)

    def test_debug_session_records_image_shapes_and_fan_in_metadata(self):
        graph = self._scenario_graph(FakeMqttClient)
        session = PipelineDebugSession(graph)
        image = np.zeros((40, 60, 3), dtype=np.uint8)
        session.load_frame(
            "driveway",
            "debug-frame",
            image,
            metadata={"detections": [{"bbox": (10, 5, 8, 8), "track_id": "person-1"}]},
        )

        records = session.run()

        crop_record = next(record for record in records if record.stage_id == "crop-driveway")
        thumbnail_record = next(record for record in records if record.stage_id == "make-thumbnail")
        post_record = next(record for record in records if record.stage_id == "combine-results")
        self.assertEqual((40, 60, 3), crop_record.input_shape)
        self.assertEqual((20, 30, 3), crop_record.output_shape)
        self.assertEqual((10, 15, 3), thumbnail_record.output_shape)
        self.assertEqual(
            ("object_detection", "thumbnail"),
            post_record.metadata_after["merged_upstream_ids"],
        )

    @staticmethod
    def _client_factory(clients):
        client = FakeMqttClient()
        clients.append(client)
        return client

    @staticmethod
    def _scenario_graph(client_factory):
        return PipelineGraph(
            pipelines=(
                NamedPipeline(
                    id="preprocessing",
                    stages=(
                        PipelineStageConfig(
                            id="crop-driveway",
                            module="nvr_common.pipeline.sample_stages.crop_stage",
                            class_name="CropStage",
                            config={"x": 0, "y": 0, "width": 30, "height": 20},
                        ),
                    ),
                ),
                NamedPipeline(
                    id="object_detection",
                    stages=(
                        PipelineStageConfig(
                            id="detect-person",
                            module=(
                                "nvr_common.pipeline.sample_stages."
                                "synthetic_person_detector_stage"
                            ),
                            class_name="SyntheticPersonDetectorStage",
                        ),
                        PipelineStageConfig(
                            id="track-person",
                            module="nvr_common.pipeline.sample_stages.movement_tracker_stage",
                            class_name="MovementTrackerStage",
                        ),
                    ),
                ),
                NamedPipeline(
                    id="thumbnail",
                    stages=(
                        PipelineStageConfig(
                            id="make-thumbnail",
                            module="nvr_common.pipeline.sample_stages.resize_stage",
                            class_name="ResizeStage",
                            config={"width": 15, "height": 10},
                        ),
                    ),
                ),
                NamedPipeline(
                    id="post_processing",
                    required_inputs=("object_detection", "thumbnail"),
                    stages=(
                        PipelineStageConfig(
                            id="combine-results",
                            module=(
                                "nvr_common.pipeline.sample_stages."
                                "merge_upstream_metadata_stage"
                            ),
                            class_name="MergeUpstreamMetadataStage",
                            config={"metadata_keys": ["detections", "tracks", "resize"]},
                        ),
                    ),
                ),
                NamedPipeline(
                    id="approach_detection",
                    stages=(
                        PipelineStageConfig(
                            id="approach-down",
                            module=(
                                "nvr_common.pipeline.sample_stages."
                                "approach_direction_stage"
                            ),
                            class_name="ApproachDirectionStage",
                            config={"direction": "down", "min_delta": 6},
                        ),
                    ),
                ),
                NamedPipeline(
                    id="mqtt_events",
                    stages=(
                        PipelineStageConfig(
                            id="mqtt-person-approaching",
                            module="nvr_common.pipeline.sample_stages.mqtt_event_stage",
                            class_name="MqttEventStage",
                            config={
                                "host": "broker.local",
                                "topic": "nvr/driveway/person-approaching",
                                "event_key": "person_approaching",
                                "cooldown_seconds": 60,
                                "client_factory": client_factory,
                            },
                        ),
                    ),
                ),
            ),
            edges=(
                PipelineEdge("preprocessing", "object_detection"),
                PipelineEdge("preprocessing", "thumbnail"),
                PipelineEdge("object_detection", "post_processing"),
                PipelineEdge("thumbnail", "post_processing"),
                PipelineEdge("post_processing", "approach_detection"),
                PipelineEdge("approach_detection", "mqtt_events"),
            ),
        )


if __name__ == "__main__":
    unittest.main()
