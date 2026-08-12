"""Error types for hwinfo."""


class HWInfoError(Exception):
    """Raised for any recoverable failure in a hwinfo operation.

    All public functions raise this (and only this) on failure so callers --
    including the CLI and the GUI -- have a single exception to catch.  Probing
    real hardware is inherently best-effort, so most collectors degrade to
    empty/partial data instead of raising; ``HWInfoError`` is reserved for
    genuine failures (e.g. an unwritable export path or a bad request).
    """
