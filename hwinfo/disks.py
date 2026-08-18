"""Disk details: partitions, usage, filesystems, IO counters and SMART health.

SMART is optional: it needs a ``smartctl`` binary, and reading it needs
privilege.  When either is missing the ``smart`` key is simply omitted --
never an error.

``smartctl --json`` is called directly rather than going through pySMART.
pySMART is a wrapper around the same binary, and its own device discovery
fails on some controllers -- NVMe in particular, where it reports a drive that
smartctl itself enumerates as "does not exist".  Parsing the documented JSON
output has no such gap and removes a dependency.
"""

from __future__ import annotations

import json
import shutil
import subprocess

from ._common import human_bytes

SMARTCTL_TIMEOUT = 15


def _smart_available():
    """True when a smartctl binary is present."""
    return shutil.which("smartctl") is not None


def _run_smartctl(args, timeout=SMARTCTL_TIMEOUT):
    """Run smartctl and return parsed JSON, or None.

    Reading SMART needs privilege, so an unprivileged call is retried through
    ``sudo -n``: with a NOPASSWD rule that succeeds silently, and without one
    it fails immediately rather than blocking on a password prompt that no
    GUI would ever show.
    """
    binary = shutil.which("smartctl")
    if not binary:
        return None
    for argv in ([binary] + args, ["sudo", "-n", binary] + args):
        try:
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  timeout=timeout, check=False)
        except Exception:
            continue
        # smartctl uses its exit code as a bitfield -- bits 0-2 mean the
        # command failed, anything above that is a drive warning and still
        # comes with usable JSON.
        if proc.returncode & 0b111 and not proc.stdout.strip():
            continue
        try:
            data = json.loads(proc.stdout)
        except Exception:
            continue
        if data.get("smartctl", {}).get("exit_status", 0) & 0b111 and \
                "device" not in data:
            continue
        return data
    return None


def _smart_scan():
    """Device paths smartctl can see, e.g. ``['/dev/nvme0', '/dev/sda']``."""
    data = _run_smartctl(["--scan", "--json"])
    if not data:
        return []
    return [d.get("name") for d in data.get("devices", []) if d.get("name")]


def _smart_health():
    """Best-effort SMART assessment per device.

    Returns a list of ``{device, name, assessment, temperature}`` dicts, or an
    empty list.  Every probe is wrapped: a flaky or permission-denied drive
    must not take the whole report down with it.
    """
    devices = []
    for path in _smart_scan():
        data = _run_smartctl(["-H", "-i", "-A", "--json", path])
        if not data:
            continue
        passed = data.get("smart_status", {}).get("passed")
        assessment = None
        if passed is True:
            assessment = "PASS"
        elif passed is False:
            assessment = "FAIL"
        temp = data.get("temperature", {}).get("current")
        model = (data.get("model_name")
                 or data.get("scsi_model_name")
                 or path)
        devices.append({
            "device": path,
            "name": model,
            "assessment": assessment,
            "temperature": temp,
        })
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
