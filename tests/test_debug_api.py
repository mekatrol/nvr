import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import yaml

from nvr_background.pipeline.ffmpeg_rtsp_frame_source import FfmpegRtspFrameSource
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
                body=json.dumps({"camera_id": "driveway", "command": "step"}).encode(
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
                config, EmptyFrameSource, logger=logger
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

    def test_ffmpeg_rtsp_frame_source_builds_gpu_decode_command(self):
        frame_source = FfmpegRtspFrameSource(
            "rtsp://camera/stream",
            ffmpeg_binary="/usr/bin/ffmpeg",
            hardware_acceleration="auto",
        )

        command = frame_source._build_command()

        self.assertIn("-hwaccel", command)
        self.assertIn("auto", command)
        self.assertIn("-vf", command)
        self.assertIn("fps=1", command)
        self.assertIn("-vcodec", command)
        self.assertIn("mjpeg", command)

    def test_opencv_frame_source_reopens_once_after_failed_file_read(self):
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
            frame_source = OpenCvFrameSource("file.mp4", warmup_frames=0)
            frame = frame_source.read()

        self.assertEqual((2, 3, 3), frame.shape)
        self.assertTrue(captures[0].released)
        self.assertTrue(captures[1].opened)

    def test_opencv_frame_source_discards_file_startup_frames_and_returns_latest(self):
        frames = [
            (True, np.full((2, 3, 3), 10, dtype=np.uint8)),
            (True, np.full((2, 3, 3), 20, dtype=np.uint8)),
            (True, np.full((2, 3, 3), 30, dtype=np.uint8)),
            (True, np.full((2, 3, 3), 40, dtype=np.uint8)),
            (False, None),
        ]
        capture = FakeCvCapture(frames)

        with patch(
            "nvr_background.pipeline.opencv_frame_source.cv2.VideoCapture",
            return_value=capture,
        ):
            frame_source = OpenCvFrameSource(
                "file.mp4", warmup_frames=2, read_drain_frames=3
            )
            frame = frame_source.read()

        self.assertEqual(40, int(frame[0, 0, 0]))

    def test_opencv_frame_source_uses_ffmpeg_source_for_rtsp(self):
        rtsp_source = FakeRtspFrameSource()

        with patch(
            "nvr_background.pipeline.opencv_frame_source.FfmpegRtspFrameSource",
            return_value=rtsp_source,
        ) as frame_source_class:
            frame_source = OpenCvFrameSource(
                "rtsp://camera/stream",
                ffmpeg_binary="/usr/bin/ffmpeg",
            )
            frame = frame_source.read()

        self.assertEqual(40, int(frame[0, 0, 0]))
        self.assertTrue(rtsp_source.opened)
        frame_source_class.assert_called_once_with(
            "rtsp://camera/stream",
            ffmpeg_binary="/usr/bin/ffmpeg",
            read_timeout_seconds=5.0,
            hardware_acceleration="auto",
        )

    def test_opencv_frame_source_can_disable_rtsp_hardware_acceleration(self):
        rtsp_source = FakeRtspFrameSource()

        with patch(
            "nvr_background.pipeline.opencv_frame_source.FfmpegRtspFrameSource",
            return_value=rtsp_source,
        ) as frame_source_class:
            frame_source = OpenCvFrameSource(
                "rtsp://camera/stream",
                hardware_acceleration=None,
            )
            frame = frame_source.read()

        self.assertEqual(40, int(frame[0, 0, 0]))
        frame_source_class.assert_called_once_with(
            "rtsp://camera/stream",
            ffmpeg_binary="ffmpeg",
            read_timeout_seconds=5.0,
            hardware_acceleration=None,
        )

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
                                        "filename": "custom_stage.py",
                                        "class": "CustomStage",
                                        "config": {},
                                    }
                                ],
                            }
                        ],
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
                "custom_stage.py",
                deployed_data["pipelines"][0]["stages"][0]["filename"],
            )
            self.assertEqual("deployed-pipeline", pipelines["pipelines"][0]["id"])
            self.assertEqual({}, state.sessions)

    def test_pipeline_config_save_rejects_stage_paths_outside_pipelines_dir(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config = self._config(temp_path)
            TestableDebugApiHandler.api_state = DebugApiState(config, FakeFrameSource)

            for filename in ("/tmp/custom_stage.py", "../custom_stage.py"):
                handler = TestableDebugApiHandler(
                    "/api/pipeline_config/pipelines",
                    method="POST",
                    body=json.dumps(
                        {
                            "enabled": True,
                            "frame_interval_seconds": 2,
                            "pipelines": [
                                {
                                    "id": "bad-pipeline",
                                    "enabled": True,
                                    "stages": [
                                        {
                                            "id": "custom",
                                            "enabled": True,
                                            "filename": filename,
                                            "class": "CustomStage",
                                            "config": {},
                                        }
                                    ],
                                }
                            ],
                        }
                    ).encode("utf-8"),
                )

                handler.do_POST()
                response = json.loads(handler.wfile.getvalue().decode("utf-8"))

                self.assertEqual(400, handler.status)
                self.assertIn("stage filename", response["error"])

    def test_stage_filename_resolves_relative_to_referencing_yaml_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config = self._config(temp_path)
            store = DebugApiState(config, FakeFrameSource).pipelines_store
            nested_yaml_path = (
                temp_path / "pipeline_config" / "pipelines" / "preprocessors" / "resize.yaml"
            )
            nested_yaml_path.parent.mkdir(parents=True, exist_ok=True)
            stage_path = temp_path / "pipeline_config" / "pipelines" / "resize_stage.py"
            stage_path.write_text("", encoding="utf-8")

            resolved_path = store._stage_path_under(
                "../resize_stage.py",
                nested_yaml_path,
                temp_path / "pipeline_config" / "pipelines",
            )

            self.assertEqual(stage_path.resolve(), resolved_path)

    def test_pipeline_stage_can_reference_child_yaml_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config = self._config(temp_path)
            store = DebugApiState(config, FakeFrameSource).pipelines_store
            pipelines_dir = temp_path / "pipeline_config" / "pipelines"
            child_yaml_path = pipelines_dir / "preprocessors" / "resize-pipeline.yaml"
            child_yaml_path.parent.mkdir(parents=True, exist_ok=True)
            stage_path = pipelines_dir / "resize_stage.py"
            stage_path.write_text(
                "from nvr_common.pipeline import PipelineStageResult\n"
                "\n"
                "class ResizeStage:\n"
                "    def __init__(self, config):\n"
                "        self.config = config\n"
                "\n"
                "    def process(self, context):\n"
                "        return PipelineStageResult(output_image=context.current_image)\n",
                encoding="utf-8",
            )
            store._write_yaml(
                store.pipelines_path,
                {
                    "enabled": True,
                    "frame_interval_seconds": 0.5,
                    "pipelines": [
                        {
                            "id": "resize-stage",
                            "enabled": True,
                            "stages": [
                                {
                                    "id": "resize-frame",
                                    "enabled": True,
                                    "pipeline": "preprocessors/resize-pipeline.yaml",
                                }
                            ],
                        }
                    ],
                },
            )
            store._write_yaml(
                child_yaml_path,
                {
                    "enabled": True,
                    "pipelines": [
                        {
                            "id": "resize-pipeline",
                            "enabled": True,
                            "stages": [
                                {
                                    "id": "resize-frame",
                                    "enabled": True,
                                    "filename": "../resize_stage.py",
                                    "class": "ResizeStage",
                                    "config": {},
                                }
                            ],
                        }
                    ],
                },
            )

            graph = store.pipeline_config_graph()

            self.assertEqual(
                ("resize-stage", "resize-pipeline"),
                graph.topological_pipeline_ids(),
            )
            self.assertEqual(
                str(stage_path.resolve()),
                graph.pipeline_by_id()["resize-pipeline"].stages[0].filename,
            )
            selected_response = store.pipeline_config_response(
                "preprocessors/resize-pipeline.yaml"
            )
            selected_session = DebugApiState(config, FakeFrameSource).load_camera_frame(
                "driveway", "preprocessors/resize-pipeline.yaml"
            )
            selected_records = selected_session.run()

            self.assertEqual(
                ["resize-pipeline"],
                [pipeline["id"] for pipeline in selected_response["pipelines"]],
            )
            self.assertEqual("resize-pipeline", selected_records[0].pipeline_id)
            self.assertEqual("resize-frame", selected_records[0].stage_id)

            deployed = store.deploy_pipeline_config_pipelines()
            deployed_root = yaml.safe_load(store.deployed_path.read_text())
            deployed_child_path = (
                temp_path
                / "pipeline_config"
                / "deployed"
                / "preprocessors"
                / "resize-pipeline.yaml"
            )
            deployed_child = yaml.safe_load(deployed_child_path.read_text())

            self.assertEqual(0.5, deployed["frame_interval_seconds"])
            self.assertEqual(
                "preprocessors/resize-pipeline.yaml",
                deployed_root["pipelines"][0]["stages"][0]["pipeline"],
            )
            self.assertEqual(
                "../resize_stage.py",
                deployed_child["pipelines"][0]["stages"][0]["filename"],
            )
            self.assertTrue((temp_path / "pipeline_config" / "deployed" / "resize_stage.py").is_file())

    def test_pipeline_config_save_can_update_selected_yaml_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config = self._config(temp_path)
            TestableDebugApiHandler.api_state = DebugApiState(config, FakeFrameSource)
            pipelines_dir = temp_path / "pipeline_config" / "pipelines"
            child_yaml_path = pipelines_dir / "preprocessors" / "mask-pipeline.yaml"
            child_yaml_path.parent.mkdir(parents=True, exist_ok=True)
            (pipelines_dir / "pipelines.yaml").write_text(
                "pipelines:\n- id: root\n  enabled: true\n  stages: []\n",
                encoding="utf-8",
            )
            child_yaml_path.write_text("pipelines: []\n", encoding="utf-8")

            handler = TestableDebugApiHandler(
                "/api/pipeline_config/pipelines",
                method="POST",
                body=json.dumps(
                    {
                        "pipeline_config_path": "preprocessors/mask-pipeline.yaml",
                        "pipelines_config": {
                            "enabled": True,
                            "frame_interval_seconds": 0.5,
                            "pipelines": [
                                {
                                    "id": "mask-pipeline",
                                    "enabled": True,
                                    "stages": [
                                        {
                                            "id": "polygon-mask",
                                            "enabled": True,
                                            "filename": "mask_stage.py",
                                            "class": "MaskStage",
                                            "config": {
                                                "polygons": [
                                                    [
                                                        {"x": 1, "y": 2},
                                                        {"x": 3, "y": 4},
                                                        {"x": 5, "y": 6},
                                                    ]
                                                ]
                                            },
                                        }
                                    ],
                                }
                            ],
                        },
                    }
                ).encode("utf-8"),
            )
            handler.do_POST()

            saved_child = yaml.safe_load(child_yaml_path.read_text(encoding="utf-8"))
            saved_root = yaml.safe_load(
                (pipelines_dir / "pipelines.yaml").read_text(encoding="utf-8")
            )

            self.assertEqual(200, handler.status)
            self.assertEqual(
                [[{"x": 1, "y": 2}, {"x": 3, "y": 4}, {"x": 5, "y": 6}]],
                saved_child["pipelines"][0]["stages"][0]["config"]["polygons"],
            )
            self.assertNotEqual(
                "mask-pipeline",
                saved_root["pipelines"][0]["id"],
            )

    def test_pipeline_config_response_includes_yaml_and_python_file_tree(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config = self._config(temp_path)
            store = DebugApiState(config, FakeFrameSource).pipelines_store
            pipelines_dir = temp_path / "pipeline_config" / "pipelines"
            nested_dir = pipelines_dir / "preprocessors"
            nested_dir.mkdir(parents=True, exist_ok=True)
            (pipelines_dir / "pipelines.yaml").write_text("pipelines: []\n", encoding="utf-8")
            (pipelines_dir / "resize_stage.py").write_text("", encoding="utf-8")
            (nested_dir / "resize.yaml").write_text("pipelines: []\n", encoding="utf-8")
            (nested_dir / "resize.py").write_text("", encoding="utf-8")
            (nested_dir / "notes.txt").write_text("", encoding="utf-8")

            response = store.pipeline_config_response()

            tree = response["pipeline_file_tree"]
            self.assertEqual("preprocessors", tree[0]["name"])
            self.assertEqual(
                ["resize.py", "resize.yaml"],
                [node["name"] for node in tree[0]["children"]],
            )
            self.assertIn("pipelines.yaml", [node["name"] for node in tree])
            self.assertIn("resize_stage.py", [node["name"] for node in tree])
            self.assertNotIn("notes.txt", [node["name"] for node in tree[0]["children"]])

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
                "example_resize_stage.py",
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


class EmptyFrameSource:
    def __init__(self, source):
        self.source = source

    def read(self):
        return np.array([], dtype=np.uint8)

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
        self.backend = None
        self.open_parameters = []

    def set(self, *_args):
        return True

    def open(self, _source, backend=None, open_parameters=None):
        self.opened = True
        self.backend = backend
        self.open_parameters = open_parameters or []
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


class FakeRtspFrameSource:
    def __init__(self):
        self.opened = False
        self.closed = False

    def open(self):
        self.opened = True

    def read(self):
        return np.full((2, 3, 3), 40, dtype=np.uint8)

    def close(self):
        self.closed = True


if __name__ == "__main__":
    unittest.main()
