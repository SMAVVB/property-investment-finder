"""Thin wrapper around the NordVPN CLI for IP rotation during scraping runs.

System-wide, not per-process: while connected, ALL of this machine's traffic
routes through the VPN (kill switch stays disabled on purpose -- if the VPN
daemon glitches during an unattended overnight run, we want traffic to fall
back to the normal connection rather than silently blackhole everything
else running on this host).

Only ONE process may hold the VPN connection at a time -- two scrapers
reconnecting independently stepped on each other's tunnel and produced
spurious 401s during testing. Never run two of these concurrently.

Picks the exit city geographically nearest the region actually being
scraped (only 3 German exit cities exist in this NordVPN account --
Berlin/Frankfurt/Hamburg -- so this is nearest-hub-of-3, not per-city
precision) so traffic looks locally-sourced rather than a single exit
point hammering every region in the country. Best-effort throughout:
every call is wrapped so a VPN hiccup degrades to "scrape on the real IP"
instead of killing the run.
"""
from __future__ import annotations

import subprocess
import sys

# bl_slug (as used throughout regions.yaml / the scraper) -> nearest of the
# 3 available exit cities. Deliberately covers all 16 Bundesländer, not just
# the ones currently active, since target_regions is meant to expand
# nationwide over time.
_BUNDESLAND_TO_VPN_CITY = {
    "berlin": "Berlin",
    "brandenburg": "Berlin",
    "sachsen": "Berlin",
    "sachsen-anhalt": "Berlin",
    "mecklenburg-vorpommern": "Hamburg",
    "hamburg": "Hamburg",
    "bremen": "Hamburg",
    "niedersachsen": "Hamburg",
    "schleswig-holstein": "Hamburg",
    "hessen": "Frankfurt",
    "rheinland-pfalz": "Frankfurt",
    "saarland": "Frankfurt",
    "nordrhein-westfalen": "Frankfurt",
    "baden-wuerttemberg": "Frankfurt",
    "bayern": "Frankfurt",
    "thueringen": "Frankfurt",
}
_DEFAULT_CITY = "Frankfurt"  # central-west default for anything unmapped

# Disabled: confirmed by direct A/B test (2026-09-27) that IS24's anti-bot
# WAF 401s requests through NordVPN's German exit IPs while the exact same
# URL succeeds on the real residential IP seconds apart. Consumer VPN/
# datacenter ranges are exactly the kind of IP reputation category WAFs
# blocklist wholesale -- rotating exit cities doesn't look "more local," it
# looks like a known VPN, which is worse than not using one. Leave this off
# until/unless a dedicated (non-shared) IP is available to test.
ENABLED = False

_current_city: str | None = None


def _run(*args: str, timeout: int = 30) -> bool:
    try:
        subprocess.run(["nordvpn", *args], check=True, capture_output=True, text=True, timeout=timeout)
        return True
    except Exception as e:
        print(f"vpn: `nordvpn {' '.join(args)}` failed ({e}) -- continuing without VPN", file=sys.stderr)
        return False


def city_for_bundesland(bl_slug: str | None) -> str:
    """Accepts either a bl_slug ('sachsen-anhalt', 'berlin/berlin' for Berlin
    boroughs -- take the part before the slash) or the display bundesland
    name stored on `listing` ('Sachsen-Anhalt', 'Berlin'). Falls back to
    _DEFAULT_CITY for anything unmapped."""
    key = (bl_slug or "").split("/")[0].lower()
    return _BUNDESLAND_TO_VPN_CITY.get(key, _DEFAULT_CITY)


def connect_for(bl_slug: str | None) -> bool:
    """Connect to the nearest exit city for this region, unless we're
    already on it (skips needless reconnect churn for consecutive listings
    in the same region)."""
    global _current_city
    if not ENABLED:
        return True
    target = city_for_bundesland(bl_slug)
    if target == _current_city:
        return True
    ok = _run("connect", f"Germany {target}", timeout=45)
    if ok:
        _current_city = target
    print(f"vpn: {'connected to' if ok else 'FAILED to connect to'} Germany {target} (region: {bl_slug})")
    return ok


def disconnect() -> None:
    global _current_city
    if not ENABLED:
        return
    _run("disconnect", timeout=20)
    _current_city = None
    print("vpn: disconnected")
