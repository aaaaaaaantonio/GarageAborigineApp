import logging


class HealthCheckFilter(logging.Filter):
    """Drop uvicorn access-log lines for /health — the Docker healthcheck hits it every few seconds."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        return not (isinstance(args, tuple) and len(args) >= 3 and args[2] == "/health")


def install_access_log_filter() -> None:
    logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())
