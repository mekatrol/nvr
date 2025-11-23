import threading
import time
import shutil
from pathlib import Path
from datetime import datetime, timedelta

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
        backup_retention_days = self.conf.stream_backup_retention_days
        stream_output_path = Path(self.conf.stream_output_path)
        backup_path = Path(self.conf.stream_backup_output_path)
        check_interval_seconds = 600  # every 10 minutes

        self.logger.log("Retention manager started")

        while not self.stop_event.is_set():
            now = datetime.now()

            # Cutoff to move from primary to backup
            move_delta = timedelta(days=retention_days)
            move_cutoff = now - move_delta

            # Cutoff to delete from backup:
            #   max lifetime = retention_days in primary + backup_retention_days in backup
            delete_cutoff = now - timedelta(days=retention_days + backup_retention_days)

            # 1) Move old files from stream_output_path -> backup_path
            for cam_dir in stream_output_path.glob("*"):
                if not cam_dir.is_dir():
                    continue

                backup_cam_dir = backup_path / cam_dir.name
                backup_cam_dir.mkdir(parents=True, exist_ok=True)

                for file in cam_dir.glob("*.mp4"):
                    try:
                        mtime = datetime.fromtimestamp(file.stat().st_mtime)
                        if mtime < move_cutoff:
                            dest = backup_cam_dir / file.name

                            # shutil.move handles cross-filesystem moves
                            shutil.move(str(file), str(dest))

                            self.logger.log(
                                f"[Retention] Moved old file to backup: {dest}"
                            )
                    except FileNotFoundError as e:
                        # File may be gone already
                        self.logger.log(
                            f"[Retention] Failed to move {file} to backup: {e}, FileNotFoundError"
                        )
                    except OSError as e:
                        # Log other I/O problems (permissions, network issues, etc.)
                        self.logger.log(
                            f"[Retention] Failed to move {file} to backup: {e}"
                        )

            # 2) Delete very old files from backup_path
            for cam_dir in backup_path.glob("*"):
                if not cam_dir.is_dir():
                    continue

                for file in cam_dir.glob("*.mp4"):
                    try:
                        mtime = datetime.fromtimestamp(file.stat().st_mtime)
                        # Delete only once the file is older than
                        # retention_days + backup_retention_days
                        if mtime < delete_cutoff:
                            file.unlink()
                            self.logger.log(
                                f"[Retention] Deleted expired backup file: {file}"
                            )
                    except FileNotFoundError:
                        # File may be gone already
                        pass

            # Sleep loop, but allow timely stop
            for _ in range(check_interval_seconds):
                if self.stop_event.is_set():
                    break
                time.sleep(1)
