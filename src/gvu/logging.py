"""Structured stderr logging shared by all viewers."""

import logging
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

LOG = logging.getLogger("gvu")


class TextFormatter(logging.Formatter):
    def __init__(self):
        super().__init__("%(timestamp)s [%(levelname)s] %(message)s %(metadata_text)s")

    def format(self, record):
        record.timestamp = datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds")
        fields = {
            "logger": record.name,
            "pid": record.process,
        }
        fields.update(getattr(record, "metadata", None) or {})

        def value_text(value):
            text = str(value)
            if isinstance(value, (str, Path)):
                return text if re.fullmatch(r"[\w./:+-]+", text) else repr(text)
            return repr(value)

        record.metadata_text = " ".join(
            f"{key}={value_text(value)}" for key, value in fields.items()
        )
        return super().format(record)


def configure_logging(log_level="INFO"):
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(TextFormatter())
    LOG.handlers[:] = [handler]
    LOG.setLevel(log_level)
    LOG.propagate = False
