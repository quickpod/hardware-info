# HardwareInfo

A fast, **offline**, **100% open-source** system & hardware information tool for Windows. Nothing is uploaded anywhere. Built entirely by AI with human testing and guidance, and published on [QuickOpen](https://quickopen.ai/projects/hardware-info).

> **100% AI-built and open source.** Apache-2.0.

## What it does

A detailed system inventory: CPU, memory, motherboard, GPU, storage and network hardware; live sensors (CPU/temps, fan, load), per-core usage, battery health, and SMART disk status where available. Export a full report. A CPU-Z/HWiNFO-style tool, fully open source.

## Install

Download **`HardwareInfo-Setup.exe`** from the [QuickOpen page](https://quickopen.ai/projects/hardware-info) or the [GitHub release](https://github.com/quickpod/hardware-info/releases/latest) and double-click it. It installs per-user, adds Desktop and Start Menu shortcuts, and can optionally trust the QuickOpen Root CA. Authenticode-signed by the QuickOpen Code Signing CA — verify at [quickopen.ai/trust](https://quickopen.ai/trust).

## Run from source

```sh
pip install -r requirements.txt
python hardware_info_app.py          # GUI
python -m hwinfo --help    # CLI
```


## Features

- **Overview** — OS, hostname, uptime/boot time, machine & architecture, Python runtime.
- **CPU** — model, physical/logical core counts, base/current/max frequency, live per-core utilisation bars, and low-level stats.
- **Memory** — physical RAM and swap, with usage meters and human-readable sizes.
- **Disks** — partitions, filesystems, capacity/usage, and aggregate IO counters. SMART disk health is shown when `smartctl` is available (install `smartmontools`); otherwise omitted. Reading SMART needs privilege, so an unprivileged run retries through `sudo -n` — grant it with a NOPASSWD rule for `smartctl` if you want health without running the app as root.
- **Network** — interfaces with IPv4/IPv6/MAC addresses, up/down state, link speed, MTU and per-NIC IO totals.
- **Sensors** — temperatures, fan speeds and battery where the OS exposes them (Linux via psutil; Windows via optional WMI). Returns gracefully when no sensors are present.
- **GPU** — best-effort inventory: NVIDIA cards via `nvidia-smi` (name, VRAM, utilisation, temperature), other adapters via WMI (Windows) or DRM (Linux).
- **Live System Monitor** — a threaded tab that refreshes CPU, per-core load, memory and network rates about once a second without blocking the UI.
- **Export** — write a full report to JSON or plain text.
- Dark/light themes (QuickOpen palette), fully offline, and a matching command-line interface. Built on [psutil](https://github.com/giampaolo/psutil) — no proprietary or copyleft runtime dependencies.

## CLI examples

Every command accepts `--json` to emit the raw, machine-readable data.

```sh
python -m hwinfo overview           # OS, host, uptime, Python
python -m hwinfo cpu                # model, cores, frequency, per-core load
python -m hwinfo memory             # RAM + swap
python -m hwinfo disks              # partitions, usage, SMART (if available)
python -m hwinfo network            # interfaces, addresses, link state
python -m hwinfo sensors            # temperatures, fans, battery
python -m hwinfo gpu                # GPU inventory (best-effort)

python -m hwinfo cpu --json         # raw JSON for any section

python -m hwinfo report             # full inventory as JSON (stdout)
python -m hwinfo report --txt       # full inventory as readable text
python -m hwinfo report --out report.json          # write JSON to a file
python -m hwinfo report --txt --out report.txt     # write text to a file

python -m hwinfo watch              # live monitor in the terminal (Ctrl-C to stop)
python -m hwinfo watch 10 --interval 0.5           # sample for 10s, twice a second
```

## License

Apache-2.0 — see [LICENSE](LICENSE). A 100% AI-built project published on QuickOpen.
