from datetime import datetime, timedelta
from pathlib import Path
import threading
import time

from logging.logger import Logger


class RetentionCleaner(threading.Thread):
    def __init__(self, global_conf):
        super().__init__(daemon=True)
        self.global_conf = global_conf
        self.stop_event = threading.Event()
        self.logger = Logger()

    def stop(self):
        self.stop_event.set()

    def run(self):
        retention_days = int(self.global_conf.get("retention_days", 7))
        storage_root = Path(self.global_conf["storage_root"])
        check_interval_seconds = 600  # every 10 minutes

        while not self.stop_event.is_set():
            cutoff = datetime.now() - timedelta(days=retention_days)
            for cam_dir in storage_root.glob("*"):
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
