"""System overview: OS, host, boot time/uptime, Python & architecture.

Everything returned by :func:`overview` is a plain JSON-serializable dict.
"""

from __future__ import annotations

import platform
import socket
import sys
import time

from ._common import human_duration


def overview():
    """Return a high-level system summary as a JSON-serializable dict.

    Keys: ``hostname``, ``os`` (system/release/version/edition), ``machine``,
    ``architecture``, ``processor``, ``python``, ``boot_time`` (epoch seconds),
    ``uptime_seconds``/``uptime`` and a one-line ``summary``.  Values that can't
    be determined fall back to empty strings / ``None`` rather than raising.
    """
    uname = platform.uname()
    hostname = ""
    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = uname.node or ""

    boot_time = None
    uptime_seconds = None
    try:
        import psutil

        boot_time = float(psutil.boot_time())
        uptime_seconds = max(0, int(time.time() - boot_time))
    except Exception:
        boot_time = None
        uptime_seconds = None

    bits, _linkage = platform.architecture()

    os_section = {
        "system": uname.system or platform.system() or "",
        "release": uname.release or "",
        "version": uname.version or "",
        "platform": _platform_string(),
    }

    data = {
        "hostname": hostname,
        "os": os_section,
        "machine": uname.machine or platform.machine() or "",
        "architecture": bits or "",
        "processor": uname.processor or platform.processor() or "",
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "compiler": platform.python_compiler(),
            "executable": sys.executable or "",
        },
        "boot_time": boot_time,
        "uptime_seconds": uptime_seconds,
        "uptime": human_duration(uptime_seconds) if uptime_seconds is not None else "n/a",
    }
    data["summary"] = _summary(data)
    return data


def _platform_string():
    try:
        return platform.platform()
    except Exception:
        return ""


def _summary(data):
    os_ = data["os"]
    name = " ".join(x for x in (os_["system"], os_["release"]) if x).strip()
    host = data["hostname"] or "this machine"
    up = data["uptime"]
    parts = [p for p in (name, f"on {host}") if p]
    line = " ".join(parts) if parts else host
    if up and up != "n/a":
        line += f" — up {up}"
    return line
