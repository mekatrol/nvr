from datetime import datetime
from pathlib import Path
import re
import threading
from utils.config import Config
from utils.singleton import Singleton


class Logger(Singleton):
    def __init__(self):
        # __init__ may run multiple times in a naive singleton,
        # so protect against reinitializing.
        if hasattr(self, "_initialized") and self._initialized:
            return

        conf = Config()
        self.log_dir = Path(conf["log_path"])
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file_path = self.log_dir / "nvr.log"
        self.log_lock = threading.Lock()
        self._initialized = True

    def log(self, msg: str) -> None:
        """
        Write a timestamped log line to the main application log file.
        Falls back to stdout if LOG_FILE_PATH is not set yet.
        RTSP credentials are scrubbed before writing.
        """

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        safe_msg = self._sanitize_rtsp_url(str(msg))
        line = f"[{ts}] {safe_msg}\n"

        if self.log_file_path is None:
            # Early logging before main() sets it
            print(line, end="", flush=True)
            return

        with self.log_lock:
            with open(self.log_file_path, "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()

    def _sanitize_rtsp_url(self, text: str) -> str:
        """
        Replace credentials inside any RTSP URL in the given text with
        $RTSP_USER and $RTSP_PASSWORD.
        Example:
        rtsp://admin:Pass123@host/path
        -> rtsp://$RTSP_USER:$RTSP_PASSWORD@host/path
        """
        return re.sub(
            r"rtsp://([^:@]+):([^@]+)@",
            r"rtsp://$RTSP_USER:$RTSP_PASSWORD@",
            text,
        )
