"""Region configuration for the ImmoScout24 scraper and the autotune loop.

Replaces the old hardcoded TRACKS list in immoscout_scraper.py with a data
file (regions.yaml) the autotune loop can read and write programmatically,
plus a seed list of German cities the Scout stage works through a batch
at a time.
"""
from __future__ import annotations

import os

import yaml

REGIONS_PATH = os.path.join(os.path.dirname(__file__), "..", "regions.yaml")


def load_regions(path: str = REGIONS_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_regions(data: dict, path: str = REGIONS_PATH) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)


def get_active_tracks(path: str = REGIONS_PATH) -> list[tuple[str, str, str, str]]:
    """Returns (bl_slug, city_slug, display_city, display_bundesland) tuples
    for every active region -- same shape immoscout_scraper.py's old
    hardcoded TRACKS list used."""
    data = load_regions(path)
    return [
        (r["bl_slug"], r["city_slug"], r["display_city"], r["display_bundesland"])
        for r in data["active"]
    ]


def load_candidate_batch(
    batch_size: int = 20, path: str = REGIONS_PATH
) -> list[tuple[str, str, str, str]]:
    """Returns up to batch_size not-yet-scouted candidates, in seed-list order."""
    data = load_regions(path)
    scouted = {(c["bl_slug"], c["city_slug"]) for c in data.get("scouted", [])}
    out = []
    for c in data["candidates"]:
        key = (c["bl_slug"], c["city_slug"])
        if key in scouted:
            continue
        out.append((c["bl_slug"], c["city_slug"], c["display_city"], c["display_bundesland"]))
        if len(out) >= batch_size:
            break
    return out


def mark_scouted(
    candidates: list[tuple[str, str, str, str]], path: str = REGIONS_PATH
) -> None:
    data = load_regions(path)
    data.setdefault("scouted", [])
    existing = {(c["bl_slug"], c["city_slug"]) for c in data["scouted"]}
    for bl_slug, city_slug, city_name, bl_name in candidates:
        if (bl_slug, city_slug) in existing:
            continue
        data["scouted"].append({
            "bl_slug": bl_slug, "city_slug": city_slug,
            "display_city": city_name, "display_bundesland": bl_name,
        })
    save_regions(data, path)


def add_active(
    bl_slug: str, city_slug: str, display_city: str, display_bundesland: str,
    path: str = REGIONS_PATH,
) -> None:
    """Promote a scouted city to the actively-deep-scraped list, if it
    isn't already there."""
    data = load_regions(path)
    if any(r["bl_slug"] == bl_slug and r["city_slug"] == city_slug for r in data["active"]):
        return
    data["active"].append({
        "bl_slug": bl_slug, "city_slug": city_slug,
        "display_city": display_city, "display_bundesland": display_bundesland,
    })
    save_regions(data, path)
