"""GPU details -- best-effort, no hard dependency on any GPU library.

Primary path: parse ``nvidia-smi --query-gpu=... --format=csv`` if the binary is
present.  Failing that we look for a couple of optional cross-vendor hints
(``wmi`` Win32_VideoController on Windows, ``/sys`` DRM entries on Linux) purely
for a name.  When nothing is found :func:`gpu_info` returns
``{"gpus": [], "source": None}`` -- never an error.
"""

from __future__ import annotations

import shutil
import subprocess


_NVIDIA_FIELDS = [
    ("name", str),
    ("memory.total", "mib"),
    ("memory.used", "mib"),
    ("memory.free", "mib"),
    ("utilization.gpu", "pct"),
    ("temperature.gpu", "num"),
    ("driver_version", str),
]


def _nvidia_smi():
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    query = ",".join(f for f, _ in _NVIDIA_FIELDS)
    try:
        proc = subprocess.run(
            [exe, f"--query-gpu={query}", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=6,
        )
    except Exception:
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None

    gpus = []
    for line in proc.stdout.strip().splitlines():
        cells = [c.strip() for c in line.split(",")]
        if len(cells) < len(_NVIDIA_FIELDS):
            continue
        entry = {}
        for (field, kind), raw in zip(_NVIDIA_FIELDS, cells):
            key = field.replace(".", "_")
            entry[key] = _coerce(raw, kind)
        entry["vendor"] = "NVIDIA"
        gpus.append(entry)
    return gpus or None


def _wmi_names():
    try:
        import wmi  # type: ignore

        conn = wmi.WMI()
        gpus = []
        for c in conn.Win32_VideoController():
            gpus.append({
                "name": getattr(c, "Name", "") or "",
                "vendor": getattr(c, "AdapterCompatibility", "") or "",
                "driver_version": getattr(c, "DriverVersion", "") or "",
            })
        return gpus or None
    except Exception:
        return None


def _linux_drm_names():
    """Very light DRM probe: read vendor/device ids' human names if present."""
    import glob
    import os

    names = []
    for path in sorted(glob.glob("/sys/class/drm/card[0-9]/device/")):
        try:
            uevent = os.path.join(path, "uevent")
            label = None
            if os.path.exists(uevent):
                with open(uevent, "r", encoding="utf-8", errors="ignore") as fh:
                    for ln in fh:
                        if ln.startswith("DRIVER="):
                            label = ln.split("=", 1)[1].strip()
                            break
            names.append({"name": label or os.path.basename(path.rstrip("/")),
                          "vendor": label or ""})
        except Exception:
            continue
    return names or None


def gpu_info():
    """Return a JSON-serializable dict: ``{"gpus": [...], "source": <str|None>}``.

    Each GPU dict always has at least a ``name``; NVIDIA entries also carry
    memory/utilisation/temperature.  Empty list when no GPU tooling is found.
    """
    gpus = _nvidia_smi()
    if gpus:
        return {"gpus": gpus, "source": "nvidia-smi"}

    gpus = _wmi_names()
    if gpus:
        return {"gpus": gpus, "source": "wmi"}

    gpus = _linux_drm_names()
    if gpus:
        return {"gpus": gpus, "source": "drm"}

    return {"gpus": [], "source": None}


def _coerce(raw, kind):
    if raw in ("", "[N/A]", "N/A", "[Not Supported]"):
        return None
    if kind is str:
        return raw
    try:
        if kind == "mib":
            return {"mib": float(raw), "bytes": int(float(raw) * 1024 * 1024)}
        if kind == "pct":
            return float(raw)
        if kind == "num":
            return float(raw)
    except (TypeError, ValueError):
        return None
    return raw
