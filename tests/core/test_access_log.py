import logging

from app.core.logging import HealthCheckFilter


def _record(path: str) -> logging.LogRecord:
    # Shape of uvicorn.access records: args = (client, method, path, http_version, status)
    return logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 0,
        '%s - "%s %s HTTP/%s" %d', ("127.0.0.1:1", "GET", path, "1.1", 200), None,
    )


def test_filter_drops_health_requests():
    assert HealthCheckFilter().filter(_record("/health")) is False


def test_filter_keeps_other_requests():
    assert HealthCheckFilter().filter(_record("/clients")) is True
    assert HealthCheckFilter().filter(_record("/health-report")) is True


def test_filter_is_installed_on_uvicorn_access_logger():
    import app.main  # noqa: F401  — installing the filter is an import side effect

    filters = logging.getLogger("uvicorn.access").filters
    assert any(isinstance(f, HealthCheckFilter) for f in filters)


def test_redact_filter_hides_download_token_but_keeps_line():
    from app.core.logging import TokenRedactFilter

    doc = "6f1c2b1e-0000-4000-8000-000000000001"
    record = _record(f"/documents/{doc}/download?token=abc.def.ghi")
    assert TokenRedactFilter().filter(record) is True
    assert record.getMessage() == f'127.0.0.1:1 - "GET /documents/{doc}/download?token=*** HTTP/1.1" 200'


def test_redact_filter_leaves_other_paths_untouched():
    from app.core.logging import TokenRedactFilter

    for path in ("/clients?token=abc", "/documents/x/file", "/health"):
        record = _record(path)
        assert TokenRedactFilter().filter(record) is True
        assert record.args[2] == path


def test_redact_filter_is_installed_on_uvicorn_access_logger():
    import app.main  # noqa: F401
    from app.core.logging import TokenRedactFilter

    assert any(isinstance(f, TokenRedactFilter) for f in logging.getLogger("uvicorn.access").filters)
