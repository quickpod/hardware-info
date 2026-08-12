"""Assemble a full inventory report and export it as JSON or plain text."""

from __future__ import annotations

import datetime
import json
import os

from .errors import HWInfoError
from ._common import human_bytes
from .sysinfo import overview
from .cpu import cpu_info
from .memory import memory_info
from .disks import disk_info
from .network import network_info
from .sensors import sensors
from .gpu import gpu_info


def full_report():
    """Return a JSON-serializable dict merging every section.

    Top-level keys: ``generated_at`` (ISO-8601), ``overview``, ``cpu``,
    ``memory``, ``disks``, ``network``, ``sensors`` and ``gpu``.  Each section is
    produced by its own collector and degrades gracefully; the whole thing is
    safe to ``json.dumps``.
    """
    return {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "overview": overview(),
        "cpu": cpu_info(),
        "memory": memory_info(),
        "disks": disk_info(),
        "network": network_info(),
        "sensors": sensors(),
        "gpu": gpu_info(),
    }


def export(path, fmt="json", report=None):
    """Write a report to *path* as ``fmt`` (``"json"`` or ``"txt"``).

    Builds a fresh :func:`full_report` unless *report* is supplied.  Returns the
    absolute path written.  Raises :class:`HWInfoError` on an unsupported format
    or any write/serialisation failure (so the CLI/GUI get one clean error).
    """
    fmt = (fmt or "json").lower().lstrip(".")
    if fmt not in ("json", "txt"):
        raise HWInfoError(f"unsupported export format: {fmt!r} (use json or txt)")
    if not path:
        raise HWInfoError("no output path given")
    if report is None:
        report = full_report()

    try:
        if fmt == "json":
            text = json.dumps(report, indent=2, sort_keys=False)
        else:
            text = render_text(report)
        parent = os.path.dirname(os.path.abspath(path))
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
            if not text.endswith("\n"):
                fh.write("\n")
    except HWInfoError:
        raise
    except Exception as exc:
        raise HWInfoError(f"could not write report to {path}: {exc}") from exc
    return os.path.abspath(path)


def render_text(report):
    """Render a report dict as a readable plain-text document (str)."""
    lines = []

    def head(title):
        lines.append("")
        lines.append(title)
        lines.append("=" * len(title))

    lines.append("HardwareInfo report")
    lines.append(f"Generated: {report.get('generated_at', '')}")

    ov = report.get("overview", {})
    head("System")
    lines.append(f"  Summary:   {ov.get('summary', '')}")
    lines.append(f"  Hostname:  {ov.get('hostname', '')}")
    os_ = ov.get("os", {})
    lines.append(f"  OS:        {os_.get('system', '')} {os_.get('release', '')}")
    lines.append(f"  Platform:  {os_.get('platform', '')}")
    lines.append(f"  Machine:   {ov.get('machine', '')} ({ov.get('architecture', '')})")
    lines.append(f"  Uptime:    {ov.get('uptime', '')}")
    py = ov.get("python", {})
    lines.append(f"  Python:    {py.get('implementation', '')} {py.get('version', '')}")

    cpu = report.get("cpu", {})
    head("CPU")
    lines.append(f"  Model:     {cpu.get('model', '')}")
    lines.append(f"  Cores:     {cpu.get('cores_physical')} physical / "
                 f"{cpu.get('cores_logical')} logical")
    freq = cpu.get("frequency", {})
    lines.append(f"  Frequency: {freq.get('current', 'n/a')} "
                 f"(max {freq.get('max', 'n/a')})")
    lines.append(f"  Load:      {cpu.get('percent_total')}%")

    mem = report.get("memory", {})
    vm = mem.get("virtual", {})
    sw = mem.get("swap", {})
    head("Memory")
    lines.append(f"  RAM:       {vm.get('used_h', '')} / {vm.get('total_h', '')} "
                 f"({vm.get('percent')}%)")
    lines.append(f"  Swap:      {sw.get('used_h', '')} / {sw.get('total_h', '')} "
                 f"({sw.get('percent')}%)")

    head("Disks")
    for p in report.get("disks", {}).get("partitions", []):
        lines.append(f"  {p.get('device', ''):<18} {p.get('mountpoint', ''):<16} "
                     f"{p.get('fstype', ''):<8} "
                     f"{p.get('used_h', ''):>10} / {p.get('total_h', ''):<10} "
                     f"({p.get('percent')}%)")
    for dev in report.get("disks", {}).get("smart", []):
        lines.append(f"  SMART {dev.get('device', '')}: {dev.get('assessment')} "
                     f"({dev.get('name', '')})")

    head("Network")
    for name, nic in report.get("network", {}).get("interfaces", {}).items():
        state = "up" if nic.get("is_up") else "down"
        speed = nic.get("speed_mbps") or 0
        lines.append(f"  {name} [{state}] {speed} Mbps")
        for a in nic.get("addresses", []):
            lines.append(f"      {a.get('family', ''):<5} {a.get('address', '')}")

    sens = report.get("sensors", {})
    head("Sensors")
    temps = sens.get("temperatures", {})
    if temps:
        for chip, entries in temps.items():
            for e in entries:
                lines.append(f"  {chip}/{e.get('label', '')}: {e.get('current')} °C")
    else:
        lines.append("  (no temperature sensors detected)")
    bat = sens.get("battery")
    if bat:
        plugged = "plugged in" if bat.get("power_plugged") else "on battery"
        lines.append(f"  Battery: {bat.get('percent')}% ({plugged})")

    head("GPU")
    gpus = report.get("gpu", {}).get("gpus", [])
    if gpus:
        for g in gpus:
            mem_total = g.get("memory_total")
            mem_str = ""
            if isinstance(mem_total, dict):
                mem_str = f" — {human_bytes(mem_total.get('bytes'))}"
            lines.append(f"  {g.get('name', 'GPU')}{mem_str}")
    else:
        lines.append("  (no GPU detected / no GPU tooling available)")

    return "\n".join(lines)
