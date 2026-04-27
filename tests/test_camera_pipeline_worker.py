import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from nvr_background.pipeline.camera_pipeline_worker import CameraPipelineWorker
from nvr_background.pipeline.image_file_frame_source import ImageFileFrameSource
from tests.config_test_helpers import reset_config_singleton, set_config_env, write_config


class CameraPipelineWorkerTest(unittest.TestCase):
    def tearDown(self):
        reset_config_singleton()

    def test_runs_pipeline_once_from_image_fixture(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            image_path = temp_path / "frame.jpg"
            config_path = temp_path / "config.yaml"
            cv2.imwrite(str(image_path), np.zeros((8, 10, 3), dtype=np.uint8))
            write_config(
                config_path,
                {
                    "enabled": True,
                    "frame_interval_seconds": 0.1,
                    "pipelines": [
                        {
                            "id": "preprocessing",
                            "enabled": True,
                            "stages": [
                                {
                                    "id": "crop",
                                    "enabled": True,
                                    "module": (
                                        "nvr_common.pipeline.sample_stages.crop_stage"
                                    ),
                                    "class": "CropStage",
                                    "config": {
                                        "x": 0,
                                        "y": 0,
                                        "width": 5,
                                        "height": 4,
                                    },
                                }
                            ],
                        }
                    ],
                    "edges": [],
                },
            )
            set_config_env(config_path)

            worker = CameraPipelineWorker(
                "driveway", frame_source=ImageFileFrameSource(str(image_path))
            )
            outputs = worker.run_once()

            self.assertEqual((4, 5, 3), outputs["preprocessing"].output_image.shape)

    def test_drops_bad_frame_without_running_pipeline(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_path = temp_path / "config.yaml"
            write_config(
                config_path,
                {
                    "enabled": True,
                    "frame_interval_seconds": 0.1,
                    "pipelines": [
                        {
                            "id": "preprocessing",
                            "enabled": True,
                            "stages": [
                                {
                                    "id": "crop",
                                    "enabled": True,
                                    "module": (
                                        "nvr_common.pipeline.sample_stages.crop_stage"
                                    ),
                                    "class": "CropStage",
                                    "config": {
                                        "x": 0,
                                        "y": 0,
                                        "width": 5,
                                        "height": 4,
                                    },
                                }
                            ],
                        }
                    ],
                    "edges": [],
                },
            )
            set_config_env(config_path)
            logger = FakeLogger()

            worker = CameraPipelineWorker(
                "driveway", frame_source=GreenFrameSource(), logger=logger
            )
            outputs = worker.run_once()

            self.assertEqual({}, outputs)
            self.assertIsNone(worker.last_outputs)
            self.assertIn("Dropping bad pipeline frame", logger.warnings[0])

class GreenFrameSource:
    def read(self):
        frame = np.zeros((80, 100, 3), dtype=np.uint8)
        frame[:, :30] = [70, 70, 70]
        frame[:, 30:55] = [245, 245, 245]
        frame[:, 55:] = [0, 120, 0]
        return frame


class FakeLogger:
    def __init__(self):
        self.warnings = []

    def warning(self, message, *args):
        self.warnings.append(message % args)


if __name__ == "__main__":
    unittest.main()
