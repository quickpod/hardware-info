r"""SMART health via smartctl.

smartctl is called directly rather than through pySMART: pySMART wraps the
same binary but its device discovery fails on some controllers -- NVMe in
particular, where it reports a drive that smartctl itself enumerates fine.
"""

from __future__ import annotations

import json

import pytest

from hwinfo import disks


class Proc:
    def __init__(self, stdout="", returncode=0):
        self.stdout = stdout
        self.stderr = ""
        self.returncode = returncode


SCAN = json.dumps({"devices": [{"name": "/dev/nvme0", "type": "nvme"}]})
HEALTHY = json.dumps({
    "model_name": "Acer FA200 4TB",
    "smart_status": {"passed": True},
    "temperature": {"current": 40},
})
FAILING = json.dumps({
    "model_name": "Old Disk",
    "smart_status": {"passed": False},
    "temperature": {"current": 55},
})


def fake_run(mapping, calls=None):
    def run(argv, **_kw):
        if calls is not None:
            calls.append(argv)
        key = "scan" if "--scan" in argv else "health"
        out = mapping.get(key, "")
        return Proc(out, 0 if out else 1)
    return run


def test_a_healthy_drive_is_reported(monkeypatch):
    monkeypatch.setattr(disks.shutil, "which", lambda _n: "/usr/sbin/smartctl")
    monkeypatch.setattr(disks.subprocess, "run",
                        fake_run({"scan": SCAN, "health": HEALTHY}))
    got = disks._smart_health()
    assert got == [{"device": "/dev/nvme0", "name": "Acer FA200 4TB",
                    "assessment": "PASS", "temperature": 40}]


def test_a_failing_drive_is_reported_as_fail(monkeypatch):
    monkeypatch.setattr(disks.shutil, "which", lambda _n: "/usr/sbin/smartctl")
    monkeypatch.setattr(disks.subprocess, "run",
                        fake_run({"scan": SCAN, "health": FAILING}))
    assert disks._smart_health()[0]["assessment"] == "FAIL"


def test_no_smartctl_means_no_smart_section(monkeypatch):
    monkeypatch.setattr(disks.shutil, "which", lambda _n: None)
    assert disks._smart_available() is False
    assert disks._smart_health() == []


def test_unparseable_output_is_ignored_not_raised(monkeypatch):
    monkeypatch.setattr(disks.shutil, "which", lambda _n: "/usr/sbin/smartctl")
    monkeypatch.setattr(disks.subprocess, "run",
                        fake_run({"scan": "not json", "health": ""}))
    assert disks._smart_health() == []


def test_a_probe_that_raises_does_not_take_the_report_down(monkeypatch):
    monkeypatch.setattr(disks.shutil, "which", lambda _n: "/usr/sbin/smartctl")

    def boom(*_a, **_k):
        raise OSError("device busy")
    monkeypatch.setattr(disks.subprocess, "run", boom)
    assert disks._smart_health() == []


def test_it_retries_through_sudo_when_unprivileged(monkeypatch):
    """Reading SMART needs privilege; the retry is what makes it work."""
    calls = []

    def run(argv, **_kw):
        calls.append(argv)
        if argv[0] != "sudo":
            return Proc("", 2)          # permission denied, no output
        return Proc(SCAN if "--scan" in argv else HEALTHY, 0)

    monkeypatch.setattr(disks.shutil, "which", lambda _n: "/usr/sbin/smartctl")
    monkeypatch.setattr(disks.subprocess, "run", run)
    got = disks._smart_health()
    assert got and got[0]["assessment"] == "PASS"
    assert any(c[0] == "sudo" and c[1] == "-n" for c in calls), \
        "sudo retry must be non-interactive -- a GUI cannot answer a prompt"


def test_a_drive_warning_still_yields_data(monkeypatch):
    """smartctl's exit code is a bitfield: high bits are warnings, not failure."""
    monkeypatch.setattr(disks.shutil, "which", lambda _n: "/usr/sbin/smartctl")

    def run(argv, **_kw):
        out = SCAN if "--scan" in argv else FAILING
        return Proc(out, 8)             # bit 3 = drive reports failing
    monkeypatch.setattr(disks.subprocess, "run", run)
    assert disks._smart_health()[0]["assessment"] == "FAIL"


def test_missing_temperature_is_none_not_an_error(monkeypatch):
    monkeypatch.setattr(disks.shutil, "which", lambda _n: "/usr/sbin/smartctl")
    payload = json.dumps({"model_name": "X", "smart_status": {"passed": True}})
    monkeypatch.setattr(disks.subprocess, "run",
                        fake_run({"scan": SCAN, "health": payload}))
    assert disks._smart_health()[0]["temperature"] is None
