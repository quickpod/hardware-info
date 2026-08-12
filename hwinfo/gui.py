#!/usr/bin/env python3
r"""HardwareInfo -- a pure-stdlib tkinter GUI on top of the ``hwinfo`` API.

A single main window: a left sidebar of sections (Overview, CPU, Memory, Disks,
Network, Sensors, GPU, System Monitor) and a main panel that swaps to the
selected section.  Every panel reads the tested core collectors (never
re-implements probing) and the live "System Monitor" refreshes on a timer via
``self.after`` -- no blocking the UI thread.  Errors surface in a single inline
status bar (the ``HWInfoError`` message, never a raw traceback).

Design goals baked in here:
  * pure standard-library tkinter/ttk -- NO third-party GUI deps.  Dark mode is
    a ttk-style + palette swap.
  * Importing this module does nothing.  Only :func:`main` builds a root window,
    and it degrades gracefully (prints a message, returns 0) with no display.
  * Frozen-exe safe: bundled assets are resolved via ``sys._MEIPASS`` / the exe
    directory when ``sys.frozen`` is set -- never ``__file__``.

100% AI-built, open source, published on QuickOpen (quickopen.ai).
"""

from __future__ import annotations

import os
import sys
import threading

# NOTE: tkinter is imported lazily inside main()/build_app so that merely
# importing this module (e.g. during packaging or on a headless CI box) never
# fails.

APP_NAME = "HardwareInfo"
APP_VERSION = "1.0.0"
WINDOW_TITLE = "HardwareInfo — by QuickOpen (quickopen.ai)"
PROJECT_URL = "https://quickopen.ai/projects/hardware-info"

