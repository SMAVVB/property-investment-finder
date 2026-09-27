"""Thin wrapper around the NordVPN CLI for IP rotation during scraping runs.

System-wide, not per-process: while connected, ALL of this machine's traffic
routes through the VPN (kill switch stays disabled on purpose -- if the VPN
daemon glitches during an unattended overnight run, we want traffic to fall
back to the normal connection rather than silently blackhole everything
else running on this host).

Rotates between German exit cities (Berlin/Frankfurt/Hamburg) rather than
random countries -- plausible-looking traffic for a .de site and low latency.
Best-effort throughout: every call is wrapped so a VPN hiccup degrades to
"scrape on the real IP" instead of killing the run.
"""
from __future__ import annotations

import itertools
import subprocess
import sys

_CITIES = ["Berlin", "Frankfurt", "Hamburg"]
_city_cycle = itertools.cycle(_CITIES)


def _run(*args: str, timeout: int = 30) -> bool:
    try:
        subprocess.run(["nordvpn", *args], check=True, capture_output=True, text=True, timeout=timeout)
        return True
    except Exception as e:
        print(f"vpn: `nordvpn {' '.join(args)}` failed ({e}) -- continuing without VPN", file=sys.stderr)
        return False


def connect(city: str | None = None) -> bool:
    city = city or next(_city_cycle)
    ok = _run("connect", f"Germany {city}", timeout=45)
    print(f"vpn: {'connected to' if ok else 'FAILED to connect to'} Germany {city}")
    return ok


def rotate() -> bool:
    """Disconnect and reconnect to the next city in the cycle."""
    _run("disconnect", timeout=20)
    return connect(next(_city_cycle))


def disconnect() -> None:
    _run("disconnect", timeout=20)
    print("vpn: disconnected")
