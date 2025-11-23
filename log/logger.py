"""
Central application logger using Python's standard logging module.

- Logs to <Config()["log_path"]>/nvr.log
- Also logs to stderr (console) by default
- RTSP credentials are scrubbed from all log messages
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from log.rtsp_sanitizing_filter import RtspSanitizingFilter
from utils.config import Config
from utils.singleton import Singleton


class Logger(Singleton):
    """
    Singleton wrapper around a configured logging.Logger instance.

    Usage:
        from utils.logger import Logger

        log = Logger().logger
        log.info("Application started")

        # Or via convenience methods:
        Logger().info("Something happened: %s", value)
    """

    _initialized: bool
    _logger: logging.Logger
    log_dir: Path
    log_file_path: Path

    def __init__(self) -> None:
        # Protect against reinitialization in a singleton.
        if getattr(self, "_initialized", False):
            return

        conf = Config()
        log_path_value = conf["log_path"]

        # Ensure we have a Path object for the log directory
        self.log_dir = Path(log_path_value)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Main log file
        self.log_file_path = self.log_dir / "nvr.log"

        # Create or retrieve a named logger for the application.
        # Using a named logger avoids accidentally modifying the root logger.
        self._logger = logging.getLogger("nvr")

        # Set a default log level; adjust as needed or make configurable.
        self._logger.setLevel(logging.INFO)

        # Avoid adding handlers multiple times if __init__ somehow runs again.
        if not self._logger.handlers:
            self._configure_handlers()

        # Prevent records from propagating to the root logger if you don't want
        # duplicate output (e.g. if root logger also has handlers).
        self._logger.propagate = False

        self._initialized = True

    def _configure_handlers(self) -> None:
        """
        Configure file and console handlers, formatter, and filters.
        """

        # Common formatter with timestamp and level
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # File handler
        file_handler = logging.FileHandler(
            filename=self.log_file_path,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)

        # Console handler (stderr by default)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        # RTSP sanitizing filter for both handlers
        sanitizing_filter = RtspSanitizingFilter()
        file_handler.addFilter(sanitizing_filter)
        console_handler.addFilter(sanitizing_filter)

        self._logger.addHandler(file_handler)
        self._logger.addHandler(console_handler)

    @property
    def logger(self) -> logging.Logger:
        """
        Access the underlying logging.Logger instance.
        """
        return self._logger

    # Convenience methods so callers can use Logger() directly
    # instead of Logger().logger.<level>(...).

    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._logger.debug(msg, *args, **kwargs)

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._logger.info(msg, *args, **kwargs)

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._logger.warning(msg, *args, **kwargs)

    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._logger.error(msg, *args, **kwargs)

    def exception(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """
        Convenience wrapper for logging exceptions with stack traces.
        Equivalent to logger.error(..., exc_info=True) but with a dedicated name.
        """
        self._logger.exception(msg, *args, **kwargs)

    def critical(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._logger.critical(msg, *args, **kwargs)
