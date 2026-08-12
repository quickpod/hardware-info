"""A lightweight live snapshot for the GUI's System Monitor tab.

:func:`sample` is deliberately cheap: instantaneous CPU percentages (deltas
since the previous call), memory percent, network byte rates computed against
the previous sample, and any temperatures.  It keeps a tiny module-level cache
of the last network counters + timestamp so successive calls yield real rates;
the very first call reports zero rates.
"""

from __future__ import annotations

import time

from ._common import human_bytes

_last_net = None  # (timestamp, bytes_sent, bytes_recv)


def sample():
    """Return a small JSON-serializable snapshot dict.

    Keys: ``time`` (epoch), ``cpu_percent``, ``cpu_per_core`` (list),
    ``mem_percent``, ``mem_used``/``mem_total``, ``net_sent_rate``/
    ``net_recv_rate`` (bytes/sec, with ``*_h`` human strings) and ``temps`` (a
    flattened ``label -> current`` dict).  Never raises for absent hardware.
    """
    global _last_net
    now = time.time()

    cpu_percent = None
    cpu_per_core = []
    mem_percent = None
    mem_used = 0
    mem_total = 0
    try:
        import psutil

        cpu_percent = round(float(psutil.cpu_percent(interval=0.0)), 1)
        cpu_per_core = [round(float(x), 1)
                        for x in psutil.cpu_percent(interval=0.0, percpu=True)]
        vm = psutil.virtual_memory()
        mem_percent = float(vm.percent)
        mem_used = int(getattr(vm, "used", 0))
        mem_total = int(vm.total)
    except Exception:
        pass

    sent_rate = 0.0
    recv_rate = 0.0
    try:
        import psutil

        io = psutil.net_io_counters(pernic=False)
        if io is not None:
            if _last_net is not None:
                dt = max(1e-6, now - _last_net[0])
                sent_rate = max(0.0, (io.bytes_sent - _last_net[1]) / dt)
                recv_rate = max(0.0, (io.bytes_recv - _last_net[2]) / dt)
            _last_net = (now, io.bytes_sent, io.bytes_recv)
    except Exception:
        pass

    temps = {}
    try:
        from .sensors import sensors as _sensors

        for chip, entries in (_sensors().get("temperatures") or {}).items():
            for e in entries:
                if e.get("current") is not None:
                    temps[e.get("label") or chip] = e["current"]
    except Exception:
        temps = {}

    return {
        "time": now,
        "cpu_percent": cpu_percent,
        "cpu_per_core": cpu_per_core,
        "mem_percent": mem_percent,
        "mem_used": mem_used,
        "mem_total": mem_total,
        "mem_used_h": human_bytes(mem_used),
        "mem_total_h": human_bytes(mem_total),
        "net_sent_rate": sent_rate,
        "net_recv_rate": recv_rate,
        "net_sent_rate_h": human_bytes(sent_rate) + "/s",
        "net_recv_rate_h": human_bytes(recv_rate) + "/s",
        "temps": temps,
    }


def reset():
    """Clear the cached network baseline (used by tests for determinism)."""
    global _last_net
    _last_net = None
