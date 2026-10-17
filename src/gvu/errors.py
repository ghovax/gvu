"""Errors exposed by the GaussView automation API."""


class ActionUnavailable(RuntimeError):
    """The installed viewer cannot perform or verify the requested action."""


class UnsupportedFormat(ValueError):
    """A file format is not supported by the installed GaussView backend."""
