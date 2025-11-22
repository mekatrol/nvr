import signal
import threading
import time
from pathlib import Path

from logging.logger import Logger
from recorder.camera_recorder import CameraRecorder
from recorder.retention_manager import RetentionManager
from utils.config import Config


def main() -> None:
    # Create config
    conf = None
    try:
        conf = Config()
    except Exception as ex:
        print(ex)
        return

    # Create logger
    logger = Logger()

    stream_output_path = Path(conf.stream_output_path)
    stream_output_path.mkdir(parents=True, exist_ok=True)

    # Main application log file
    logger.log(f"NVR starting with config: {conf.config_path}")

    cameras = conf.get("cameras") or []
    recorders = []

    # Start one CameraRecorder thread per enabled camera
    for camera in cameras:
        # Create a recorder
        rec = CameraRecorder(camera["id"])

        # Start it
        rec.start()

        # Add to recorders
        recorders.append(rec)

    # Start retention manager
    retention_manager = RetentionManager()
    retention_manager.start()

    # Handle signals for clean shutdown
    stop_event = threading.Event()

    def handle_signal(signum, frame):
        logger.log(f"Received signal {signum}, shutting down...")
        stop_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # Wait for stop
    while not stop_event.is_set():
        time.sleep(1)

    logger.log("Stopping recorders and retention manager...")
    retention_manager.stop()
    for rec in recorders:
        rec.stop()

    retention_manager.join()
    for rec in recorders:
        rec.join()

    logger.log("All stopped")


if __name__ == "__main__":
    main()
