#!/usr/bin/env python3
r"""HardwareInfo -- an Aura (QuickOpen design system) GUI on top of ``hwinfo``.

A single Aura window: the sidebar lists the sections (Overview, CPU, Memory,
Disks, Network, Sensors, GPU, System Monitor) and the content pane swaps to the
selected section.  Every panel reads the tested core collectors (never
re-implements probing) and the live "System Monitor" refreshes on a timer:
samples are taken on a worker thread and marshalled back with ``self.after``
-- the UI thread never blocks.  Errors surface in the Aura status bar (the
``HWInfoError`` message, never a raw traceback).

Design goals baked in here (mirrors the QuickOpen house style):
  * built on the vendored ``hwinfo/aura.py`` design system, which layers the
    quickopen.ai look (deep space + light) over CustomTkinter.  Runtime deps:
    ``customtkinter`` (+ ``darkdetect``) — declared in requirements.txt; the
    PyInstaller build adds ``--collect-all customtkinter``.
  * Importing this module does nothing.  Only :func:`main` builds a root
    window, and it degrades gracefully (prints a message, returns 0) with no
    display or with customtkinter missing.
  * Frozen-exe safe: bundled assets are resolved via ``sys._MEIPASS`` / the exe
    directory when ``sys.frozen`` is set -- never ``__file__``.

100% AI-built, open source, published on QuickOpen (quickopen.ai).
"""

from __future__ import annotations

import os
import sys
import threading

# NOTE: tkinter/customtkinter are imported lazily inside main()/build_app so
# that merely importing this module (e.g. during packaging or on a headless CI
# box) never fails.

APP_NAME = "HardwareInfo"
APP_VERSION = "1.0.0"
WINDOW_TITLE = "HardwareInfo — by QuickOpen (quickopen.ai)"
PROJECT_URL = "https://quickopen.ai/projects/hardware-info"
ACCENT = "#2f5fe0"      # publish/specs/hardware-info.json "accent": [47, 95, 224]

# (section_id, label, sidebar glyph) -- glyphs are DejaVu-safe (no tofu on
# Linux/Xvfb; NOTE ⌗ and ⏱ are NOT in DejaVu despite older notes).
# section_id maps to a _panel_<id> builder method.
SECTIONS = [
    ("overview", "Overview", "⌂"),
    ("cpu", "CPU", "◈"),
    ("memory", "Memory", "▤"),
    ("disks", "Disks", "⛁"),
    ("network", "Network", "⇄"),
    ("sensors", "Sensors", "⊙"),
    ("gpu", "GPU", "▦"),
    ("monitor", "System Monitor", "◷"),
]

SECTION_DESCRIPTIONS = {
    "overview": "Operating system, host, uptime, Python and architecture.",
    "cpu": "Model, core counts, frequency and live per-core utilisation.",
    "memory": "Physical RAM and swap usage.",
    "disks": "Partitions, filesystems, usage and SMART health where available.",
    "network": "Interfaces, addresses, link state, speeds and IO totals.",
    "sensors": "Temperatures, fan speeds and battery (where the OS exposes them).",
    "gpu": "Best-effort GPU inventory (nvidia-smi / WMI / DRM).",
    "monitor": "Live CPU, memory and network — refreshes automatically.",
}


# ---------------------------------------------------------------------------
# Asset / frozen handling
# ---------------------------------------------------------------------------
def asset_path(name):
    """Locate a bundled asset from source OR a PyInstaller one-file build.

    For a frozen exe we look only at ``sys._MEIPASS`` and the executable's own
    directory (never ``__file__``).  From source we also consult the package
    dir, the repo root and the CWD.  Returns an absolute path or ``None``.
    """
    roots = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            roots.append(meipass)
        roots.append(os.path.dirname(os.path.abspath(sys.executable)))
    else:
        here = os.path.dirname(os.path.abspath(__file__))
        roots += [here, os.path.dirname(here), os.getcwd()]
    for root in roots:
        candidate = os.path.join(root, name)
        if os.path.exists(candidate):
            return candidate
    return None


def open_in_file_manager(path):
    """Best-effort 'reveal in file manager', guarded on every platform."""
    try:
        folder = path if os.path.isdir(path) else os.path.dirname(os.path.abspath(path))
        if hasattr(os, "startfile"):          # Windows
            os.startfile(folder)              # noqa: S606 - intended
        elif sys.platform == "darwin":
            import subprocess
            subprocess.Popen(["open", folder])
        else:
            import subprocess
            subprocess.Popen(["xdg-open", folder])
        return True
    except Exception:
        return False


