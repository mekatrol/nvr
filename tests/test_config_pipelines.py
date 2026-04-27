import os
import tempfile
import unittest
from pathlib import Path

import yaml

from nvr_common.config import Config


class ConfigPipelineGraphTest(unittest.TestCase):
    def setUp(self):
        self.original_nvr_config = os.environ.get("NVR_CONFIG")
        self.original_rtsp_user = os.environ.get("RTSP_USER")
        self.original_rtsp_password = os.environ.get("RTSP_PASSWORD")
        os.environ["RTSP_USER"] = "user"
        os.environ["RTSP_PASSWORD"] = "password"
        self._reset_config_singleton()

    def tearDown(self):
        if self.original_nvr_config is None:
            os.environ.pop("NVR_CONFIG", None)
        else:
            os.environ["NVR_CONFIG"] = self.original_nvr_config

        if self.original_rtsp_user is None:
            os.environ.pop("RTSP_USER", None)
        else:
            os.environ["RTSP_USER"] = self.original_rtsp_user

        if self.original_rtsp_password is None:
            os.environ.pop("RTSP_PASSWORD", None)
        else:
            os.environ["RTSP_PASSWORD"] = self.original_rtsp_password

        self._reset_config_singleton()

    def test_parses_pipelines(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            self._write_config(config_path, self._base_config())
            os.environ["NVR_CONFIG"] = str(config_path)

            config = Config()
            graph = config.get_pipelines()

            self.assertIsNotNone(graph)
            self.assertEqual(
                ("preprocessing", "thumbnail"), graph.topological_pipeline_ids()
            )
            self.assertEqual(1.5, config.get_pipeline_frame_interval_seconds())

            preprocessing = graph.pipeline_by_id()["preprocessing"]
            stage = preprocessing.stages[0]
            self.assertEqual("clip", stage.id)
            self.assertEqual("tests.pipeline.append_stage", stage.module)
            self.assertEqual("AppendStage", stage.class_name)
            self.assertEqual({"suffix": "-base"}, stage.config)

    def test_parses_separate_pipeline_conf(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            pipeline_conf_path = Path(temp_dir) / "pipeline_conf.yaml"
            config_data = self._base_config()
            config_data.pop("pipelines")
            self._write_config(config_path, config_data)
            self._write_config(
                pipeline_conf_path,
                {
                    "pipelines": {
                        "pipeline": [
                            {
                                "id": "preprocessing",
                                "name": "Image preprocessing",
                                "stages": [
                                    {
                                        "id": "clip",
                                        "enabled": True,
                                        "filename": "tests/pipeline/append_stage.py",
                                        "class": "AppendStage",
                                        "config": {"suffix": "-base"},
                                    },
                                    {
                                        "id": "thumbnail",
                                        "enabled": True,
                                        "pipeline": "thumbnail",
                                    },
                                ],
                            },
                            {
                                "id": "thumbnail",
                                "name": "Thumbnail generation",
                                "stages": [],
                            },
                        ]
                    }
                },
            )
            os.environ["NVR_CONFIG"] = str(config_path)

            config = Config()
            graph = config.get_pipelines()

            self.assertEqual(
                ("preprocessing", "thumbnail"), graph.topological_pipeline_ids()
            )
            preprocessing = graph.pipeline_by_id()["preprocessing"]
            self.assertEqual("Image preprocessing", preprocessing.name)
            self.assertEqual(
                "tests/pipeline/append_stage.py", preprocessing.stages[0].filename
            )
            self.assertEqual("thumbnail", preprocessing.stages[1].pipeline)

    def test_rejects_circular_pipeline_references(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            pipeline_conf_path = Path(temp_dir) / "pipeline_conf.yaml"
            config_data = self._base_config()
            config_data.pop("pipelines")
            self._write_config(config_path, config_data)
            self._write_config(
                pipeline_conf_path,
                {
                    "pipelines": {
                        "pipeline": [
                            {
                                "id": "a",
                                "stages": [
                                    {"id": "call-b", "enabled": True, "pipeline": "b"}
                                ],
                            },
                            {
                                "id": "b",
                                "stages": [
                                    {"id": "call-a", "enabled": True, "pipeline": "a"}
                                ],
                            },
                        ]
                    }
                },
            )
            os.environ["NVR_CONFIG"] = str(config_path)

            with self.assertRaisesRegex(ValueError, "cycle detected"):
                Config()

    def test_camera_pipelines_overrides_global_stages_by_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_data = self._base_config()
            config_data["cameras"][0]["pipelines"] = {
                "frame_interval_seconds": 3,
                "pipelines": [
                    {
                        "id": "preprocessing",
                        "enabled": True,
                        "stages": [
                            {
                                "id": "clip",
                                "enabled": False,
                                "module": "tests.pipeline.append_stage",
                                "class": "AppendStage",
                                "config": {"suffix": "-camera"},
                            }
                        ],
                    }
                ],
            }
            config_path = Path(temp_dir) / "config.yaml"
            self._write_config(config_path, config_data)
            os.environ["NVR_CONFIG"] = str(config_path)

            config = Config()
            graph = config.get_pipelines("driveway")

            self.assertEqual(
                3.0, config.get_pipeline_frame_interval_seconds("driveway")
            )
            stage = graph.pipeline_by_id()["preprocessing"].stages[0]
            self.assertFalse(stage.enabled)
            self.assertEqual({"suffix": "-camera"}, stage.config)

    def test_debug_config_overlays_pipelines(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            debug_path = Path(temp_dir) / "config.debug.yaml"
            self._write_config(config_path, self._base_config())
            self._write_config(
                debug_path,
                {
                    "pipelines": {
                        "pipelines": [
                            {
                                "id": "preprocessing",
                                "enabled": True,
                                "stages": [
                                    {
                                        "id": "clip",
                                        "enabled": True,
                                        "module": "tests.pipeline.append_stage",
                                        "class": "AppendStage",
                                        "config": {"suffix": "-debug"},
                                    }
                                ],
                            }
                        ]
                    }
                },
            )
            os.environ["NVR_CONFIG"] = str(config_path)

            config = Config()
            stage = config.get_pipelines().pipeline_by_id()["preprocessing"].stages[0]

            self.assertEqual({"suffix": "-debug"}, stage.config)

    def test_rejects_invalid_pipelines_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_data = self._base_config()
            config_data["pipelines"]["pipelines"][0]["stages"][0]["config"] = "invalid"
            config_path = Path(temp_dir) / "config.yaml"
            self._write_config(config_path, config_data)
            os.environ["NVR_CONFIG"] = str(config_path)

            with self.assertRaisesRegex(
                ValueError, "stage 'clip' config must be a mapping"
            ):
                Config()

    @staticmethod
    def _reset_config_singleton():
        if hasattr(Config, "_instance"):
            delattr(Config, "_instance")

    @staticmethod
    def _write_config(path, data):
        path.write_text(yaml.safe_dump(data), encoding="utf-8")

    @staticmethod
    def _base_config():
        return {
            "log_path": "../../nvr/logs",
            "ffmpeg_binary": "ffmpeg",
            "stream": {
                "segment_seconds": 300,
                "output_path": "../../nvr/streams",
                "retention_days": 0.1,
                "backup_retention_days": 5,
                "backup_output_path": "../../nvr/streams/backup",
            },
            "pipelines": {
                "enabled": True,
                "frame_interval_seconds": 1.5,
                "pipelines": [
                    {
                        "id": "preprocessing",
                        "enabled": True,
                        "stages": [
                            {
                                "id": "clip",
                                "enabled": True,
                                "module": "tests.pipeline.append_stage",
                                "class": "AppendStage",
                                "config": {"suffix": "-base"},
                            }
                        ],
                    },
                    {"id": "thumbnail", "enabled": True, "stages": []},
                ],
            },
            "cameras": [
                {
                    "id": "driveway",
                    "name": "driveway",
                    "enabled": True,
                    "log_ffmpeg": False,
                    "rtsp_url": "rtsp://{RTSP_USER}:{RTSP_PASSWORD}@camera/stream",
                }
            ],
        }


if __name__ == "__main__":
    unittest.main()
