import os
import re
import signal
import subprocess
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import yaml

# Global log file path (set in main())
LOG_FILE_PATH = None
LOG_LOCK = threading.Lock()


def expand_env_in_url(url: str) -> str:
    return url.format(
        RTSP_USER=os.environ.get("RTSP_USER", ""),
        RTSP_PASSWORD=os.environ.get("RTSP_PASSWORD", ""),
    )


def merge_dicts(base: dict, overrides: dict) -> dict:
    """
    Recursively merge `overrides` into `base`.

    - If a key exists in both and both values are dicts, merge them.
    - Otherwise, the value from `overrides` replaces the one in `base`.
    """
    if not isinstance(base, dict):
        base = {}
    if not isinstance(overrides, dict):
        return base

    for key, override_value in overrides.items():
        if (
            key in base
            and isinstance(base[key], dict)
            and isinstance(override_value, dict)
        ):
            merge_dicts(base[key], override_value)
        else:
            base[key] = override_value
    return base


def load_config(path: str):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def sanitize_rtsp_url(text: str) -> str:
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


def log(msg: str):
    """
    Write a timestamped log line to the main application log file.
    Falls back to stdout if LOG_FILE_PATH is not set yet.
    RTSP credentials are scrubbed before writing.
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    safe_msg = sanitize_rtsp_url(str(msg))
    line = f"[{ts}] {safe_msg}\n"

    global LOG_FILE_PATH
    if LOG_FILE_PATH is None:
        # Early logging before main() sets it
        print(line, end="", flush=True)
        return

    with LOG_LOCK:
        with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()


class CameraRecorder(threading.Thread):
    def __init__(self, cam_conf, global_conf):
        super().__init__(daemon=True)
        self.cam_conf = cam_conf
        self.global_conf = global_conf
        self.stop_event = threading.Event()
        self.proc = None

        # Per-camera ffmpeg log file
        self.log_dir = Path(self.global_conf.get("log_path", "./logs"))
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.ffmpeg_log_path = self.log_dir / f"{self.cam_conf['name']}.ffmpeg.log"

    def build_ffmpeg_command(self):
        storage_root = Path(self.global_conf["storage_root"])
        cam_name = self.cam_conf["name"]
        segment_seconds = int(self.global_conf.get("segment_seconds", 300))
        ffmpeg_bin = self.global_conf.get("ffmpeg_binary", "ffmpeg")

        out_dir = storage_root / cam_name
        out_dir.mkdir(parents=True, exist_ok=True)

        # e.g. 20251122_203000_300s.mp4
        out_pattern = str(out_dir / f"%Y%m%d_%H%M%S_{segment_seconds}s.mp4")

        rtsp_url = expand_env_in_url(self.cam_conf["rtsp_url"])

        cmd = [
            ffmpeg_bin,
            "-rtsp_transport",
            "tcp",
            "-i",
            rtsp_url,
            "-an",
            "-c",
            "copy",
            "-f",
            "segment",
            "-segment_time",
            str(segment_seconds),
            "-reset_timestamps",
            "1",
            "-strftime",
            "1",
            out_pattern,
        ]
        return cmd, rtsp_url

    def stop(self):
        self.stop_event.set()
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass

    def run(self):
        cam_name = self.cam_conf["name"]

        while not self.stop_event.is_set():
            cmd, rtsp_url = self.build_ffmpeg_command()

            # Validate RTSP URL after env expansion
            if (
                not rtsp_url
                or "{RTSP_USER}" in rtsp_url
                or "{RTSP_PASSWORD}" in rtsp_url
            ):
                log(f"[{cam_name}] Invalid RTSP URL after env expansion: {rtsp_url!r}")
                time.sleep(10)
                continue

            try:
                # Build a sanitised command string for logging
                safe_cmd = []
                for part in cmd:
                    if isinstance(part, str) and part.startswith("rtsp://"):
                        safe_cmd.append(sanitize_rtsp_url(part))
                    else:
                        safe_cmd.append(str(part))

                log(f"[{cam_name}] Starting ffmpeg: {' '.join(safe_cmd)}")

                # Start ffmpeg, capturing its stdout+stderr
                self.proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )

                # Stream ffmpeg output to per-camera log, sanitising credentials
                assert self.proc.stdout is not None
                with open(
                    self.ffmpeg_log_path, "a", buffering=1, encoding="utf-8"
                ) as log_file:
                    for line in self.proc.stdout:
                        if line is None:
                            break
                        safe_line = sanitize_rtsp_url(line.rstrip("\n"))
                        log_file.write(safe_line + "\n")

                        if self.stop_event.is_set():
                            break

                # Wait for process to exit (in case stdout loop ended early)
                ret = self.proc.wait()
                log(f"[{cam_name}] ffmpeg exited with code {ret}")

            except Exception as e:
                log(f"[{cam_name}] Error starting ffmpeg: {repr(e)}")

            if self.stop_event.is_set():
                break

            log(f"[{cam_name}] Restarting ffmpeg in 5s...")
            time.sleep(5)


class RetentionCleaner(threading.Thread):
    def __init__(self, global_conf):
        super().__init__(daemon=True)
        self.global_conf = global_conf
        self.stop_event = threading.Event()

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
                            log(f"[Retention] Deleted old file: {file}")
                    except FileNotFoundError:
                        # File may be gone already
                        pass
            for _ in range(check_interval_seconds):
                if self.stop_event.is_set():
                    break
                time.sleep(1)


def main():
    global LOG_FILE_PATH

    # Base config (usually config.yaml, or whatever NVR_CONFIG points to)
    config_path = os.environ.get("NVR_CONFIG", "config.yaml")
    conf = load_config(config_path)

    # Local-only overrides: config.debug.yaml in the same directory as config.yaml
    base_path = Path(config_path)
    debug_config_path = base_path.with_name("config.debug.yaml")

    if debug_config_path.exists():
        debug_conf = load_config(str(debug_config_path))
        if debug_conf:
            conf = merge_dicts(conf, debug_conf)
            # This will log to stdout initially because LOG_FILE_PATH is not set yet.
            log(f"Applying local overrides from {debug_config_path}")

    storage_root = Path(conf["storage_root"])
    storage_root.mkdir(parents=True, exist_ok=True)

    log_dir = Path(conf["log_path"])
    log_dir.mkdir(parents=True, exist_ok=True)

    # Main application log file
    LOG_FILE_PATH = log_dir / "nvr.log"
    log(f"NVR starting with config: {config_path}")

    cameras = conf.get("cameras", [])
    recorders = []

    # Start one CameraRecorder thread per enabled camera
    for cam in cameras:
        if not cam.get("enabled", True):
            log(f"Camera disabled, skipping: {cam.get('name', cam.get('id'))}")
            continue
        rec = CameraRecorder(cam, conf)
        rec.start()
        recorders.append(rec)
        log(f"Started recorder for camera: {cam['name']}")

    # Start retention cleaner
    cleaner = RetentionCleaner(conf)
    cleaner.start()
    log("Retention cleaner started")

    # Handle signals for clean shutdown
    stop_event = threading.Event()

    def handle_signal(signum, frame):
        log(f"Received signal {signum}, shutting down...")
        stop_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # Wait for stop
    while not stop_event.is_set():
        time.sleep(1)

    log("Stopping recorders...")
    cleaner.stop()
    for rec in recorders:
        rec.stop()

    cleaner.join()
    for rec in recorders:
        rec.join()

    log("All recorders stopped")


if __name__ == "__main__":
    main()
