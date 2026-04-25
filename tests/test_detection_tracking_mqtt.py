import unittest

import numpy as np

from nvr_common.pipeline import (
    NamedPipeline,
    PipelineGraph,
    PipelineGraphRunner,
    PipelineStageConfig,
)
from tests.pipeline.fake_mqtt_client import FakeMqttClient


class DetectionTrackingMqttTest(unittest.TestCase):
    def test_tracks_movement_and_emits_approach_event(self):
        graph = PipelineGraph(
            pipelines=(
                NamedPipeline(
                    id="approach",
                    stages=(
                        PipelineStageConfig(
                            id="detect",
                            module=(
                                "nvr_common.pipeline.sample_stages."
                                "synthetic_person_detector_stage"
                            ),
                            class_name="SyntheticPersonDetectorStage",
                        ),
                        PipelineStageConfig(
                            id="track",
                            module=(
                                "nvr_common.pipeline.sample_stages."
                                "movement_tracker_stage"
                            ),
                            class_name="MovementTrackerStage",
                        ),
                        PipelineStageConfig(
                            id="approach-down",
                            module=(
                                "nvr_common.pipeline.sample_stages."
                                "approach_direction_stage"
                            ),
                            class_name="ApproachDirectionStage",
                            config={"direction": "down", "min_delta": 2},
                        ),
                    ),
                ),
            )
        )
        runner = PipelineGraphRunner(graph)
        image = np.zeros((10, 10, 3), dtype=np.uint8)

        runner.run(
            "driveway",
            "1",
            image,
            metadata={"detections": [{"bbox": (1, 1, 2, 2), "track_id": "p1"}]},
        )
        outputs = runner.run(
            "driveway",
            "2",
            image,
            metadata={"detections": [{"bbox": (1, 5, 2, 2), "track_id": "p1"}]},
        )

        event = outputs["approach"].metadata["person_approaching"]
        self.assertTrue(event["active"])
        self.assertEqual(("p1",), event["track_ids"])

    def test_mqtt_stage_uses_fake_client_and_cooldown(self):
        clients = []

        def client_factory():
            client = FakeMqttClient()
            clients.append(client)
            return client

        graph = PipelineGraph(
            pipelines=(
                NamedPipeline(
                    id="mqtt",
                    stages=(
                        PipelineStageConfig(
                            id="mqtt-event",
                            module=(
                                "nvr_common.pipeline.sample_stages.mqtt_event_stage"
                            ),
                            class_name="MqttEventStage",
                            config={
                                "host": "broker.local",
                                "topic": "nvr/driveway/person",
                                "event_key": "person_approaching",
                                "cooldown_seconds": 60,
                                "client_factory": client_factory,
                            },
                        ),
                    ),
                ),
            )
        )
        runner = PipelineGraphRunner(graph)
        image = np.zeros((2, 2, 3), dtype=np.uint8)
        metadata = {"person_approaching": {"active": True, "track_ids": ("p1",)}}

        first = runner.run("driveway", "1", image, metadata=metadata)
        second = runner.run("driveway", "2", image, metadata=metadata)

        self.assertTrue(first["mqtt"].metadata["mqtt"]["published"])
        self.assertEqual("cooldown", second["mqtt"].metadata["mqtt"]["reason"])
        self.assertEqual(1, len(clients))
        self.assertEqual("nvr/driveway/person", clients[0].published_topic)

if __name__ == "__main__":
    unittest.main()
