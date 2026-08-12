"""Internal helpers shared across the hwinfo collectors.

Nothing here touches hardware; these are pure formatting/guard utilities so the
collector modules stay small and consistent.  Keeping them private (leading
underscore) makes the public surface exactly the collector functions.
"""

from __future__ import annotations

import functools


def human_bytes(num_bytes):
    """Human-readable byte size, e.g. ``1536`` -> ``"1.5 KB"``.

    Accepts ``None``/junk defensively (treated as 0) so it never raises while
    formatting best-effort hardware data.
    """
    try:
        size = float(num_bytes or 0)
    except (TypeError, ValueError):
        size = 0.0
    neg = size < 0
    size = abs(size)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if size < 1024.0 or unit == "PB":
            if unit == "B":
                text = f"{int(size)} {unit}"
            else:
                text = f"{size:.1f} {unit}"
            return ("-" + text) if neg else text
        size /= 1024.0
    return "0 B"


def human_hz(hz):
    """Format a frequency given in **MHz** (psutil's unit) as GHz/MHz text."""
    try:
        mhz = float(hz or 0)
    except (TypeError, ValueError):
        return "n/a"
    if mhz <= 0:
        return "n/a"
    if mhz >= 1000:
        return f"{mhz / 1000.0:.2f} GHz"
    return f"{mhz:.0f} MHz"


def human_duration(seconds):
    """Format a duration in seconds as ``"2d 3h 4m 5s"`` (largest 3 units)."""
    try:
        secs = int(max(0, seconds))
    except (TypeError, ValueError):
        return "n/a"
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    mins, sec = divmod(rem, 60)
    parts = []
    for value, label in ((days, "d"), (hours, "h"), (mins, "m"), (sec, "s")):
        if value or (parts and label != "s") or label == "s":
            parts.append(f"{value}{label}")
    # keep it compact: drop leading zero-days/zero-hours
    while len(parts) > 1 and parts[0].startswith("0"):
        parts.pop(0)
    return " ".join(parts[:3]) if parts else "0s"


def safe(default):
    """Decorator: run the wrapped collector, returning *default* on any error.

    Hardware probing routinely raises platform-specific quirks; a collector
    should degrade to an empty section rather than take down a whole report.
    Note this intentionally swallows everything EXCEPT that callers who want a
    hard failure raise :class:`~hwinfo.errors.HWInfoError` explicitly outside
    the decorated body.
    """

    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception:
                return default() if callable(default) else default

        return wrapper

    return deco
