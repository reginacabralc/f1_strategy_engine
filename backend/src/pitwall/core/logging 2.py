"""Structured JSON logging via structlog.

Call :func:`configure_logging` once at process start (typically inside
:func:`pitwall.api.main.create_app`). After that, request a logger from
:func:`get_logger` anywhere; the configuration is process-wide.

Output format is line-delimited JSON suitable for shipping to anything
that understands ``stdout`` (Loki, CloudWatch, etc.).
"""

from __future__ import annotations

import logging
from typing import Any

import structlog

_LEVEL_TO_INT: dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def configure_logging(level: str = "INFO") -> None:
    """Configure ``logging`` and ``structlog`` to emit JSON to stdout.

    Idempotent: calling more than once is a no-op for the root handler.
    """
    int_level = _LEVEL_TO_INT.get(level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", level=int_level)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(int_level),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None, **initial_values: Any) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger, optionally bound to initial values.

    Usage::

        log = get_logger(__name__, component="engine")
        log.info("event_processed", driver="VER", lap=18)
    """
    return structlog.get_logger(name, **initial_values)
