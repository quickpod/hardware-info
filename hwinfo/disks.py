"""Disk details: partitions, usage, filesystems, IO counters and SMART health.

SMART is optional and platform-dependent: we use ``pySMART`` when it is
importable AND a ``smartctl`` binary is present (it shells out to it).  When
neither is available the ``smart`` key is simply omitted -- never an error.
"""

from __future__ import annotations

import shutil

from ._common import human_bytes


def _smart_available():
    """True only if pySMART imports and smartctl is on PATH (pySMART needs it)."""
    try:
        import pySMART  # noqa: F401
    except Exception:
        return False
    return shutil.which("smartctl") is not None


def _smart_health():
    """Best-effort SMART assessment per device via pySMART.

    Returns a list of ``{device, name, assessment, temperature}`` dicts, or an
    empty list.  Wrapped so a flaky/permission-denied probe can't raise.
    """
    devices = []
    try:
        import pySMART

        dev_list = getattr(pySMART, "DeviceList", None)
        listing = dev_list().devices if dev_list else []
        for dev in listing:
            devices.append({
                "device": getattr(dev, "name", "") or "",
                "name": getattr(dev, "model", "") or getattr(dev, "name", "") or "",
                "assessment": getattr(dev, "assessment", None),
                "temperature": getattr(dev, "temperature", None),
            })
    except Exception:
        return []
    return devices


def disk_info(include_smart=True):
    """Return a JSON-serializable dict describing disks.

    Keys: ``partitions`` (list of ``{device, mountpoint, fstype, opts, total,
    used, free, percent, *_h}``) and ``io`` (aggregate + per-disk counters).
    When SMART tooling is present a top-level ``smart`` list is added; otherwise
    it is omitted entirely.
    """
    import psutil

    partitions = []
    try:
        parts = psutil.disk_partitions(all=False)
    except Exception:
        parts = []
    for part in parts:
        entry = {
            "device": part.device,
            "mountpoint": part.mountpoint,
            "fstype": part.fstype,
            "opts": getattr(part, "opts", ""),
            "total": 0, "used": 0, "free": 0, "percent": 0.0,
        }
        try:
            usage = psutil.disk_usage(part.mountpoint)
            entry.update({
                "total": int(usage.total),
                "used": int(usage.used),
                "free": int(usage.free),
                "percent": float(usage.percent),
            })
        except Exception:
            # e.g. an empty CD-ROM / permission-denied mount; keep zeros
            pass
        for key in ("total", "used", "free"):
            entry[key + "_h"] = human_bytes(entry[key])
        partitions.append(entry)

    io = {"total": {}, "per_disk": {}}
    try:
        agg = psutil.disk_io_counters(perdisk=False)
        if agg is not None:
            io["total"] = _io_dict(agg)
    except Exception:
        pass
    try:
        per = psutil.disk_io_counters(perdisk=True) or {}
        io["per_disk"] = {name: _io_dict(ctr) for name, ctr in per.items()}
    except Exception:
        io["per_disk"] = {}

    result = {"partitions": partitions, "io": io}

    if include_smart and _smart_available():
        health = _smart_health()
        if health:
            result["smart"] = health
    return result


def _io_dict(ctr):
    out = {
        "read_bytes": int(getattr(ctr, "read_bytes", 0)),
        "write_bytes": int(getattr(ctr, "write_bytes", 0)),
        "read_count": int(getattr(ctr, "read_count", 0)),
        "write_count": int(getattr(ctr, "write_count", 0)),
    }
    out["read_bytes_h"] = human_bytes(out["read_bytes"])
    out["write_bytes_h"] = human_bytes(out["write_bytes"])
    return out