def open_with_default_app(path):
    """Open a file/URL with the OS default application, guarded."""
    try:
        if hasattr(os, "startfile"):
            os.startfile(path)                # noqa: S606
        elif sys.platform == "darwin":
            import subprocess
            subprocess.Popen(["open", path])
        else:
            import subprocess
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# The app (built lazily; tkinter/customtkinter imported only inside build_app)
# ---------------------------------------------------------------------------
def build_app():
    """Construct and return the App class bound to live GUI imports.

    Kept inside a function so this module imports cleanly without a display
    (and without customtkinter installed).
    """
    import tkinter as tk
    from tkinter import filedialog, ttk
    import customtkinter as ctk

    from . import aura, guiconfig
    from .errors import HWInfoError
    from . import (
        overview, cpu_info, memory_info, disk_info,
        network_info, sensors, gpu_info,
    )
    from . import monitor as monitor_mod
    from .report import full_report, export

    def tone(key):
        """(light, dark) color tuple from the Aura tokens — auto-flips."""
        return (aura.TOKENS["light"][key], aura.TOKENS["dark"][key])

    def line(parent, text, muted=False):
        """One left-aligned body-text row (the workhorse of the info panels)."""
        return ctk.CTkLabel(parent, text=text, font=aura.font(role="body"),
                            anchor="w", justify="left",
                            text_color=tone("muted") if muted else tone("text"))

    # -- small reusable widgets ------------------------------------------

    class KeyValue(ctk.CTkFrame):
        """A tidy two-column list of (label, value) rows (goes in a Card.body)."""

        def __init__(self, master):
            super().__init__(master, fg_color="transparent")
            self._row = 0
            self.grid_columnconfigure(1, weight=1)

        def add(self, label, value):
            ctk.CTkLabel(self, text=label, font=aura.font(role="body"),
                         text_color=tone("muted"), anchor="w").grid(
                row=self._row, column=0, sticky="w", padx=(0, 18), pady=2)
            ctk.CTkLabel(self, text=str(value), font=aura.font(role="body"),
                         text_color=tone("text"), anchor="w", justify="left",
                         wraplength=560).grid(
                row=self._row, column=1, sticky="w", pady=2)
            self._row += 1

    class Meter(ctk.CTkFrame):
        """A labelled percentage bar drawn on a raw Canvas.

        The canvas is custom-painted, so it re-renders itself from the live
        Aura palette (accent fill on a surface2 track; warn/danger tokens at
        high load) — the app re-renders every registered Meter on theme flip.
        NOTE: never assign ``self._w`` on a widget subclass — tkinter uses it
        as the widget path name (see the Aura manual do/don'ts).
        """

        def __init__(self, master, app, caption="", width=260):
            super().__init__(master, fg_color="transparent")
            self.app = app
            self._pct = 0.0
            self._default_width = width
            self.cap = ctk.CTkLabel(self, text=caption, width=104, anchor="w",
                                    font=aura.font(role="body"),
                                    text_color=tone("muted"))
            self.cap.pack(side="left")
            self.canvas = tk.Canvas(self, height=6, width=width,
                                    highlightthickness=0, bd=0)
            self.canvas.pack(side="left", fill="x", expand=True, padx=(8, 8))
            self.val = ctk.CTkLabel(self, text="—", width=48, anchor="e",
                                    font=aura.font(role="body"),
                                    text_color=tone("text"))
            self.val.pack(side="left")
            self.canvas.bind("<Configure>", lambda _e: self._redraw())
            app.register_meter(self)
            self._redraw()

        def set(self, pct, text=None):
            try:
                pct = max(0.0, min(100.0, float(pct)))
            except (TypeError, ValueError):
                pct = 0.0
            self._pct = pct
            self.val.configure(text=text if text is not None else f"{pct:.0f}%")
            self._redraw()

        def set_caption(self, text):
            self.cap.configure(text=text)

        def _redraw(self):
            p = aura.P()
            c = self.canvas
            c.delete("all")
            w = c.winfo_width() or self._default_width
            h = int(c["height"])
            c.configure(bg=p["surface2"])                     # track
            fill = p["accent"] if self._pct < 75 else (
                p["warn"] if self._pct < 90 else p["danger"])
            fw = int(w * self._pct / 100.0)
            if fw > 0:
                c.create_rectangle(0, 0, fw, h, fill=fill, width=0)

    # -- the main window --------------------------------------------------

    class App(aura.AuraApp):
        def __init__(self):
            super().__init__(
                title=WINDOW_TITLE, app_name=APP_NAME, accent=ACCENT,
                theme=guiconfig.get_theme(),
                icon_png=asset_path("hardware-info.png"), version=APP_VERSION,
                tagline="offline inventory",
                on_theme_change=guiconfig.set_theme,
                size=(1100, 700), min_size=(900, 560))

            self._busy = False
            self._mon_running = False
            self._mon_job = None
            self._mon_widgets = {}     # live monitor widget handles
            self._mon_core_meters = []
            self._meters = []          # every live Meter (theme-flip registry)
            self._img_refs_gui = []    # keep PhotoImage refs alive

            self._set_icon()
            self._build_menu()
            for sid, label, glyph in SECTIONS:
                self.add_section(sid, label, glyph,
                                 lambda f, s=sid: self._build_section(s, f))
            aura.AuraButton(self.header_actions, "Refresh", kind="secondary",
                            command=self._refresh_current).pack(side="left")
            aura.AuraButton(self.header_actions, "Export report…",
                            command=self._export_report).pack(
                side="left", padx=(10, 0))
            self.show("overview")
            self.set_status("Ready")
            self.protocol("WM_DELETE_WINDOW", self._on_close)

        # ---- assets / icon
        def _set_icon(self):
            try:
                ico = asset_path("hardware-info.ico")
                if ico and os.name == "nt":
                    self.iconbitmap(ico)
                    return
            except Exception:
                pass
            try:
                png = asset_path("hardware-info.png")
                if png:
                    img = tk.PhotoImage(file=png)
                    self._img_refs_gui.append(img)
                    self.iconphoto(True, img)
            except Exception:
                pass  # icon is cosmetic; never block launch

        # ---- meters / theming
        def register_meter(self, meter):
            self._meters.append(meter)

        def _retheme_meters(self):
            for m in list(self._meters):
                try:
                    if not m.canvas.winfo_exists():
                        self._meters.remove(m)
                        continue
                    m._redraw()
                except Exception:
                    pass

        def set_theme(self, theme):
            super().set_theme(theme)
            self._retheme_meters()      # custom canvases don't auto-flip

        # ---- menu (native menus stay; theme also lives in the sidebar toggle)
        def _build_menu(self):
            bar = tk.Menu(self)
            filem = tk.Menu(bar, tearoff=0)
            filem.add_command(label="Export report…", accelerator="Ctrl+E",
                              command=self._export_report)
            filem.add_command(label="Refresh", accelerator="F5",
                              command=self._refresh_current)
            filem.add_separator()
            filem.add_command(label="Exit", command=self._on_close)
            bar.add_cascade(label="File", menu=filem)

            viewm = tk.Menu(bar, tearoff=0)
            viewm.add_command(
                label="Toggle dark mode",
                command=lambda: self.set_theme(
                    "light" if self.theme == "dark" else "dark"))
            bar.add_cascade(label="View", menu=viewm)

            helpm = tk.Menu(bar, tearoff=0)
            helpm.add_command(label="About", command=self._about)
            helpm.add_command(label="Open project page (quickopen.ai)",
                              command=lambda: open_with_default_app(PROJECT_URL))
            bar.add_cascade(label="Help", menu=helpm)
            self.configure(menu=bar)
            self.bind_all("<Control-e>", lambda e: self._export_report())
            self.bind_all("<F5>", lambda e: self._refresh_current())

        # ---- navigation (rebuild on every visit so data is fresh)
        def show(self, sid):
            # leaving (or rebuilding) the monitor section? stop the timer.
            if self.active_section == "monitor":
                self._stop_monitor()
            sec = self._sections.get(sid)
            if sec and sec["built"]:
                for child in sec["frame"].winfo_children():
                    child.destroy()
                sec["built"] = False
            if sec:
                self.set_status("Ready")
            super().show(sid)
            if sid == "monitor" and sec:
                self._start_monitor()

        def _refresh_current(self):
            if self.active_section:
                self.show(self.active_section)

        def _build_section(self, sid, frame):
            desc = SECTION_DESCRIPTIONS.get(sid)
            if desc:
                aura.Caption(frame, desc).pack(anchor="w", pady=(0, 10))
            label = {s: l for s, l, _g in SECTIONS}.get(sid, sid)
            try:
                getattr(self, "_panel_" + sid)(frame)
            except HWInfoError as exc:
                self.set_error(str(exc))
            except Exception as exc:  # never leak a traceback
                self.set_error(f"Could not read {label}: {exc}")

        # ---- scrollable helper
        def _scroll_host(self, parent):
            """Return an inner frame inside a vertical-scrolling host."""
            host = ctk.CTkScrollableFrame(parent, fg_color="transparent")
            host.pack(fill="both", expand=True)
            return host

        # =====================================================================
        # PANELS
        # =====================================================================
        def _panel_overview(self, parent):
            d = overview()
            host = self._scroll_host(parent)
            os_ = d["os"]
            py = d["python"]

            card = aura.Card(host, title="System")
            card.pack(fill="x")
            kv = KeyValue(card.body)
            kv.pack(fill="x")
            kv.add("Summary", d["summary"])
            kv.add("Hostname", d["hostname"])
            kv.add("Operating system", f"{os_['system']} {os_['release']}")
            kv.add("Version", os_["version"])
            kv.add("Platform", os_["platform"])
            kv.add("Machine", f"{d['machine']} ({d['architecture']})")
            kv.add("Processor", d["processor"] or "—")
            kv.add("Uptime", d["uptime"])

            card2 = aura.Card(host, title="Python runtime")
            card2.pack(fill="x", pady=(14, 0))
            kv2 = KeyValue(card2.body)
            kv2.pack(fill="x")
            kv2.add("Version", f"{py['implementation']} {py['version']}")
            kv2.add("Compiler", py["compiler"])
            kv2.add("Executable", py["executable"])

        def _panel_cpu(self, parent):
            d = cpu_info(per_core_interval=0.0)
            host = self._scroll_host(parent)
            freq = d["frequency"]

            card = aura.Card(host, title="Processor")
            card.pack(fill="x")
            kv = KeyValue(card.body)
            kv.pack(fill="x")
            kv.add("Model", d["model"])
            kv.add("Architecture", d["architecture"])
            kv.add("Cores", f"{d['cores_physical']} physical / "
                            f"{d['cores_logical']} logical")
            kv.add("Frequency", f"{freq['current']} (max {freq['max']})")
            kv.add("Total load", f"{d['percent_total']}%")

            bars = aura.Card(host, title="Per-core utilisation")
            bars.pack(fill="x", pady=(14, 0))
            for i, pct in enumerate(d["percent_per_core"]):
                m = Meter(bars.body, self, caption=f"Core {i}")
                m.pack(fill="x", pady=2)
                m.set(pct)
            if not d["percent_per_core"]:
                line(bars.body, "(per-core data unavailable)",
                     muted=True).pack(anchor="w")

        def _panel_memory(self, parent):
            d = memory_info()
            host = self._scroll_host(parent)
            vm, sw = d["virtual"], d["swap"]

            card = aura.Card(host, title="Physical memory (RAM)")
            card.pack(fill="x")
            m = Meter(card.body, self, caption="RAM")
            m.pack(fill="x", pady=(2, 6))
            m.set(vm["percent"], text=f"{vm['percent']:.0f}%")
            line(card.body,
                 f"{vm['used_h']} used / {vm['total_h']} total  "
                 f"({vm['available_h']} available)").pack(anchor="w")

            card2 = aura.Card(host, title="Swap")
            card2.pack(fill="x", pady=(14, 0))
            m2 = Meter(card2.body, self, caption="Swap")
            m2.pack(fill="x", pady=(2, 6))
            m2.set(sw["percent"], text=f"{sw['percent']:.0f}%")
            line(card2.body,
                 f"{sw['used_h']} used / {sw['total_h']} total").pack(anchor="w")

        def _panel_disks(self, parent):
            d = disk_info()
            host = self._scroll_host(parent)
            cols = ("mount", "fstype", "used", "total", "pct")
            tree = ttk.Treeview(host, columns=cols, show="headings", height=8)
            for c, txt, w in (("mount", "Mount", 240), ("fstype", "FS", 90),
                              ("used", "Used", 100), ("total", "Total", 100),
                              ("pct", "Use %", 70)):
                tree.heading(c, text=aura.spaced(txt), anchor="w")
                tree.column(c, width=w, anchor="w")
            for p in d["partitions"]:
                tree.insert("", "end", values=(
                    f"{p['device']} → {p['mountpoint']}", p["fstype"],
                    p["used_h"], p["total_h"], f"{p['percent']}%"))
            tree.pack(fill="x")

            if d.get("smart"):
                card = aura.Card(host, title="SMART health")
                card.pack(fill="x", pady=(14, 0))
                for dev in d["smart"]:
                    line(card.body,
                         f"{dev['device']}: {dev['assessment']} "
                         f"({dev['name']})").pack(anchor="w")
            else:
                aura.Caption(host, (
                    "SMART health is shown when smartctl + pySMART are "
                    "available (Windows, or Linux with smartmontools).")).pack(
                    anchor="w", pady=(10, 0))

            io = d["io"].get("total", {})
            if io:
                aura.Caption(host,
                             f"IO since boot:  read {io.get('read_bytes_h', '')}"
                             f"  ·  write {io.get('write_bytes_h', '')}").pack(
                    anchor="w", pady=(8, 0))

        def _panel_network(self, parent):
            d = network_info()
            host = self._scroll_host(parent)
            for name, nic in d["interfaces"].items():
                card = aura.Card(host, title=name)
                card.pack(fill="x", pady=(0, 12))
                state = "up" if nic["is_up"] else "down"
                speed = nic.get("speed_mbps") or 0
                aura.Caption(card.body, f"link {state}  ·  {speed} Mbps").pack(
                    anchor="w", pady=(0, 4))
                for a in nic["addresses"]:
                    line(card.body,
                         f"{a['family']:<6} {a['address']}").pack(anchor="w")
                io = nic.get("io") or {}
                if io:
                    line(card.body,
                         f"↑ {io.get('bytes_sent_h', '')}   "
                         f"↓ {io.get('bytes_recv_h', '')}",
                         muted=True).pack(anchor="w", pady=(4, 0))
            if not d["interfaces"]:
                line(host, "No network interfaces found.",
                     muted=True).pack(anchor="w")

        def _panel_sensors(self, parent):
            d = sensors()
            host = self._scroll_host(parent)

            card = aura.Card(host, title="Temperatures")
            card.pack(fill="x")
            temps = d["temperatures"]
            if temps:
                for chip, entries in temps.items():
                    for e in entries:
                        cur = e.get("current")
                        line(card.body,
                             f"{chip}/{e.get('label', '')}: {cur} °C").pack(
                            anchor="w")
            else:
                line(card.body, "(no temperature sensors detected)",
                     muted=True).pack(anchor="w")

            fans = d.get("fans") or {}
            if fans:
                fcard = aura.Card(host, title="Fans")
                fcard.pack(fill="x", pady=(14, 0))
                for chip, entries in fans.items():
                    for e in entries:
                        line(fcard.body,
                             f"{chip}/{e.get('label', '')}: "
                             f"{e.get('rpm')} rpm").pack(anchor="w")

            bcard = aura.Card(host, title="Battery")
            bcard.pack(fill="x", pady=(14, 0))
            bat = d.get("battery")
            if bat:
                plugged = ("plugged in" if bat.get("power_plugged")
                           else "on battery")
                line(bcard.body,
                     f"{bat.get('percent')}% ({plugged})").pack(anchor="w")
            else:
                line(bcard.body, "(no battery present)",
                     muted=True).pack(anchor="w")

        def _panel_gpu(self, parent):
            d = gpu_info()
            host = self._scroll_host(parent)
            if not d["gpus"]:
                line(host, (
                    "No GPU detected, or no GPU tooling available. NVIDIA "
                    "cards are read via nvidia-smi; other adapters via WMI "
                    "(Windows) or DRM (Linux)."), muted=True).pack(anchor="w")
                return
            aura.Caption(host, f"Source: {d['source']}").pack(
                anchor="w", pady=(0, 8))
            for g in d["gpus"]:
                card = aura.Card(host, title=g.get("name", "GPU"))
                card.pack(fill="x", pady=(0, 12))
                for label, key in (("Vendor", "vendor"),
                                   ("Driver", "driver_version")):
                    if g.get(key):
                        line(card.body, f"{label}: {g[key]}").pack(anchor="w")
                mem = g.get("memory_total")
                if isinstance(mem, dict):
                    from ._common import human_bytes
                    used = g.get("memory_used")
                    used_str = (f" (used {human_bytes(used['bytes'])})"
                                if isinstance(used, dict) else "")
                    line(card.body,
                         f"Memory: {human_bytes(mem['bytes'])}{used_str}").pack(
                        anchor="w")
                if g.get("utilization_gpu") is not None:
                    line(card.body,
                         f"Utilisation: {g['utilization_gpu']}%").pack(
                        anchor="w")
                if g.get("temperature_gpu") is not None:
                    line(card.body,
                         f"Temperature: {g['temperature_gpu']} °C").pack(
                        anchor="w")

        # ---- live System Monitor
        def _panel_monitor(self, parent):
            monitor_mod.reset()
            host = self._scroll_host(parent)

            card = aura.Card(host, title="Live system monitor")
            card.pack(fill="x")
            cpu_m = Meter(card.body, self, caption="CPU")
            cpu_m.pack(fill="x", pady=3)
            mem_m = Meter(card.body, self, caption="Memory")
            mem_m.pack(fill="x", pady=3)
            self._mon_widgets = {"cpu": cpu_m, "mem": mem_m}

            self._mon_net = line(card.body, "Network: —")
            self._mon_net.pack(anchor="w", pady=(10, 0))
            self._mon_temp = line(card.body, "Temps: —")
            self._mon_temp.pack(anchor="w", pady=(2, 0))

            cores = aura.Card(host, title="Per-core")
            cores.pack(fill="x", pady=(14, 0))
            self._mon_core_meters = []
            try:
                ncores = len(monitor_mod.sample().get("cpu_per_core", []))
            except Exception:
                ncores = 0
            for i in range(ncores):
                m = Meter(cores.body, self, caption=f"Core {i}")
                m.pack(fill="x", pady=2)
                self._mon_core_meters.append(m)

            aura.Caption(host,
                         "Updates automatically about once a second while "
                         "this section is open.").pack(anchor="w", pady=(10, 0))

        def _start_monitor(self):
            if self._mon_running:
                return
            self._mon_running = True
            self._tick_monitor()

        def _stop_monitor(self):
            self._mon_running = False
            if self._mon_job is not None:
                try:
                    self.after_cancel(self._mon_job)
                except Exception:
                    pass
                self._mon_job = None

        def _tick_monitor(self):
            """Poll a sample off-thread, then marshal the update back via after()."""
            if not self._mon_running:
                return

            def work():
                try:
                    snap = monitor_mod.sample()
                except Exception:
                    snap = None
                try:
                    self.after(0, lambda: self._apply_monitor(snap))
                except Exception:
                    pass  # window torn down while sampling

            threading.Thread(target=work, daemon=True).start()

        def _apply_monitor(self, snap):
            if not self._mon_running or snap is None:
                if self._mon_running:
                    self._mon_job = self.after(1000, self._tick_monitor)
                return
            try:
                cpu = self._mon_widgets.get("cpu")
                mem = self._mon_widgets.get("mem")
                if cpu is not None and snap.get("cpu_percent") is not None:
                    cpu.set(snap["cpu_percent"])
                if mem is not None and snap.get("mem_percent") is not None:
                    mem.set(snap["mem_percent"],
                            text=f"{snap['mem_percent']:.0f}%")
                if hasattr(self, "_mon_net"):
                    self._mon_net.configure(
                        text=f"Network:  ↑ {snap.get('net_sent_rate_h', '')}   "
                             f"↓ {snap.get('net_recv_rate_h', '')}")
                if hasattr(self, "_mon_temp"):
                    temps = snap.get("temps") or {}
                    if temps:
                        txt = "  ".join(f"{k}:{v}°C" for k, v in
                                        list(temps.items())[:4])
                    else:
                        txt = "(none)"
                    self._mon_temp.configure(text=f"Temps:  {txt}")
                for i, m in enumerate(getattr(self, "_mon_core_meters", [])):
                    cores = snap.get("cpu_per_core") or []
                    if i < len(cores):
                        m.set(cores[i])
            except Exception:
                pass
            if self._mon_running:
                self._mon_job = self.after(1000, self._tick_monitor)

        # ---- export
        def _export_report(self):
            if self._busy:
                return
            path = filedialog.asksaveasfilename(
                title="Export hardware report",
                initialdir=guiconfig.get_last_export_dir() or None,
                defaultextension=".json",
                filetypes=[("JSON report", "*.json"), ("Text report", "*.txt"),
                           ("All files", "*.*")])
            if not path:
                return
            fmt = "txt" if path.lower().endswith(".txt") else "json"
            self._busy = True
            self.set_status("Exporting…", kind="working")

            def work():
                try:
                    rep = full_report()
                    out = export(path, fmt=fmt, report=rep)
                    err = None
                except HWInfoError as ex:
                    out, err = None, str(ex)
                except Exception as ex:
                    out, err = None, f"Unexpected error: {ex}"
                self.after(0, lambda: finish(out, err))

            def finish(out, err):
                self._busy = False
                if err is not None:
                    self.set_error(err)
                    return
                guiconfig.set_last_export_dir(os.path.dirname(os.path.abspath(out)))
                self.set_success(f"Report written → {out}")
                open_in_file_manager(out)

            threading.Thread(target=work, daemon=True).start()

        # ---- About
        def _about(self):
            win = ctk.CTkToplevel(self)
            win.title("About HardwareInfo")
            win.resizable(False, False)
            frm = ctk.CTkFrame(win, fg_color="transparent")
            frm.pack(fill="both", expand=True, padx=22, pady=18)
            aura.Heading(frm, APP_NAME).pack(anchor="w")
            aura.Caption(frm, f"Version {APP_VERSION}").pack(
                anchor="w", pady=(0, 10))
            ctk.CTkLabel(
                frm, font=aura.font(role="body"), justify="left", anchor="w",
                wraplength=380,
                text="A fast, fully-offline system & hardware inventory — CPU, "
                     "memory, disks, network, GPU and live sensors.\n\n"
                     "100% AI-built, open source, published on QuickOpen.\n"
                     "Nothing is ever uploaded anywhere.").pack(anchor="w")
            aura.Caption(frm,
                         "Licensed under Apache-2.0. Built on psutil and "
                         "CustomTkinter (MIT).").pack(anchor="w", pady=(8, 4))
            aura.AuraButton(frm, "Project page: quickopen.ai", kind="ghost",
                            command=lambda: open_with_default_app(
                                PROJECT_URL)).pack(anchor="w", pady=(4, 8))
            aura.AuraButton(frm, "Close", kind="secondary",
                            command=win.destroy).pack(anchor="e")
            win.transient(self)
            win.grab_set()

        # ---- shutdown
        def _on_close(self):
            self._stop_monitor()
            self.destroy()

    return App


