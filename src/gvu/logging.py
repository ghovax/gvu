"""Structured stderr logging shared by all viewers."""

import json
import logging
import sys
from datetime import UTC, datetime

LOG = logging.getLogger("gvu")


class JsonLineFormatter(logging.Formatter):
    def format(self, record):
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "pid": record.process,
            "event": record.getMessage(),
        }
        if metadata := getattr(record, "metadata", None):
            entry["metadata"] = metadata
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


def configure_logging(log_level="INFO"):
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonLineFormatter())
    LOG.handlers[:] = [handler]
    LOG.setLevel(log_level)
    LOG.propagate = False
