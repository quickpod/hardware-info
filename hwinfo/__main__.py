"""Command-line interface: ``python -m hwinfo <command> ...``.

Every subcommand accepts ``--json`` to dump the raw collector dict; otherwise a
compact human summary is printed.  A failure anywhere surfaces as a single
``HWInfoError`` and a clean non-zero exit (never a traceback).
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from .errors import HWInfoError
from ._common import human_bytes
from .sysinfo import overview
from .cpu import cpu_info
from .memory import memory_info
from .disks import disk_info
from .network import network_info
from .sensors import sensors
from .gpu import gpu_info
from .report import full_report, export, render_text
from .monitor import sample


def _emit(data, as_json):
    if as_json:
        print(json.dumps(data, indent=2))
        return True
    return False


# --- command handlers -------------------------------------------------------


def cmd_overview(a):
    d = overview()
    if _emit(d, a.json):
        return
    os_ = d["os"]
    py = d["python"]
    print(d["summary"])
    print(f"Hostname:  {d['hostname']}")
    print(f"OS:        {os_['system']} {os_['release']}")
    print(f"Platform:  {os_['platform']}")
    print(f"Machine:   {d['machine']} ({d['architecture']})")
    print(f"Uptime:    {d['uptime']}")
    print(f"Python:    {py['implementation']} {py['version']}")


def cmd_cpu(a):
    d = cpu_info()
    if _emit(d, a.json):
        return
    freq = d["frequency"]
    print(f"Model:     {d['model']}")
    print(f"Cores:     {d['cores_physical']} physical / {d['cores_logical']} logical")
    print(f"Frequency: {freq['current']} (max {freq['max']})")
    print(f"Load:      {d['percent_total']}%")
    if d["percent_per_core"]:
        cells = "  ".join(f"{i}:{p:.0f}%" for i, p in enumerate(d["percent_per_core"]))
        print(f"Per-core:  {cells}")


def cmd_memory(a):
    d = memory_info()
    if _emit(d, a.json):
        return
    vm, sw = d["virtual"], d["swap"]
    print(f"RAM:  {vm['used_h']} / {vm['total_h']} ({vm['percent']}%), "
          f"{vm['available_h']} available")
    print(f"Swap: {sw['used_h']} / {sw['total_h']} ({sw['percent']}%)")


def cmd_disks(a):
    d = disk_info()
    if _emit(d, a.json):
        return
    for p in d["partitions"]:
        print(f"{p['device']:<18} {p['mountpoint']:<16} {p['fstype']:<8} "
              f"{p['used_h']:>10} / {p['total_h']:<10} ({p['percent']}%)")
    for dev in d.get("smart", []):
        print(f"SMART {dev['device']}: {dev['assessment']} ({dev['name']})")


def cmd_network(a):
    d = network_info()
    if _emit(d, a.json):
        return
    for name, nic in d["interfaces"].items():
        state = "up" if nic["is_up"] else "down"
        print(f"{name} [{state}] {nic.get('speed_mbps') or 0} Mbps")
        for addr in nic["addresses"]:
            print(f"    {addr['family']:<5} {addr['address']}")


def cmd_sensors(a):
    d = sensors()
    if _emit(d, a.json):
        return
    temps = d["temperatures"]
    if temps:
        for chip, entries in temps.items():
            for e in entries:
                print(f"{chip}/{e['label']}: {e['current']} °C")
    else:
        print("No temperature sensors detected.")
    for chip, entries in d.get("fans", {}).items():
        for e in entries:
            print(f"{chip}/{e['label']}: {e['rpm']} rpm")
    bat = d.get("battery")
    if bat:
        plugged = "plugged in" if bat["power_plugged"] else "on battery"
        print(f"Battery: {bat['percent']}% ({plugged})")


def cmd_gpu(a):
    d = gpu_info()
    if _emit(d, a.json):
        return
    if not d["gpus"]:
        print("No GPU detected (or no GPU tooling available).")
        return
    for g in d["gpus"]:
        line = g.get("name", "GPU")
        mem = g.get("memory_total")
        if isinstance(mem, dict):
            line += f" — {human_bytes(mem.get('bytes'))}"
        if g.get("utilization_gpu") is not None:
            line += f" — {g['utilization_gpu']}% util"
        if g.get("temperature_gpu") is not None:
            line += f" — {g['temperature_gpu']} °C"
        print(line)


def cmd_report(a):
    rep = full_report()
    if a.out:
        fmt = "txt" if a.txt else "json"
        path = export(a.out, fmt=fmt, report=rep)
        print(f"Wrote {fmt} report -> {path}")
        return
    if a.txt and not a.json:
        print(render_text(rep))
    else:
        print(json.dumps(rep, indent=2))


def cmd_watch(a):
    seconds = a.seconds
    end = time.time() + seconds if seconds and seconds > 0 else None
    try:
        while True:
            snap = sample()
            if a.json:
                print(json.dumps(snap))
            else:
                cores = " ".join(f"{p:.0f}" for p in snap["cpu_per_core"])
                print(f"CPU {snap['cpu_percent']}% [{cores}]  "
                      f"MEM {snap['mem_percent']}% "
                      f"({snap['mem_used_h']}/{snap['mem_total_h']})  "
                      f"NET ↑{snap['net_sent_rate_h']} ↓{snap['net_recv_rate_h']}")
            sys.stdout.flush()
            if end is not None and time.time() >= end:
                break
            time.sleep(max(0.2, a.interval))
    except KeyboardInterrupt:
        pass


# --- parser -----------------------------------------------------------------


def build_parser():
    p = argparse.ArgumentParser(
        prog="hwinfo",
        description="Offline system & hardware inventory with live sensors. "
                    "Add --json to any command for the raw data.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    def add(name, help, handler, with_json=True):
        sp = sub.add_parser(name, help=help)
        sp.set_defaults(func=handler)
        if with_json:
            sp.add_argument("--json", action="store_true",
                            help="emit raw JSON instead of a summary")
        return sp

    add("overview", "OS, host, uptime, Python & architecture", cmd_overview)
    add("cpu", "CPU model, cores, frequency and load", cmd_cpu)
    add("memory", "RAM and swap usage", cmd_memory)
    add("disks", "Partitions, usage and SMART health", cmd_disks)
    add("network", "Interfaces, addresses and link state", cmd_network)
    add("sensors", "Temperatures, fans and battery", cmd_sensors)
    add("gpu", "GPU inventory (best-effort)", cmd_gpu)

    s = add("report", "Full inventory (all sections)", cmd_report)
    s.add_argument("--txt", action="store_true", help="text format (with --out)")
    s.add_argument("--out", help="write the report to this file")

    s = add("watch", "Live system monitor in the terminal", cmd_watch)
    s.add_argument("seconds", nargs="?", type=float, default=0,
                   help="stop after N seconds (default: run until Ctrl-C)")
    s.add_argument("--interval", type=float, default=1.0,
                   help="seconds between samples (default: 1.0)")

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except HWInfoError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