def main():
    """Entry point: build the root window and run.  Degrades on headless hosts.

    Importing this module does nothing; only this function creates a Tk root.
    With no display (e.g. a server) or without customtkinter installed, it
    prints a friendly note and returns 0 instead of raising.
    """
    if os.environ.get("HWINFO_GUI_SELFTEST") == "1":
        # Headless smoke path: exercise build_app() without a display.
        try:
            import tkinter  # noqa: F401
        except Exception as exc:
            print(f"{APP_NAME}: tkinter unavailable ({exc}).")
            return 0
        try:
            build_app()
        except ImportError as exc:
            print(f"{APP_NAME}: GUI deps unavailable ({exc}).")
            return 0
        except Exception as exc:
            print(f"{APP_NAME}: self-test failed to build app: {exc}")
            return 1
        print(f"{APP_NAME}: self-test OK (app class built).")
        return 0

    try:
        import tkinter as tk
    except Exception as exc:  # tkinter missing entirely
        print(f"{APP_NAME}: a graphical environment with tkinter is required "
              f"to run the GUI ({exc}).")
        return 0

    try:
        App = build_app()
        app = App()
    except ImportError as exc:
        print(f"{APP_NAME}: the GUI needs the 'customtkinter' package "
              f"({exc}). Install it with:  pip install customtkinter")
        return 0
    except tk.TclError as exc:
        # Typically "no display name and no $DISPLAY environment variable".
        print(f"{APP_NAME}: no graphical display available — cannot start the "
              f"GUI here ({exc}). This app is intended for the Windows desktop.")
        return 0
    except Exception as exc:
        print(f"{APP_NAME}: could not start the GUI ({exc}).")
        return 1

    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
