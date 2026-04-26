import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from nvr_common.config import Config
from nvr_web.debug_api_state import DebugApiState
from tests.config_test_helpers import (
    reset_config_singleton,
    set_config_env,
    write_config,
)
from tests.pipeline.testable_debug_api_handler import TestableDebugApiHandler


class DebugApiTest(unittest.TestCase):
    def tearDown(self):
        reset_config_singleton()

    def test_debug_session_steps_and_breakpoints(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self._config(Path(temp_dir))
            state = DebugApiState(config, FakeFrameSource)
            session = state.load_camera_frame("driveway")

            session.add_breakpoint("preprocessing", "annotate")
            records = session.run()

            self.assertEqual(1, len(records))
            self.assertEqual("completed", records[0].status)
            self.assertEqual("completed", session.snapshot()["status"])

    def test_http_api_lists_cameras_and_runs_step(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self._config(Path(temp_dir))
            TestableDebugApiHandler.api_state = DebugApiState(config, FakeFrameSource)
            cameras_handler = TestableDebugApiHandler("/api/cameras")
            cameras_handler.do_GET()
            state_handler = TestableDebugApiHandler(
                "/api/debug/command",
                method="POST",
                body=json.dumps({"camera_id": "driveway", "command": "run"}).encode(
                    "utf-8"
                ),
            )
            state_handler.do_POST()

            cameras = json.loads(cameras_handler.wfile.getvalue().decode("utf-8"))
            state = json.loads(state_handler.wfile.getvalue().decode("utf-8"))

            self.assertEqual("driveway", cameras["cameras"][0]["id"])
            self.assertEqual("completed", state["records"][0]["status"])
            self.assertTrue(
                state["records"][0]["output_preview"].startswith(
                    "data:image/jpeg;base64,"
                )
            )
            self.assertEqual([8, 10, 3], state["records"][0]["input_shape"])

    def _config(self, temp_path):
        config_path = temp_path / "config.yaml"
        write_config(
            config_path,
            {
                "enabled": True,
                "frame_interval_seconds": 1,
                "pipelines": [
                    {
                        "id": "preprocessing",
                        "enabled": True,
                        "stages": [
                            {
                                "id": "annotate",
                                "enabled": True,
                                "module": (
                                    "nvr_common.pipeline.sample_stages."
                                    "metadata_annotation_stage"
                                ),
                                "class": "MetadataAnnotationStage",
                                "config": {"metadata": {"ready": True}},
                            }
                        ],
                    }
                ],
                "edges": [],
            },
        )
        set_config_env(config_path)
        return Config()


class FakeFrameSource:
    def __init__(self, source):
        self.source = source
        self.closed = False

    def read(self):
        return np.full((8, 10, 3), 120, dtype=np.uint8)

    def close(self):
        self.closed = True


if __name__ == "__main__":
    unittest.main()
