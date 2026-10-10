import logging
import re


class HealthCheckFilter(logging.Filter):
    """Drop uvicorn access-log lines for /health — the Docker healthcheck hits it every few seconds."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        return not (isinstance(args, tuple) and len(args) >= 3 and args[2] == "/health")


_DOWNLOAD_TOKEN = re.compile(r"^(/documents/[^/?]+/download\?(?:[^#]*&)?token=)[^&#]*")


class TokenRedactFilter(logging.Filter):
    """Replace the signed token of PDF download links with *** in access-log lines (the line is kept)."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
            redacted = _DOWNLOAD_TOKEN.sub(r"\g<1>***", args[2])
            if redacted != args[2]:
                record.args = (*args[:2], redacted, *args[3:])
        return True


def install_access_log_filter() -> None:
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.addFilter(HealthCheckFilter())
    access_logger.addFilter(TokenRedactFilter())
