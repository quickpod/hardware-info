"""HardwareInfo -- a fully-offline system & hardware inventory with live sensors.

The public API is a set of small, dependency-light collector functions that each
return a plain, JSON-serializable ``dict``.  They lean on :mod:`psutil` (a
permissively-licensed cross-platform library) and the standard library, and fall
back gracefully when an optional tool (``nvidia-smi``, ``smartctl``,
``wmi``) or a piece of hardware is absent -- returning empty/partial data rather
than raising.  ``HWInfoError`` is the single error type callers must catch.

Importing this package is side-effect-free; nothing probes hardware until you
call a collector.  The GUI lives in :mod:`hwinfo.gui` (tkinter, built lazily);
the CLI is :mod:`hwinfo.__main__`.

100% AI-built, open source, published on QuickOpen (quickopen.ai).
"""

from __future__ import annotations

from .errors import HWInfoError
from .sysinfo import overview
from .cpu import cpu_info
from .memory import memory_info
from .disks import disk_info
from .network import network_info
from .sensors import sensors
from .gpu import gpu_info
from .report import full_report, export
from .monitor import sample

__all__ = [
    "HWInfoError",
    "overview",
    "cpu_info",
    "memory_info",
    "disk_info",
    "network_info",
    "sensors",
    "gpu_info",
    "full_report",
    "export",
    "sample",
    "__version__",
]

__version__ = "1.0.0"
