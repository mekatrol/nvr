import re
import logging
from typing import Final

# Shared pattern + helper for sanitizing RTSP URLs
_RTSP_CRED_PATTERN: Final[re.Pattern[str]] = re.compile(r"rtsp://([^:@]+):([^@]+)@")


def sanitize_rtsp_url(text: str) -> str:
    """
    Replace credentials inside any RTSP URL in the given text with
    $RTSP_USER and $RTSP_PASSWORD.

    Example:
        rtsp://admin:Pass123@host/path
        -> rtsp://$RTSP_USER:$RTSP_PASSWORD@host/path
    """
    return _RTSP_CRED_PATTERN.sub(
        "rtsp://$RTSP_USER:$RTSP_PASSWORD@",
        text,
    )


class RtspSanitizingFilter(logging.Filter):
    """
    Logging filter that sanitizes RTSP URLs in log messages.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # Get fully formatted message (msg + args) as a string
        msg = record.getMessage()
        sanitized = sanitize_rtsp_url(msg)

        # Rewrite record so handlers see sanitized text
        record.msg = sanitized
        record.args = ()

        return True
