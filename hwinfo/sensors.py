"""Hardware sensors: temperatures, fan speeds and battery.

psutil exposes ``sensors_temperatures``/``sensors_fans`` on Linux (and battery
on most platforms) but NOT on Windows.  On Windows we optionally try ``wmi``
(guarded import) via the MSAcpi/OpenHardwareMonitor namespaces.  When nothing is
available :func:`sensors` returns ``{}``-ish empty sections rather than raising.
"""

from __future__ import annotations


def _temps_psutil():
    out = {}
    try:
        import psutil

        fn = getattr(psutil, "sensors_temperatures", None)
        if fn is None:
            return {}
        readings = fn() or {}
        for chip, entries in readings.items():
            out[chip] = [
                {
                    "label": e.label or chip,
                    "current": _num(e.current),
                    "high": _num(e.high),
                    "critical": _num(e.critical),
                }
                for e in entries
            ]
    except Exception:
        return {}
    return out


def _temps_wmi():
    """Windows fallback via WMI (MSAcpi_ThermalZoneTemperature, in deci-Kelvin)."""
    out = {}
    try:
        import wmi  # type: ignore

        conn = wmi.WMI(namespace="root\\wmi")
        zones = []
        for z in conn.MSAcpi_ThermalZoneTemperature():
            # value is tenths of Kelvin
            celsius = (z.CurrentTemperature / 10.0) - 273.15
            zones.append({
                "label": getattr(z, "InstanceName", "ThermalZone"),
                "current": round(celsius, 1),
                "high": None,
                "critical": None,
            })
        if zones:
            out["acpitz"] = zones
    except Exception:
        return {}
    return out


def _fans():
    out = {}
    try:
        import psutil

        fn = getattr(psutil, "sensors_fans", None)
        if fn is None:
            return {}
        readings = fn() or {}
        for chip, entries in readings.items():
            out[chip] = [
                {"label": e.label or chip, "rpm": _num(e.current)}
                for e in entries
            ]
    except Exception:
        return {}
    return out


def _battery():
    try:
        import psutil

        fn = getattr(psutil, "sensors_battery", None)
        if fn is None:
            return None
        bat = fn()
        if bat is None:
            return None
        secs = getattr(bat, "secsleft", None)
        # psutil sentinels: POWER_TIME_UNLIMITED / _UNKNOWN are large negatives
        if secs is not None and secs < 0:
            secs = None
        return {
            "percent": round(float(bat.percent), 1),
            "power_plugged": bool(bat.power_plugged) if bat.power_plugged is not None else None,
            "secsleft": secs,
        }
    except Exception:
        return None


def sensors():
    """Return a JSON-serializable dict of live sensor readings.

    Keys: ``temperatures`` (dict chip -> list), ``fans`` (dict chip -> list) and
    ``battery`` (dict or ``None``).  Any section with no readable hardware is an
    empty dict / ``None`` -- the function never raises for absent sensors.
    """
    temps = _temps_psutil()
    if not temps:
        temps = _temps_wmi()
    return {
        "temperatures": temps,
        "fans": _fans(),
        "battery": _battery(),
    }


def _num(value):
    try:
        if value is None:
            return None
        return round(float(value), 1)
    except (TypeError, ValueError):
        return None
