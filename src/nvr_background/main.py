import signal
import threading
import time
from pathlib import Path

from nvr_background.pipeline.camera_pipeline_worker import CameraPipelineWorker
from nvr_background.recorder.camera_recorder import CameraRecorder
from nvr_background.recorder.retention_manager import RetentionManager
from nvr_common.config import Config
from nvr_common.logging.logger import Logger


def main() -> None:
    # Create config
    conf = None
    try:
        conf = Config()
    except Exception as ex:
        print(ex)
        return

    # Create logger
    logger = Logger().logger

    # Log config
    conf.log_config(logger)

    # Make sure output paths exist
    stream_output_path = Path(conf.stream_output_path)
    stream_output_path.mkdir(parents=True, exist_ok=True)

    stream_backup_output_path = Path(conf.stream_backup_output_path)
    stream_backup_output_path.mkdir(parents=True, exist_ok=True)

    # Main application log file
    logger.info(f"NVR starting with config: {conf.config_path}")

    cameras = conf.get("cameras") or []
    recorders = []
    pipeline_workers = []

    # Start one CameraRecorder thread per enabled camera
    for camera in cameras:
        # Create a recorder
        rec = CameraRecorder(camera["id"])

        # Start it
        rec.start()

        # Add to recorders
        recorders.append(rec)

        if camera.get(Config.KEY_CAMERA_ENABLED, False) and conf.get_pipeline_graph(
            camera["id"]
        ):
            pipeline_worker = CameraPipelineWorker(camera["id"], logger=logger)
            pipeline_worker.start()
            pipeline_workers.append(pipeline_worker)

    # Start retention manager
    retention_manager = RetentionManager()
    retention_manager.start()

    # Handle signals for clean shutdown
    stop_event = threading.Event()

    def handle_signal(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        stop_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # Wait for stop
    while not stop_event.is_set():
        time.sleep(1)

    logger.info("Stopping recorders and retention manager...")
    retention_manager.stop()
    for rec in recorders:
        rec.stop()
    for pipeline_worker in pipeline_workers:
        pipeline_worker.stop()

    retention_manager.join()
    for rec in recorders:
        rec.join()
    for pipeline_worker in pipeline_workers:
        pipeline_worker.join()

    logger.info("All stopped")
