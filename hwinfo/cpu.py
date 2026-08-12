"""CPU details: model, core counts, frequencies and per-core utilisation."""

from __future__ import annotations

import platform

from ._common import human_hz


def _model_name():
    """Best-effort human CPU model.  ``platform.processor()`` is often empty on
    Linux, so we also peek at ``/proc/cpuinfo`` and the registry-ish fallbacks.
    """
    name = (platform.processor() or "").strip()
    if name:
        return name
    # Linux: /proc/cpuinfo "model name"
    try:
        with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass
    # macOS
    try:
        import subprocess

        out = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True, text=True, timeout=3,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return platform.machine() or "Unknown CPU"


def cpu_info(per_core_interval=0.0):
    """Return a JSON-serializable dict describing the CPU.

    Keys: ``model``, ``architecture``, ``cores_physical``, ``cores_logical``,
    ``frequency`` (``{current_mhz, min_mhz, max_mhz, ...}``), ``percent_total``,
    ``percent_per_core`` (list), and ``stats``.  ``per_core_interval`` is passed
    to psutil for the utilisation sample; ``0`` returns instantaneous numbers
    (deltas since the last call) which keeps this cheap and deterministic-ish.
    """
    import psutil

    try:
        phys = psutil.cpu_count(logical=False)
    except Exception:
        phys = None
    try:
        logi = psutil.cpu_count(logical=True)
    except Exception:
        logi = None

    freq = {"current_mhz": None, "min_mhz": None, "max_mhz": None,
            "current": "n/a", "max": "n/a"}
    try:
        f = psutil.cpu_freq()
        if f is not None:
            freq["current_mhz"] = _num(f.current)
            freq["min_mhz"] = _num(f.min)
            freq["max_mhz"] = _num(f.max)
            freq["current"] = human_hz(f.current)
            freq["max"] = human_hz(f.max)
    except Exception:
        pass

    try:
        per_core = psutil.cpu_percent(interval=per_core_interval, percpu=True)
        per_core = [round(float(x), 1) for x in per_core]
    except Exception:
        per_core = []

    try:
        total = round(float(psutil.cpu_percent(interval=0.0)), 1)
    except Exception:
        total = None

    stats = {}
    try:
        st = psutil.cpu_stats()
        stats = {
            "ctx_switches": int(st.ctx_switches),
            "interrupts": int(st.interrupts),
            "soft_interrupts": int(st.soft_interrupts),
            "syscalls": int(st.syscalls),
        }
    except Exception:
        stats = {}

    return {
        "model": _model_name(),
        "architecture": platform.machine() or "",
        "cores_physical": phys,
        "cores_logical": logi,
        "frequency": freq,
        "percent_total": total,
        "percent_per_core": per_core,
        "stats": stats,
    }


def _num(value):
    try:
        v = float(value)
        return round(v, 2) if v else 0.0
    except (TypeError, ValueError):
        return None
