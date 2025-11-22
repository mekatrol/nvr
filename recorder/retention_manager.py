from datetime import datetime, timedelta
from pathlib import Path
import threading
import time

from logging.logger import Logger
from utils.config import Config


class RetentionManager(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.conf = Config()
        self.stop_event = threading.Event()
        self.logger = Logger()

    def stop(self) -> None:
        self.stop_event.set()

    def run(self) -> None:
        retention_days = self.conf.stream_retention_days
        stream_output_path = Path(self.conf.stream_output_path)
        check_interval_seconds = 600  # every 10 minutes

        self.logger.log("Retention manager started")

        while not self.stop_event.is_set():
            cutoff = datetime.now() - timedelta(days=retention_days)
            for cam_dir in stream_output_path.glob("*"):
                if not cam_dir.is_dir():
                    continue
                for file in cam_dir.glob("*.mp4"):
                    try:
                        mtime = datetime.fromtimestamp(file.stat().st_mtime)
                        if mtime < cutoff:
                            file.unlink()
                            self.logger.log(f"[Retention] Deleted old file: {file}")
                    except FileNotFoundError:
                        # File may be gone already
                        pass
            for _ in range(check_interval_seconds):
                if self.stop_event.is_set():
                    break
                time.sleep(1)
