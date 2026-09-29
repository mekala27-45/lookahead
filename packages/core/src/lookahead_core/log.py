"""Structured JSON logging. No raw meter row is ever logged; ids and origins only.

Keys that could carry a household or demand row are dropped before the event is written,
and any value longer than a stated length is truncated, so a frame printed by
mistake never reaches a log line.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog

FORBIDDEN_KEYS = frozenset({"row", "rows", "household", "households", "frame", "record", "records"})
MAX_VALUE_LENGTH = 200


def redact(_: Any, __: str, event: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    for key in list(event):
        if key in FORBIDDEN_KEYS:
            event.pop(key)
        elif isinstance(event[key], str) and len(event[key]) > MAX_VALUE_LENGTH:
            event[key] = event[key][:MAX_VALUE_LENGTH] + "[truncated]"
    return event


def configure(level: int = logging.INFO) -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact,
            structlog.processors.JSONRenderer(sort_keys=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str) -> Any:
    return structlog.get_logger(name)
