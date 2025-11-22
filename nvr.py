import os
import signal
import threading
import time
from pathlib import Path

from logging.logger import Logger
from recorder.camera_recorder import CameraRecorder
from recorder.retention_manager import RetentionManager
from utils.config import load_config, merge_dicts


def main() -> None:
    # Create logger singleton instance
    logger = Logger()

    # Base config (usually config.yaml, or whatever NVR_CONFIG points to)
    config_path = os.environ.get("NVR_CONFIG", "config.yaml")
    conf = load_config(config_path)

    # Local-only overrides: config.debug.yaml in the same directory as config.yaml
    base_path = Path(config_path)
    debug_config_path = base_path.with_name("config.debug.yaml")

    # If there there is a debug conf then merge configured values
    if debug_config_path.exists():
        debug_conf = load_config(str(debug_config_path))
        if debug_conf:
            conf = merge_dicts(conf, debug_conf)

    # Now initialise from configuration settings
    logger.init_from_config(conf)

    storage_root = Path(conf["storage_root"])
    storage_root.mkdir(parents=True, exist_ok=True)

    # Main application log file
    logger.log(f"NVR starting with config: {config_path}")

    cameras = conf.get("cameras", [])
    recorders = []

    # Start one CameraRecorder thread per enabled camera
    for cam in cameras:
        if not cam.get("enabled", True):
            logger.log(f"Camera disabled, skipping: {cam.get('name', cam.get('id'))}")
            continue
        rec = CameraRecorder(cam, conf)
        rec.start()
        recorders.append(rec)
        logger.log(f"Started recorder for camera: {cam['name']}")

    # Start retention manager
    retention_manager = RetentionManager(conf)
    retention_manager.start()
    logger.log("Retention manager started")

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
