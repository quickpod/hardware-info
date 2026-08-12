"""Structure/type tests for the hwinfo collectors.

These run headless on Linux (psutil works there).  We deliberately never assert
exact hardware values -- those vary by machine -- only that each collector
returns a JSON-serializable dict with the expected shape, and that the failure
path raises a clean ``HWInfoError``.
"""

import json

import pytest

import hwinfo
from hwinfo import (
    HWInfoError, overview, cpu_info, memory_info, disk_info,
    network_info, sensors, gpu_info, full_report, export,
)
from hwinfo import monitor


def _roundtrip(obj):
    """json.dumps must succeed and re-parse to an equal structure."""
    text = json.dumps(obj)
    assert json.loads(text) == obj
    return text


# --- overview ---------------------------------------------------------------

def test_overview_shape():
    d = overview()
    assert isinstance(d, dict)
    for key in ("hostname", "os", "machine", "architecture", "processor",
                "python", "boot_time", "uptime_seconds", "uptime", "summary"):
        assert key in d
    assert isinstance(d["os"], dict)
    assert {"system", "release", "version", "platform"} <= set(d["os"])
    assert isinstance(d["python"], dict)
    assert isinstance(d["summary"], str) and d["summary"]
    _roundtrip(d)


# --- cpu --------------------------------------------------------------------

def test_cpu_shape():
    d = cpu_info()
    assert isinstance(d, dict)
    for key in ("model", "architecture", "cores_physical", "cores_logical",
                "frequency", "percent_total", "percent_per_core", "stats"):
        assert key in d
    assert isinstance(d["frequency"], dict)
    assert isinstance(d["percent_per_core"], list)
    for v in d["percent_per_core"]:
        assert isinstance(v, (int, float))
    assert isinstance(d["model"], str) and d["model"]
    _roundtrip(d)


# --- memory -----------------------------------------------------------------

def test_memory_shape():
    d = memory_info()
    assert set(d) == {"virtual", "swap"}
    vm = d["virtual"]
    for key in ("total", "available", "used", "free", "percent",
                "total_h", "used_h"):
        assert key in vm
    assert isinstance(vm["total"], int) and vm["total"] > 0
    assert 0.0 <= vm["percent"] <= 100.0
    assert isinstance(vm["total_h"], str)
    _roundtrip(d)


# --- disks ------------------------------------------------------------------

def test_disks_shape():
    d = disk_info()
    assert "partitions" in d and "io" in d
    assert isinstance(d["partitions"], list)
    for p in d["partitions"]:
        for key in ("device", "mountpoint", "fstype", "total", "used",
                    "free", "percent", "total_h"):
            assert key in p
        assert isinstance(p["total"], int)
    # smart is optional -> when present it must be a list
    if "smart" in d:
        assert isinstance(d["smart"], list)
    _roundtrip(d)


# --- network ----------------------------------------------------------------

def test_network_shape():
    d = network_info()
    assert "interfaces" in d and "io_total" in d
    assert isinstance(d["interfaces"], dict)
    for name, nic in d["interfaces"].items():
        assert isinstance(name, str)
        assert isinstance(nic["addresses"], list)
        for a in nic["addresses"]:
            assert {"family", "address"} <= set(a)
    _roundtrip(d)


# --- sensors (may be empty; must not raise) ---------------------------------

def test_sensors_shape():
    d = sensors()
    assert isinstance(d, dict)
    assert set(d) == {"temperatures", "fans", "battery"}
    assert isinstance(d["temperatures"], dict)
    assert isinstance(d["fans"], dict)
    assert d["battery"] is None or isinstance(d["battery"], dict)
    _roundtrip(d)


# --- gpu (best-effort; may be empty; must not raise) ------------------------

def test_gpu_shape():
    d = gpu_info()
    assert isinstance(d, dict)
    assert "gpus" in d and "source" in d
    assert isinstance(d["gpus"], list)
    for g in d["gpus"]:
        assert "name" in g
    _roundtrip(d)


# --- monitor ----------------------------------------------------------------

def test_monitor_sample_shape():
    monitor.reset()
    snap = monitor.sample()
    for key in ("time", "cpu_percent", "cpu_per_core", "mem_percent",
                "net_sent_rate", "net_recv_rate", "temps"):
        assert key in snap
    # first sample => zero net rates (no prior baseline)
    assert snap["net_sent_rate"] == 0.0
    assert snap["net_recv_rate"] == 0.0
    assert isinstance(snap["cpu_per_core"], list)
    snap2 = monitor.sample()
    assert snap2["net_sent_rate"] >= 0.0
    _roundtrip(snap)


# --- full report ------------------------------------------------------------

def test_full_report_shape():
    rep = full_report()
    for key in ("generated_at", "overview", "cpu", "memory", "disks",
                "network", "sensors", "gpu"):
        assert key in rep
    assert isinstance(rep["generated_at"], str)
    _roundtrip(rep)


def test_export_json_and_txt_roundtrip(tmp_path):
    jpath = tmp_path / "report.json"
    tpath = tmp_path / "report.txt"

    out_j = export(str(jpath), fmt="json")
    assert jpath.exists()
    with open(out_j, encoding="utf-8") as fh:
        loaded = json.load(fh)  # valid JSON
    assert "overview" in loaded and "cpu" in loaded

    out_t = export(str(tpath), fmt="txt")
    assert tpath.exists()
    text = tpath.read_text(encoding="utf-8")
    assert "HardwareInfo report" in text
    assert "CPU" in text
    assert out_t.endswith("report.txt")


def test_export_reuses_supplied_report(tmp_path):
    rep = full_report()
    p = tmp_path / "r.json"
    export(str(p), fmt="json", report=rep)
    with open(p, encoding="utf-8") as fh:
        assert json.load(fh)["generated_at"] == rep["generated_at"]


# --- failure path -> clean HWInfoError --------------------------------------

def test_export_bad_format_raises_hwinfoerror(tmp_path):
    with pytest.raises(HWInfoError):
        export(str(tmp_path / "x.csv"), fmt="csv")


def test_export_unwritable_path_raises_hwinfoerror(tmp_path):
    # Treat an existing *file* as a parent directory: creating a child under it
    # is refused by the OS on both POSIX and Windows -> clean HWInfoError.
    blocker = tmp_path / "blocker"
    blocker.write_text("x")
    with pytest.raises(HWInfoError):
        export(str(blocker / "report.json"), fmt="json")


def test_export_empty_path_raises_hwinfoerror():
    with pytest.raises(HWInfoError):
        export("", fmt="json")


# --- package surface --------------------------------------------------------

def test_public_api_exports():
    for name in ("overview", "cpu_info", "memory_info", "disk_info",
                 "network_info", "sensors", "gpu_info", "full_report",
                 "export", "sample", "HWInfoError"):
        assert hasattr(hwinfo, name)
    assert issubclass(HWInfoError, Exception)
