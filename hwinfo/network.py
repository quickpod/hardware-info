"""Network details: interfaces, addresses, link state, speeds and IO counters."""

from __future__ import annotations

import socket

from ._common import human_bytes


# Map psutil address-family constants to friendly names without assuming which
# ones exist on a given platform (AF_PACKET is Linux-only, AF_LINK is BSD/mac).
def _family_name(family):
    try:
        if family == socket.AF_INET:
            return "IPv4"
        if family == socket.AF_INET6:
            return "IPv6"
    except Exception:
        pass
    name = getattr(family, "name", None)
    if name in ("AF_PACKET", "AF_LINK"):
        return "MAC"
    return str(name or family)


def network_info():
    """Return a JSON-serializable dict describing network interfaces.

    Keys: ``interfaces`` -- a dict keyed by NIC name, each with ``addresses``
    (list of ``{family, address, netmask, broadcast}``), ``is_up``, ``speed_mbps``,
    ``mtu``, ``duplex`` and per-NIC ``io`` counters -- and a top-level ``io_total``.
    """
    import psutil

    addrs = {}
    try:
        addrs = psutil.net_if_addrs()
    except Exception:
        addrs = {}
    stats = {}
    try:
        stats = psutil.net_if_stats()
    except Exception:
        stats = {}
    per_nic_io = {}
    try:
        per_nic_io = psutil.net_io_counters(pernic=True) or {}
    except Exception:
        per_nic_io = {}

    interfaces = {}
    for name, addr_list in addrs.items():
        entry = {
            "addresses": [],
            "is_up": None,
            "speed_mbps": None,
            "mtu": None,
            "duplex": None,
            "io": {},
        }
        for a in addr_list:
            entry["addresses"].append({
                "family": _family_name(a.family),
                "address": a.address,
                "netmask": a.netmask,
                "broadcast": getattr(a, "broadcast", None),
            })
        st = stats.get(name)
        if st is not None:
            entry["is_up"] = bool(st.isup)
            entry["speed_mbps"] = int(st.speed) if st.speed else 0
            entry["mtu"] = int(st.mtu)
            entry["duplex"] = _duplex_name(getattr(st, "duplex", None))
        ctr = per_nic_io.get(name)
        if ctr is not None:
            entry["io"] = _io_dict(ctr)
        interfaces[name] = entry

    io_total = {}
    try:
        agg = psutil.net_io_counters(pernic=False)
        if agg is not None:
            io_total = _io_dict(agg)
    except Exception:
        io_total = {}

    return {"interfaces": interfaces, "io_total": io_total}


def _duplex_name(duplex):
    try:
        import psutil

        return {
            psutil.NIC_DUPLEX_FULL: "full",
            psutil.NIC_DUPLEX_HALF: "half",
            psutil.NIC_DUPLEX_UNKNOWN: "unknown",
        }.get(duplex, "unknown")
    except Exception:
        return "unknown"


def _io_dict(ctr):
    out = {
        "bytes_sent": int(getattr(ctr, "bytes_sent", 0)),
        "bytes_recv": int(getattr(ctr, "bytes_recv", 0)),
        "packets_sent": int(getattr(ctr, "packets_sent", 0)),
        "packets_recv": int(getattr(ctr, "packets_recv", 0)),
        "errin": int(getattr(ctr, "errin", 0)),
        "errout": int(getattr(ctr, "errout", 0)),
        "dropin": int(getattr(ctr, "dropin", 0)),
        "dropout": int(getattr(ctr, "dropout", 0)),
    }
    out["bytes_sent_h"] = human_bytes(out["bytes_sent"])
    out["bytes_recv_h"] = human_bytes(out["bytes_recv"])
    return out
