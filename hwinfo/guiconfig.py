r"""Tiny JSON-backed config for the HardwareInfo GUI.

Stores just the chosen theme ("light"/"dark") and the last export directory, and
never raises.  On Windows the file lives at
``%LOCALAPPDATA%\HardwareInfo\config.json``; elsewhere it falls back to
``~/.hardwareinfo/config.json``.  Every function is defensive -- a corrupt or
unreadable config must never stop the app from starting.
"""

from __future__ import annotations

import json
import os

APP_DIRNAME = "HardwareInfo"
CONFIG_NAME = "config.json"
VALID_THEMES = ("light", "dark")


def config_dir():
    r"""Directory that holds the config file (created on demand).

    ``%LOCALAPPDATA%\HardwareInfo`` on Windows, ``~/.hardwareinfo`` otherwise.
    """
    local = os.environ.get("LOCALAPPDATA")
    if local and os.name == "nt":
        return os.path.join(local, APP_DIRNAME)
    return os.path.join(os.path.expanduser("~"), "." + APP_DIRNAME.lower())


def config_path():
    return os.path.join(config_dir(), CONFIG_NAME)


def _defaults():
    return {"theme": "dark", "last_export_dir": ""}


def load():
    """Return the config dict, always with ``theme`` and ``last_export_dir``."""
    cfg = _defaults()
    try:
        with open(config_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            theme = data.get("theme")
            if theme in VALID_THEMES:
                cfg["theme"] = theme
            last = data.get("last_export_dir")
            if isinstance(last, str):
                cfg["last_export_dir"] = last
    except Exception:
        pass  # missing/corrupt -> defaults; never fatal
    return cfg


def save(cfg):
    """Persist *cfg* (best-effort; failures are swallowed)."""
    try:
        os.makedirs(config_dir(), exist_ok=True)
        clean = {
            "theme": cfg.get("theme") if cfg.get("theme") in VALID_THEMES else "dark",
            "last_export_dir": cfg.get("last_export_dir")
            if isinstance(cfg.get("last_export_dir"), str) else "",
        }
        tmp = config_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(clean, fh, indent=2)
        os.replace(tmp, config_path())
    except Exception:
        pass


def get_theme():
    return load().get("theme", "dark")


def set_theme(theme):
    if theme not in VALID_THEMES:
        return
    cfg = load()
    cfg["theme"] = theme
    save(cfg)


def get_last_export_dir():
    return load().get("last_export_dir", "")


def set_last_export_dir(path):
    if not isinstance(path, str):
        return
    cfg = load()
    cfg["last_export_dir"] = path
    save(cfg)
