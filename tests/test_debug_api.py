import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import yaml

from nvr_background.pipeline.opencv_frame_source import OpenCvFrameSource
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

    def test_debug_session_reuses_open_frame_source_between_runs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            CountingFrameSource.instances = []
            config = self._config(Path(temp_dir))
            state = DebugApiState(config, CountingFrameSource)

            state.load_camera_frame("driveway")
            state.load_camera_frame("driveway")

            self.assertEqual(1, len(CountingFrameSource.instances))
            self.assertEqual(2, CountingFrameSource.instances[0].reads)

    def test_debug_session_drops_bad_frame_without_running_pipeline(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = FakeLogger()
            config = self._config(Path(temp_dir))
            TestableDebugApiHandler.api_state = DebugApiState(
                config, GreenFrameSource, logger=logger
            )

            run_handler = TestableDebugApiHandler(
                "/api/debug/command",
                method="POST",
                body=json.dumps(
                    {"camera_id": "driveway", "command": "run"}
                ).encode("utf-8"),
            )
            run_handler.do_POST()
            debug_state = json.loads(run_handler.wfile.getvalue().decode("utf-8"))

            self.assertEqual(200, run_handler.status)
            self.assertEqual("completed", debug_state["status"])
            self.assertEqual([], debug_state["records"])
            self.assertIn("Dropping bad pipeline frame", logger.warnings[0])

    def test_opencv_frame_source_defaults_rtsp_to_tcp_transport(self):
        original_options = os.environ.pop("OPENCV_FFMPEG_CAPTURE_OPTIONS", None)
        try:
            frame_source = OpenCvFrameSource("rtsp://camera/stream")
            frame_source._configure_rtsp_transport()

            self.assertEqual(
                "rtsp_transport;tcp",
                os.environ.get("OPENCV_FFMPEG_CAPTURE_OPTIONS"),
            )
        finally:
            if original_options is None:
                os.environ.pop("OPENCV_FFMPEG_CAPTURE_OPTIONS", None)
            else:
                os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = original_options

    def test_opencv_frame_source_reopens_once_after_failed_read(self):
        captures = [
            FakeCvCapture([(False, None)]),
            FakeCvCapture(
                [(True, np.full((2, 3, 3), 255, dtype=np.uint8)), (False, None)]
            ),
        ]

        with patch(
            "nvr_background.pipeline.opencv_frame_source.cv2.VideoCapture",
            side_effect=captures,
        ):
            frame_source = OpenCvFrameSource("rtsp://camera/stream")
            frame = frame_source.read()

        self.assertEqual((2, 3, 3), frame.shape)
        self.assertTrue(captures[0].released)
        self.assertTrue(captures[1].opened)

    def test_opencv_frame_source_discards_startup_frames_and_returns_latest(self):
        frames = [
            (True, np.full((2, 3, 3), 10, dtype=np.uint8)),
            (True, np.full((2, 3, 3), 20, dtype=np.uint8)),
            (True, np.full((2, 3, 3), 30, dtype=np.uint8)),
            (False, None),
        ]
        capture = FakeCvCapture(frames)

        with patch(
            "nvr_background.pipeline.opencv_frame_source.cv2.VideoCapture",
            return_value=capture,
        ):
            frame_source = OpenCvFrameSource(
                "rtsp://camera/stream", warmup_frames=4, read_drain_frames=3
            )
            frame = frame_source.read()

        self.assertEqual(4, capture.grabs)
        self.assertEqual(30, int(frame[0, 0, 0]))

    def test_config_creates_pipeline_storage_directory_on_load(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            self._config(temp_path)

            self.assertTrue((temp_path / "pipeline_config").is_dir())
            self.assertTrue((temp_path / "pipeline_config" / "pipelines").is_dir())
            self.assertTrue((temp_path / "pipeline_config" / "deployed").is_dir())

    def test_pipeline_config_save_does_not_modify_deployed_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config = self._config(temp_path)
            TestableDebugApiHandler.api_state = DebugApiState(config, FakeFrameSource)

            save_handler = TestableDebugApiHandler(
                "/api/pipeline_config/pipelines",
                method="POST",
                body=json.dumps(
                    {
                        "enabled": True,
                        "frame_interval_seconds": 2,
                        "pipelines": [
                            {"id": "pipelines-only", "enabled": True, "stages": []}
                        ],
                        "edges": [],
                    }
                ).encode("utf-8"),
            )
            save_handler.do_POST()

            config_data = yaml.safe_load((temp_path / "config.yaml").read_text())
            pipelines_data = yaml.safe_load(
                (
                    temp_path / "pipeline_config" / "pipelines" / "pipelines.yaml"
                ).read_text()
            )

            self.assertEqual(200, save_handler.status)
            self.assertEqual(
                "preprocessing", config_data["pipelines"]["pipelines"][0]["id"]
            )
            self.assertEqual(
                "pipelines-only", pipelines_data["pipelines"][0]["id"]
            )

    def test_pipeline_config_deploy_updates_deployed_file_and_reloads_sessions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config = self._config(temp_path)
            state = DebugApiState(config, FakeFrameSource)
            TestableDebugApiHandler.api_state = state
            self.assertIsNotNone(state.session("driveway"))
            pipelines_stage_path = (
                temp_path / "pipeline_config" / "pipelines" / "custom_stage.py"
            )
            pipelines_stage_path.write_text(
                "from nvr_common.pipeline import PipelineStageResult\n"
                "\n"
                "class CustomStage:\n"
                "    def __init__(self, config):\n"
                "        self.config = config\n"
                "\n"
                "    def process(self, context):\n"
                "        return PipelineStageResult(output_image=context.current_image)\n",
                encoding="utf-8",
            )

            save_handler = TestableDebugApiHandler(
                "/api/pipeline_config/pipelines",
                method="POST",
                body=json.dumps(
                    {
                        "enabled": True,
                        "frame_interval_seconds": 2,
                        "pipelines": [
                            {
                                "id": "deployed-pipeline",
                                "enabled": True,
                                "stages": [
                                    {
                                        "id": "custom",
                                        "enabled": True,
                                        "filename": str(pipelines_stage_path),
                                        "class": "CustomStage",
                                        "config": {},
                                    }
                                ],
                            }
                        ],
                        "edges": [],
                    }
                ).encode("utf-8"),
            )
            save_handler.do_POST()
            deploy_handler = TestableDebugApiHandler(
                "/api/pipeline_config/pipelines/deploy"
            )
            deploy_handler.do_POST()

            config_data = yaml.safe_load((temp_path / "config.yaml").read_text())
            pipelines_handler = TestableDebugApiHandler("/api/pipelines")
            pipelines_handler.do_GET()
            pipelines = json.loads(pipelines_handler.wfile.getvalue().decode("utf-8"))
            deployed_data = yaml.safe_load(
                (
                    temp_path / "pipeline_config" / "deployed" / "pipelines.yaml"
                ).read_text()
            )
            deployed_stage_path = (
                temp_path / "pipeline_config" / "deployed" / "custom_stage.py"
            )

            self.assertEqual(200, deploy_handler.status)
            self.assertEqual(
                "preprocessing", config_data["pipelines"]["pipelines"][0]["id"]
            )
            self.assertEqual(
                "deployed-pipeline",
                deployed_data["pipelines"][0]["id"],
            )
            self.assertTrue(deployed_stage_path.is_file())
            self.assertEqual(
                str(deployed_stage_path),
                deployed_data["pipelines"][0]["stages"][0]["filename"],
            )
            self.assertEqual("deployed-pipeline", pipelines["pipelines"][0]["id"])
            self.assertEqual({}, state.sessions)

    def test_generate_example_resize_pipeline_writes_to_pipeline_storage(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config = self._config(temp_path)
            TestableDebugApiHandler.api_state = DebugApiState(config, FakeFrameSource)

            handler = TestableDebugApiHandler("/api/pipelines/examples/resize")
            handler.do_POST()

            response = json.loads(handler.wfile.getvalue().decode("utf-8"))
            pipelines_path = (
                temp_path / "pipeline_config" / "pipelines" / "pipelines.yaml"
            )
            stage_path = (
                temp_path / "pipeline_config" / "pipelines" / "example_resize_stage.py"
            )
            deployed_path = temp_path / "pipeline_config" / "deployed" / "pipelines.yaml"
            deployed_stage_path = (
                temp_path / "pipeline_config" / "deployed" / "example_resize_stage.py"
            )
            pipelines_data = yaml.safe_load(pipelines_path.read_text(encoding="utf-8"))
            response_pipeline = next(
                pipeline
                for pipeline in response["pipelines"]
                if pipeline["id"] == "example-resize"
            )
            pipeline_config_pipeline = next(
                pipeline
                for pipeline in pipelines_data["pipelines"]
                if pipeline["id"] == "example-resize"
            )

            self.assertEqual(200, handler.status)
            self.assertEqual(0.5, response["frame_interval_seconds"])
            self.assertTrue(stage_path.is_file())
            self.assertFalse(deployed_path.exists())
            self.assertFalse(deployed_stage_path.exists())
            self.assertEqual("example-resize", response_pipeline["id"])
            self.assertTrue(
                any(
                    pipeline["id"] == "preprocessing"
                    for pipeline in pipelines_data["pipelines"]
                )
            )
            self.assertEqual(
                str(stage_path),
                pipeline_config_pipeline["stages"][0]["filename"],
            )
            self.assertEqual(
                {"output_width": 640, "output_height": 360},
                pipeline_config_pipeline["stages"][0]["config"],
            )

            run_handler = TestableDebugApiHandler(
                "/api/debug/command",
                method="POST",
                body=json.dumps(
                    {"camera_id": "driveway", "command": "run"}
                ).encode("utf-8"),
            )
            run_handler.do_POST()
            debug_state = json.loads(run_handler.wfile.getvalue().decode("utf-8"))

            self.assertEqual(200, run_handler.status)
            self.assertTrue(
                any(
                    record["pipeline_id"] == "example-resize"
                    and record["stage_id"] == "resize-frame"
                    for record in debug_state["records"]
                )
            )

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
            pipeline_config_storage_path="pipeline_config",
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


class CountingFrameSource:
    instances = []

    def __init__(self, source):
        self.source = source
        self.reads = 0
        self.closed = False
        self.instances.append(self)

    def read(self):
        self.reads += 1
        return np.full((8, 10, 3), self.reads, dtype=np.uint8)

    def close(self):
        self.closed = True


class GreenFrameSource:
    def __init__(self, source):
        self.source = source

    def read(self):
        frame = np.zeros((80, 100, 3), dtype=np.uint8)
        frame[:, :30] = [70, 70, 70]
        frame[:, 30:55] = [245, 245, 245]
        frame[:, 55:] = [0, 120, 0]
        return frame

    def close(self):
        return None


class FakeLogger:
    def __init__(self):
        self.warnings = []

    def warning(self, message, *args):
        self.warnings.append(message % args)


class FakeCvCapture:
    def __init__(self, reads):
        self.reads = list(reads)
        self.opened = False
        self.released = False
        self.grabs = 0

    def set(self, *_args):
        return True

    def open(self, _source):
        self.opened = True
        return True

    def isOpened(self):
        return self.opened

    def read(self):
        if not self.reads:
            return False, None
        return self.reads.pop(0)

    def grab(self):
        self.grabs += 1
        return True

    def release(self):
        self.released = True
        self.opened = False


if __name__ == "__main__":
    unittest.main()
