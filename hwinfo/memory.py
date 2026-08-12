"""Memory details: virtual (RAM) and swap, with human-formatted sizes."""

from __future__ import annotations

from ._common import human_bytes


def memory_info():
    """Return a JSON-serializable dict with ``virtual`` and ``swap`` sections.

    ``virtual`` has ``total``/``available``/``used``/``free`` (bytes) plus a
    ``percent`` and human-formatted ``*_h`` strings; ``swap`` is similar.  All
    values are plain numbers/strings; missing metrics degrade to ``0``.
    """
    import psutil

    vm = psutil.virtual_memory()
    virtual = {
        "total": int(vm.total),
        "available": int(getattr(vm, "available", 0)),
        "used": int(getattr(vm, "used", 0)),
        "free": int(getattr(vm, "free", 0)),
        "percent": float(vm.percent),
    }
    for key in ("total", "available", "used", "free"):
        virtual[key + "_h"] = human_bytes(virtual[key])

    swap_section = {"total": 0, "used": 0, "free": 0, "percent": 0.0}
    try:
        sw = psutil.swap_memory()
        swap_section = {
            "total": int(sw.total),
            "used": int(sw.used),
            "free": int(sw.free),
            "percent": float(sw.percent),
        }
    except Exception:
        pass
    for key in ("total", "used", "free"):
        swap_section[key + "_h"] = human_bytes(swap_section[key])

    return {"virtual": virtual, "swap": swap_section}