# (section_id, label) -- section_id maps to a _panel_<id> builder method.
SECTIONS = [
    ("overview", "Overview"),
    ("cpu", "CPU"),
    ("memory", "Memory"),
    ("disks", "Disks"),
    ("network", "Network"),
    ("sensors", "Sensors"),
    ("gpu", "GPU"),
    ("monitor", "System Monitor"),
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

# ---- colour palettes (mirror the QuickOpen palette) -------------------------
PALETTES = {
    "light": {
        "bg": "#f5f7fa", "surface": "#ffffff", "text": "#141820",
        "muted": "#5b6472", "primary": "#2f5fe0", "primary_hi": "#2450c8",
        "entry": "#ffffff", "border": "#d5dae2", "sel": "#2f5fe0",
        "sel_fg": "#ffffff", "trough": "#e2e7ef", "ok": "#1f7a3d",
        "warn": "#b8860b", "err": "#c0392b",
    },
    "dark": {
        "bg": "#0f1115", "surface": "#1a1e24", "text": "#f1f3f7",
        "muted": "#9aa4b2", "primary": "#5b86f7", "primary_hi": "#7098ff",
        "entry": "#1a1e24", "border": "#2a2f38", "sel": "#5b86f7",
        "sel_fg": "#0f1115", "trough": "#2a2f38", "ok": "#5bd68a",
        "warn": "#e0b341", "err": "#ff6b5e",
    },
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
# The app (built lazily; tkinter imported only inside build_app/main)
# ---------------------------------------------------------------------------
def build_app():
    """Construct and return the App class bound to a live tkinter import.

    Kept inside a function so this module imports cleanly without a display.
    """
    import tkinter as tk
    from tkinter import ttk, filedialog

    from . import guiconfig
    from .errors import HWInfoError
    from . import (
        overview, cpu_info, memory_info, disk_info,
        network_info, sensors, gpu_info,
    )
    from . import monitor as monitor_mod
    from .report import full_report, export

    FONT = "Segoe UI"
    MONO = "Consolas"

    # -- small reusable widgets ------------------------------------------

    class KeyValue(ttk.Frame):
        """A tidy two-column list of (label, value) rows."""

        def __init__(self, master, app):
            super().__init__(master, style="Card.TFrame", padding=12)
            self.app = app
            self._row = 0
            self.columnconfigure(1, weight=1)

        def add(self, label, value, value_style="Value.TLabel"):
            ttk.Label(self, text=label, style="KeyMuted.TLabel").grid(
                row=self._row, column=0, sticky="w", padx=(0, 16), pady=2)
            ttk.Label(self, text=str(value), style=value_style, wraplength=560,
                      justify="left").grid(row=self._row, column=1, sticky="w", pady=2)
            self._row += 1

        def add_heading(self, text):
            ttk.Label(self, text=text, style="CardHead.TLabel").grid(
                row=self._row, column=0, columnspan=2, sticky="w",
                pady=(10 if self._row else 0, 4))
            self._row += 1

    class Meter(ttk.Frame):
        """A labelled percentage bar drawn on a Canvas (theme-aware)."""

        def __init__(self, master, app, caption="", width=260):
            super().__init__(master, style="TFrame")
            self.app = app
            self._w = width
            self.cap = ttk.Label(self, text=caption, style="Mono.TLabel", width=14,
                                 anchor="w")
            self.cap.pack(side="left")
            self.canvas = tk.Canvas(self, height=16, width=width,
                                    highlightthickness=0, bd=0)
            self.canvas.pack(side="left", fill="x", expand=True, padx=(6, 6))
            self.val = ttk.Label(self, text="—", style="Mono.TLabel", width=6,
                                 anchor="e")
            self.val.pack(side="left")
            app.track(self.canvas, "canvas")
            self._pct = 0.0

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
            p = self.app._pal()
            c = self.canvas
            c.delete("all")
            w = c.winfo_width() or self._w
            h = int(c["height"])
            c.configure(bg=p["trough"])
            fill = p["ok"] if self._pct < 75 else (p["warn"] if self._pct < 90
                                                   else p["err"])
            fw = int(w * self._pct / 100.0)
            if fw > 0:
                c.create_rectangle(0, 0, fw, h, fill=fill, width=0)

    # -- the main window --------------------------------------------------

    class App(tk.Tk):
        def __init__(self):
            super().__init__()
            self.title(WINDOW_TITLE)
            self.geometry("1040x680")
            self.minsize(860, 560)

            self.theme = guiconfig.get_theme()
            self._panels = {}          # section_id -> built frame (lazy)
            self._current = None
            self._current_id = None
            self._tracked = []         # (tk_widget, role) for manual re-theming
            self._img_refs = []        # keep PhotoImage refs alive
            self._busy = False
            self._mon_running = False
            self._mon_job = None
            self._mon_widgets = {}     # live monitor widget handles
            self._core_meters = []     # CPU per-core meters

            self._set_icon()
            self._build_menu()
            self._build_layout()
            self._apply_theme()
            self.protocol("WM_DELETE_WINDOW", self._on_close)
            self.after(50, self._select_first)

        # ---- assets / icon
        def _set_icon(self):
            try:
                ico = asset_path("hardware-info.ico")
                if ico:
                    self.iconbitmap(ico)
                    return
            except Exception:
                pass
            try:
                png = asset_path("hardware-info.png")
                if png:
                    img = tk.PhotoImage(file=png)
                    self._img_refs.append(img)
                    self.iconphoto(True, img)
            except Exception:
                pass  # icon is cosmetic; never block launch

        # ---- theming
        def track(self, widget, role):
            self._tracked.append((widget, role))

        def _pal(self):
            return PALETTES[self.theme]

        def _apply_theme(self):
            p = self._pal()
            style = ttk.Style(self)
            try:
                style.theme_use("clam")
            except Exception:
                pass
            self.configure(bg=p["bg"])
            style.configure(".", background=p["bg"], foreground=p["text"],
                            fieldbackground=p["entry"], bordercolor=p["border"],
                            font=(FONT, 10))
            style.configure("TFrame", background=p["bg"])
            style.configure("Sidebar.TFrame", background=p["surface"])
            style.configure("Card.TFrame", background=p["surface"])
            style.configure("TLabel", background=p["bg"], foreground=p["text"])
            style.configure("Muted.TLabel", background=p["bg"], foreground=p["muted"])
            style.configure("Header.TLabel", background=p["bg"], foreground=p["text"],
                            font=(FONT, 15, "bold"))
            style.configure("Sub.TLabel", background=p["bg"], foreground=p["muted"],
                            font=(FONT, 10))
            style.configure("Brand.TLabel", background=p["surface"],
                            foreground=p["text"], font=(FONT, 12, "bold"))
            style.configure("Status.TLabel", background=p["surface"],
                            foreground=p["muted"])
            style.configure("Value.TLabel", background=p["surface"],
                            foreground=p["text"])
            style.configure("KeyMuted.TLabel", background=p["surface"],
                            foreground=p["muted"])
            style.configure("CardHead.TLabel", background=p["surface"],
                            foreground=p["primary"], font=(FONT, 11, "bold"))
            style.configure("Mono.TLabel", background=p["bg"], foreground=p["text"],
                            font=(MONO, 10))
            style.configure("MonoCard.TLabel", background=p["surface"],
                            foreground=p["text"], font=(MONO, 10))
            style.configure("Ok.TLabel", background=p["surface"], foreground=p["ok"])
            style.configure("Err.TLabel", background=p["surface"], foreground=p["err"])
            style.configure("TButton", background=p["surface"], foreground=p["text"],
                            bordercolor=p["border"], focuscolor=p["surface"],
                            padding=(10, 5))
            style.map("TButton",
                      background=[("active", p["trough"]), ("disabled", p["bg"])],
                      foreground=[("disabled", p["muted"])])
            style.configure("Accent.TButton", background=p["primary"],
                            foreground="#ffffff", padding=(12, 6))
            style.map("Accent.TButton",
                      background=[("active", p["primary_hi"]),
                                  ("disabled", p["border"])],
                      foreground=[("disabled", p["muted"])])
            style.configure("Toggle.TButton", background=p["surface"],
                            foreground=p["text"], padding=(8, 4))
            style.configure("Treeview", background=p["surface"],
                            fieldbackground=p["surface"], foreground=p["text"],
                            bordercolor=p["border"], rowheight=26)
            style.map("Treeview", background=[("selected", p["primary"])],
                      foreground=[("selected", p["sel_fg"])])
            style.configure("Sidebar.Treeview", background=p["surface"],
                            fieldbackground=p["surface"], borderwidth=0)
            style.configure("Sidebar.Treeview.Heading", background=p["surface"])
            style.configure("TScrollbar", background=p["surface"],
                            troughcolor=p["bg"], bordercolor=p["border"],
                            arrowcolor=p["text"])
            style.configure("TSeparator", background=p["border"])
            style.configure("TNotebook", background=p["bg"], bordercolor=p["border"])
            style.configure("TNotebook.Tab", background=p["surface"],
                            foreground=p["muted"], padding=(12, 6))
            style.map("TNotebook.Tab",
                      background=[("selected", p["bg"])],
                      foreground=[("selected", p["text"])])

            # manually re-colour raw tk widgets (Text / Canvas / Treeview data)
            for widget, role in list(self._tracked):
                try:
                    if role == "text":
                        widget.configure(bg=p["surface"], fg=p["text"],
                                         insertbackground=p["text"],
                                         selectbackground=p["primary"],
                                         selectforeground=p["sel_fg"],
                                         highlightthickness=1,
                                         highlightbackground=p["border"],
                                         borderwidth=0, font=(MONO, 10))
                    elif role == "canvas":
                        widget.configure(bg=p["trough"], highlightthickness=0)
                except Exception:
                    pass
            for meter in list(self._core_meters):
                try:
                    meter._redraw()
                except Exception:
                    pass
            for key in ("cpu", "mem", "net"):
                m = self._mon_widgets.get(key)
                if m is not None:
                    try:
                        m._redraw()
                    except Exception:
                        pass

        def toggle_theme(self):
            self.theme = "dark" if self.theme == "light" else "light"
            guiconfig.set_theme(self.theme)
            self._apply_theme()
            self._theme_btn.configure(
                text="☀ Light mode" if self.theme == "dark" else "🌙 Dark mode")

        # ---- menu
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
            viewm.add_command(label="Toggle dark mode", command=self.toggle_theme)
            bar.add_cascade(label="View", menu=viewm)

            helpm = tk.Menu(bar, tearoff=0)
            helpm.add_command(label="About", command=self._about)
            helpm.add_command(label="Open project page (quickopen.ai)",
                              command=lambda: open_with_default_app(PROJECT_URL))
            bar.add_cascade(label="Help", menu=helpm)
            self.configure(menu=bar)
            self.bind_all("<Control-e>", lambda e: self._export_report())
            self.bind_all("<F5>", lambda e: self._refresh_current())

        # ---- layout
        def _build_layout(self):
            top = ttk.Frame(self, style="Sidebar.TFrame", padding=(12, 8))
            top.pack(fill="x", side="top")
            ttk.Label(top, text="HardwareInfo", style="Brand.TLabel").pack(side="left")
            ttk.Label(top, style="Status.TLabel",
                      text="  offline · open source · by QuickOpen").pack(side="left")
            self._theme_btn = ttk.Button(
                top, style="Toggle.TButton", command=self.toggle_theme,
                text="☀ Light mode" if self.theme == "dark" else "🌙 Dark mode")
            self._theme_btn.pack(side="right")
            ttk.Button(top, text="Export report…", style="Accent.TButton",
                       command=self._export_report).pack(side="right", padx=8)

            body = ttk.Frame(self, style="TFrame")
            body.pack(fill="both", expand=True)

            side = ttk.Frame(body, style="Sidebar.TFrame", width=200)
            side.pack(side="left", fill="y")
            side.pack_propagate(False)
            self.nav = ttk.Treeview(side, show="tree", selectmode="browse",
                                    style="Sidebar.Treeview")
            self.nav.pack(fill="both", expand=True, padx=6, pady=6)
            self._nav_ids = {}
            for sid, label in SECTIONS:
                iid = self.nav.insert("", "end", text="  " + label)
                self._nav_ids[iid] = sid
            self.nav.bind("<<TreeviewSelect>>", self._on_nav_select)

            main = ttk.Frame(body, style="TFrame", padding=(16, 12))
            main.pack(side="left", fill="both", expand=True)

            head = ttk.Frame(main, style="TFrame")
            head.pack(fill="x")
            self.title_lbl = ttk.Label(head, text="Overview", style="Header.TLabel")
            self.title_lbl.pack(anchor="w")
            self.desc_lbl = ttk.Label(head, text="", style="Sub.TLabel",
                                      wraplength=720, justify="left")
            self.desc_lbl.pack(anchor="w", pady=(2, 8))
            ttk.Separator(main).pack(fill="x")

            self.container = ttk.Frame(main, style="TFrame")
            self.container.pack(fill="both", expand=True, pady=(10, 8))

            bar = ttk.Frame(self, style="Sidebar.TFrame", padding=(12, 6))
            bar.pack(fill="x", side="bottom")
            self.status_lbl = ttk.Label(bar, text="Ready", style="Status.TLabel",
                                        width=16, anchor="w")
            self.status_lbl.pack(side="left")
            self.result_lbl = ttk.Label(bar, text="", style="Status.TLabel",
                                        anchor="w", wraplength=720, justify="left")
            self.result_lbl.pack(side="left", fill="x", expand=True, padx=8)

        def _select_first(self):
            for iid in self._nav_ids:
                self.nav.selection_set(iid)
                self.nav.see(iid)
                break

        def _on_nav_select(self, _e=None):
            sel = self.nav.selection()
            if not sel:
                return
            sid = self._nav_ids.get(sel[0])
            if sid:
                self._show_section(sid)

        def _show_section(self, section_id):
            # leaving the monitor tab? stop the timer.
            if self._current_id == "monitor" and section_id != "monitor":
                self._stop_monitor()

            if self._current is not None:
                self._current.pack_forget()
            panel = self._panels.get(section_id)
            rebuild = panel is None
            if rebuild:
                panel = ttk.Frame(self.container, style="TFrame")
                self._panels[section_id] = panel
            panel.pack(fill="both", expand=True)
            self._current = panel
            self._current_id = section_id

            label = dict(SECTIONS).get(section_id, section_id)
            self.title_lbl.configure(text=label)
            self.desc_lbl.configure(text=SECTION_DESCRIPTIONS.get(section_id, ""))
            self._clear_result()

            # (re)build content each time so data is fresh on revisit
            for child in panel.winfo_children():
                child.destroy()
            builder = getattr(self, "_panel_" + section_id, None)
            try:
                if builder:
                    builder(panel)
                else:
                    ttk.Label(panel, text="Not implemented.").pack()
            except HWInfoError as exc:
                self._show_error(str(exc))
            except Exception as exc:  # never leak a traceback
                self._show_error(f"Could not read {label}: {exc}")
            self._apply_theme()
            if section_id == "monitor":
                self._start_monitor()

        def _refresh_current(self):
            if self._current_id:
                self._show_section(self._current_id)

        # ---- scrollable helper
        def _scroll_host(self, parent):
            """Return an inner frame inside a vertical-scrolling canvas."""
            canvas = tk.Canvas(parent, highlightthickness=0, bd=0)
            sb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
            inner = ttk.Frame(canvas, style="TFrame")
            inner.bind("<Configure>",
                       lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
            win = canvas.create_window((0, 0), window=inner, anchor="nw")
            canvas.bind("<Configure>",
                        lambda e: canvas.itemconfigure(win, width=e.width))
            canvas.configure(yscrollcommand=sb.set)
            sb.pack(side="right", fill="y")
            canvas.pack(side="left", fill="both", expand=True)
            canvas.configure(bg=self._pal()["bg"])

            def _wheel(e):
                canvas.yview_scroll(int(-1 * (e.delta / 120)) or (-1 if e.num == 4
                                    else 1), "units")
            canvas.bind_all("<MouseWheel>", _wheel)
            return inner

        # ---- status bar helpers
        def _set_status(self, text, kind="idle"):
            p = self._pal()
            color = {"working": p["primary"], "ok": p["ok"], "err": p["err"]}.get(
                kind, p["muted"])
            self.status_lbl.configure(text=text, foreground=color)

        def _clear_result(self):
            self.result_lbl.configure(text="")
            self._set_status("Ready")

        def _show_error(self, message):
            self.result_lbl.configure(text="✕ " + message,
                                      foreground=self._pal()["err"])
            self._set_status("error", kind="err")

        def _show_ok(self, message):
            self.result_lbl.configure(text="✓ " + message,
                                      foreground=self._pal()["ok"])
            self._set_status("done", kind="ok")

        # =====================================================================
        # PANELS
        # =====================================================================
        def _panel_overview(self, parent):
            d = overview()
            host = self._scroll_host(parent)
            kv = KeyValue(host, self)
            kv.pack(fill="x", anchor="n")
            os_ = d["os"]
            py = d["python"]
            kv.add_heading("System")
            kv.add("Summary", d["summary"])
            kv.add("Hostname", d["hostname"])
            kv.add("Operating system", f"{os_['system']} {os_['release']}")
            kv.add("Version", os_["version"])
            kv.add("Platform", os_["platform"])
            kv.add("Machine", f"{d['machine']} ({d['architecture']})")
            kv.add("Processor", d["processor"] or "—")
            kv.add("Uptime", d["uptime"])
            kv.add_heading("Python runtime")
            kv.add("Version", f"{py['implementation']} {py['version']}")
            kv.add("Compiler", py["compiler"])
            kv.add("Executable", py["executable"])

        def _panel_cpu(self, parent):
            d = cpu_info(per_core_interval=0.0)
            host = self._scroll_host(parent)
            kv = KeyValue(host, self)
            kv.pack(fill="x")
            freq = d["frequency"]
            kv.add("Model", d["model"])
            kv.add("Architecture", d["architecture"])
            kv.add("Cores", f"{d['cores_physical']} physical / "
                            f"{d['cores_logical']} logical")
            kv.add("Frequency", f"{freq['current']} (max {freq['max']})")
            kv.add("Total load", f"{d['percent_total']}%")

            bars = ttk.Frame(host, style="Card.TFrame", padding=12)
            bars.pack(fill="x", pady=(10, 0))
            ttk.Label(bars, text="Per-core utilisation", style="CardHead.TLabel"
                      ).pack(anchor="w", pady=(0, 6))
            self._core_meters = []
            for i, pct in enumerate(d["percent_per_core"]):
                m = Meter(bars, self, caption=f"Core {i}")
                m.pack(fill="x", pady=1)
                m.set(pct)
                self._core_meters.append(m)
            if not d["percent_per_core"]:
                ttk.Label(bars, text="(per-core data unavailable)",
                          style="MonoCard.TLabel").pack(anchor="w")

        def _panel_memory(self, parent):
            d = memory_info()
            host = self._scroll_host(parent)
            vm, sw = d["virtual"], d["swap"]
            card = ttk.Frame(host, style="Card.TFrame", padding=12)
            card.pack(fill="x")
            ttk.Label(card, text="Physical memory (RAM)", style="CardHead.TLabel"
                      ).pack(anchor="w")
            m = Meter(card, self, caption="RAM")
            m.pack(fill="x", pady=6)
            m.set(vm["percent"], text=f"{vm['percent']:.0f}%")
            ttk.Label(card, style="MonoCard.TLabel",
                      text=f"{vm['used_h']} used / {vm['total_h']} total  "
                           f"({vm['available_h']} available)").pack(anchor="w")

            ttk.Label(card, text="Swap", style="CardHead.TLabel").pack(
                anchor="w", pady=(12, 0))
            m2 = Meter(card, self, caption="Swap")
            m2.pack(fill="x", pady=6)
            m2.set(sw["percent"], text=f"{sw['percent']:.0f}%")
            ttk.Label(card, style="MonoCard.TLabel",
                      text=f"{sw['used_h']} used / {sw['total_h']} total").pack(
                anchor="w")

        def _panel_disks(self, parent):
            d = disk_info()
            host = self._scroll_host(parent)
            cols = ("mount", "fstype", "used", "total", "pct")
            tree = ttk.Treeview(host, columns=cols, show="headings", height=8)
            for c, txt, w in (("mount", "Mount", 160), ("fstype", "FS", 80),
                              ("used", "Used", 100), ("total", "Total", 100),
                              ("pct", "Use %", 70)):
                tree.heading(c, text=txt)
                tree.column(c, width=w, anchor="w")
            for p in d["partitions"]:
                tree.insert("", "end", values=(
                    f"{p['device']} → {p['mountpoint']}", p["fstype"],
                    p["used_h"], p["total_h"], f"{p['percent']}%"))
            tree.pack(fill="x")

            if d.get("smart"):
                card = ttk.Frame(host, style="Card.TFrame", padding=12)
                card.pack(fill="x", pady=(10, 0))
                ttk.Label(card, text="SMART health", style="CardHead.TLabel").pack(
                    anchor="w")
                for dev in d["smart"]:
                    ttk.Label(card, style="MonoCard.TLabel",
                              text=f"{dev['device']}: {dev['assessment']} "
                                   f"({dev['name']})").pack(anchor="w")
            else:
                ttk.Label(host, style="Muted.TLabel", text=(
                    "SMART health is shown when smartctl + pySMART are available "
                    "(Windows, or Linux with smartmontools).")).pack(
                    anchor="w", pady=(8, 0))

            io = d["io"].get("total", {})
            if io:
                ttk.Label(host, style="Muted.TLabel",
                          text=f"IO since boot:  read {io.get('read_bytes_h', '')}  "
                               f"·  write {io.get('write_bytes_h', '')}").pack(
                    anchor="w", pady=(8, 0))

        def _panel_network(self, parent):
            d = network_info()
            host = self._scroll_host(parent)
            for name, nic in d["interfaces"].items():
                card = ttk.Frame(host, style="Card.TFrame", padding=12)
                card.pack(fill="x", pady=4)
                state = "up" if nic["is_up"] else "down"
                speed = nic.get("speed_mbps") or 0
                ttk.Label(card, text=f"{name}   [{state}]   {speed} Mbps",
                          style="CardHead.TLabel").pack(anchor="w")
                for a in nic["addresses"]:
                    ttk.Label(card, style="MonoCard.TLabel",
                              text=f"  {a['family']:<5} {a['address']}").pack(
                        anchor="w")
                io = nic.get("io") or {}
                if io:
                    ttk.Label(card, style="MonoCard.TLabel",
                              text=f"  ↑ {io.get('bytes_sent_h', '')}   "
                                   f"↓ {io.get('bytes_recv_h', '')}").pack(anchor="w")
            if not d["interfaces"]:
                ttk.Label(host, text="No network interfaces found.",
                          style="Muted.TLabel").pack(anchor="w")

        def _panel_sensors(self, parent):
            d = sensors()
            host = self._scroll_host(parent)
            card = ttk.Frame(host, style="Card.TFrame", padding=12)
            card.pack(fill="x")
            temps = d["temperatures"]
            ttk.Label(card, text="Temperatures", style="CardHead.TLabel").pack(
                anchor="w")
            if temps:
                for chip, entries in temps.items():
                    for e in entries:
                        cur = e.get("current")
                        ttk.Label(card, style="MonoCard.TLabel",
                                  text=f"  {chip}/{e.get('label', '')}: "
                                       f"{cur} °C").pack(anchor="w")
            else:
                ttk.Label(card, text="  (no temperature sensors detected)",
                          style="MonoCard.TLabel").pack(anchor="w")

            fans = d.get("fans") or {}
            if fans:
                ttk.Label(card, text="Fans", style="CardHead.TLabel").pack(
                    anchor="w", pady=(10, 0))
                for chip, entries in fans.items():
                    for e in entries:
                        ttk.Label(card, style="MonoCard.TLabel",
                                  text=f"  {chip}/{e.get('label', '')}: "
                                       f"{e.get('rpm')} rpm").pack(anchor="w")

            bat = d.get("battery")
            ttk.Label(card, text="Battery", style="CardHead.TLabel").pack(
                anchor="w", pady=(10, 0))
            if bat:
                plugged = "plugged in" if bat.get("power_plugged") else "on battery"
                ttk.Label(card, style="MonoCard.TLabel",
                          text=f"  {bat.get('percent')}% ({plugged})").pack(anchor="w")
            else:
                ttk.Label(card, text="  (no battery present)",
                          style="MonoCard.TLabel").pack(anchor="w")

        def _panel_gpu(self, parent):
            d = gpu_info()
            host = self._scroll_host(parent)
            if not d["gpus"]:
                ttk.Label(host, style="Muted.TLabel", text=(
                    "No GPU detected, or no GPU tooling available. NVIDIA cards are "
                    "read via nvidia-smi; other adapters via WMI (Windows) or DRM "
                    "(Linux).")).pack(anchor="w")
                return
            ttk.Label(host, style="Muted.TLabel",
                      text=f"Source: {d['source']}").pack(anchor="w", pady=(0, 6))
            for g in d["gpus"]:
                card = ttk.Frame(host, style="Card.TFrame", padding=12)
                card.pack(fill="x", pady=4)
                ttk.Label(card, text=g.get("name", "GPU"),
                          style="CardHead.TLabel").pack(anchor="w")
                for label, key in (("Vendor", "vendor"),
                                   ("Driver", "driver_version")):
                    if g.get(key):
                        ttk.Label(card, style="MonoCard.TLabel",
                                  text=f"  {label}: {g[key]}").pack(anchor="w")
                mem = g.get("memory_total")
                if isinstance(mem, dict):
                    from ._common import human_bytes
                    used = g.get("memory_used")
                    used_str = (f" (used {human_bytes(used['bytes'])})"
                                if isinstance(used, dict) else "")
                    ttk.Label(card, style="MonoCard.TLabel",
                              text=f"  Memory: {human_bytes(mem['bytes'])}{used_str}"
                              ).pack(anchor="w")
                if g.get("utilization_gpu") is not None:
                    ttk.Label(card, style="MonoCard.TLabel",
                              text=f"  Utilisation: {g['utilization_gpu']}%").pack(
                        anchor="w")
                if g.get("temperature_gpu") is not None:
                    ttk.Label(card, style="MonoCard.TLabel",
                              text=f"  Temperature: {g['temperature_gpu']} °C").pack(
                        anchor="w")

        # ---- live System Monitor
        def _panel_monitor(self, parent):
            monitor_mod.reset()
            card = ttk.Frame(parent, style="Card.TFrame", padding=14)
            card.pack(fill="x")
            ttk.Label(card, text="Live system monitor", style="CardHead.TLabel"
                      ).pack(anchor="w", pady=(0, 8))

            cpu_m = Meter(card, self, caption="CPU")
            cpu_m.pack(fill="x", pady=3)
            mem_m = Meter(card, self, caption="Memory")
            mem_m.pack(fill="x", pady=3)
            self._mon_widgets = {"cpu": cpu_m, "mem": mem_m}

            self._mon_net = ttk.Label(card, style="MonoCard.TLabel",
                                      text="Network: —")
            self._mon_net.pack(anchor="w", pady=(8, 0))
            self._mon_temp = ttk.Label(card, style="MonoCard.TLabel",
                                       text="Temps: —")
            self._mon_temp.pack(anchor="w", pady=(2, 0))

            cores = ttk.Frame(card, style="Card.TFrame")
            cores.pack(fill="x", pady=(10, 0))
            ttk.Label(cores, text="Per-core", style="CardHead.TLabel").pack(anchor="w")
            self._mon_core_meters = []
            try:
                ncores = len(monitor_mod.sample().get("cpu_per_core", []))
            except Exception:
                ncores = 0
            for i in range(ncores):
                m = Meter(cores, self, caption=f"Core {i}")
                m.pack(fill="x", pady=1)
                self._mon_core_meters.append(m)

            ttk.Label(parent, style="Muted.TLabel",
                      text="Updates automatically about once a second while this "
                           "tab is open.").pack(anchor="w", pady=(8, 0))

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
                self.after(0, lambda: self._apply_monitor(snap))

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
            self._set_status("Exporting…", kind="working")

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
                    self._show_error(err)
                    return
                guiconfig.set_last_export_dir(os.path.dirname(os.path.abspath(out)))
                self._show_ok(f"Report written → {out}")
                open_in_file_manager(out)

            threading.Thread(target=work, daemon=True).start()

        # ---- About
        def _about(self):
            win = tk.Toplevel(self)
            win.title("About HardwareInfo")
            win.configure(bg=self._pal()["bg"])
            win.resizable(False, False)
            frm = ttk.Frame(win, style="TFrame", padding=18)
            frm.pack(fill="both", expand=True)
            ttk.Label(frm, text="HardwareInfo", style="Header.TLabel").pack(anchor="w")
            ttk.Label(frm, text=f"Version {APP_VERSION}",
                      style="Sub.TLabel").pack(anchor="w", pady=(0, 8))
            ttk.Label(frm, style="TLabel", justify="left", wraplength=380,
                      text="A fast, fully-offline system & hardware inventory — CPU, "
                           "memory, disks, network, GPU and live sensors.\n\n"
                           "100% AI-built, open source, published on QuickOpen.\n"
                           "Nothing is ever uploaded anywhere.").pack(anchor="w")
            ttk.Label(frm, style="Sub.TLabel", justify="left", wraplength=380,
                      text="Licensed under Apache-2.0. Built on psutil.").pack(
                anchor="w", pady=(8, 4))
            link = ttk.Label(frm, text="Project page: quickopen.ai",
                             style="Ok.TLabel", cursor="hand2")
            link.pack(anchor="w", pady=(4, 10))
            link.bind("<Button-1>", lambda e: open_with_default_app(PROJECT_URL))
            ttk.Button(frm, text="Close", command=win.destroy).pack(anchor="e")
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
    With no display (e.g. a server), it prints a friendly note and returns 0
    instead of raising.
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
