#!/usr/bin/env python3
"""
ImmoScout24 scraper -- built directly by hand after the agent failed to get
jev-ultrafast working. Uses Scrapling's StealthyFetcher (real headless
Chromium, passes IS24's AWS WAF JS challenge) to:
  1. Paginate search results per city/track, parsing the embedded
     `resultListModel` JSON (price, size, rooms, year, energy class, etc.)
  2. Fetch each listing's own expose page and extract the real
     `expose-description-body` text (verified by hand: this is genuine
     free-text prose, not a search-card snippet).

Run: /home/vincent/multica-lab/venv-scrape/bin/python is24_scrape.py
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field

from scrapling.fetchers import StealthyFetcher

from regions import get_active_tracks
from vpn import connect_for as vpn_connect_for, disconnect as vpn_disconnect

TRACKS = get_active_tracks()

# Optional scope-down for callers that only want to (re-)scrape specific
# active cities this run (e.g. autotune.py's promote_to_deep_dive(), so a
# cycle doesn't re-scrape every active city every time as the active list
# grows -- that's what originally blew past the Multica task execution
# timeout on the first live autotune run). Comma-separated "bl_slug/city_slug"
# keys; unset (the default) scrapes every active track, same as always.
_scope = os.environ.get("IS24_SCRAPE_CITIES")
if _scope:
    _scope_keys = set(_scope.split(","))
    TRACKS = [t for t in TRACKS if f"{t[0]}/{t[1]}" in _scope_keys]

PAGES_PER_CITY = 30  # safety ceiling only (~20 listings/page -> 600/city); the inner loop
                      # already stops naturally once page * 20 >= numberOfHits, so this just
                      # needs to be above the largest city's real hit count (Leipzig: 305).
CONCURRENCY = 5

MIN_BUILT_YEAR = 1990  # skip pre-1990 buildings before the (expensive) per-listing expose
                        # fetch -- constructionYear is already in the cheap search-result JSON.
                        # Listings with no constructionYear in the search result are kept (not
                        # rejected on missing data); Calculator._apply_filters() still enforces
                        # this too, as a backstop and for non-IS24 sources.


@dataclass
class RawListing:
    is24_id: str
    title: str
    price: float | None
    living_space: float | None
    rooms: float | None
    plz: str | None
    city: str
    bundesland: str
    built_year: int | None
    energy_class: str | None
    broker_fee_pct: float | None
    url: str


def extract_result_json(html: str) -> dict | None:
    idx = html.find("resultListModel")
    if idx == -1:
        return None
    start = html.index("{", idx)
    depth = 0
    in_str = False
    esc = False
    end = None
    for i in range(start, len(html)):
        c = html[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        return None
    try:
        return json.loads(html[start:end])
    except json.JSONDecodeError:
        return None


def parse_entries(data: dict, city: str, bundesland: str) -> tuple[list[RawListing], int]:
    try:
        rl = data["searchResponseModel"]["resultlist.resultlist"]
        num_hits = int(rl["paging"]["numberOfHits"])
        entries = rl["resultlistEntries"][0]["resultlistEntry"]
    except (KeyError, IndexError, TypeError, ValueError):
        return [], 0
    if isinstance(entries, dict):
        entries = [entries]
    out = []
    for e in entries:
        re_ = e.get("resultlist.realEstate", {})
        is24_id = str(e.get("@id") or re_.get("@id") or "")
        if not is24_id:
            continue
        price = None
        p = re_.get("price", {})
        if isinstance(p, dict):
            price = p.get("value")
        addr = re_.get("address", {})
        plz = addr.get("postcode")
        courtage = re_.get("courtage", {})
        broker_pct = None
        if isinstance(courtage, dict):
            txt = courtage.get("description", {}).get("value") if isinstance(courtage.get("description"), dict) else None
        out.append(RawListing(
            is24_id=is24_id,
            title=re_.get("title", ""),
            price=float(price) if price else None,
            living_space=_to_float(re_.get("livingSpace")),
            rooms=_to_float(re_.get("numberOfRooms")),
            plz=plz,
            city=addr.get("city") or city,
            bundesland=bundesland,
            built_year=_to_int(re_.get("constructionYear")),
            energy_class=re_.get("energyEfficiencyClass"),
            broker_fee_pct=None,
            url=f"https://www.immobilienscout24.de/expose/{is24_id}",
        ))
    return out, num_hits


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def scrape_search_pages() -> list[RawListing]:
    all_listings: dict[str, RawListing] = {}
    for bl_slug, city_slug, city_name, bl_name in TRACKS:
        vpn_connect_for(bl_slug)
        for page in range(1, PAGES_PER_CITY + 1):
            url = (
                f"https://www.immobilienscout24.de/Suche/de/{bl_slug}/{city_slug}/wohnung-kaufen"
                f"?price=80000-150000&livingspace=30-55"
            )
            if page > 1:
                url += f"&pagenumber={page}"
            try:
                r = StealthyFetcher.fetch(url, headless=True, disable_resources=True,
                                           network_idle=True, timeout=30000)
            except Exception as e:
                print(f"  [{city_name} p{page}] FETCH ERROR: {e}", file=sys.stderr)
                continue
            if r.status != 200:
                print(f"  [{city_name} p{page}] status={r.status}, stopping this city")
                break
            data = extract_result_json(r.html_content)
            if data is None:
                print(f"  [{city_name} p{page}] no resultListModel found, stopping this city")
                break
            entries, num_hits = parse_entries(data, city_name, bl_name)
            if not entries:
                print(f"  [{city_name} p{page}] 0 entries (numberOfHits={num_hits}), stopping this city")
                break
            new, too_old = 0, 0
            for e in entries:
                if e.built_year is not None and e.built_year < MIN_BUILT_YEAR:
                    too_old += 1
                    continue
                if e.is24_id not in all_listings:
                    all_listings[e.is24_id] = e
                    new += 1
            print(f"  [{city_name} p{page}] {len(entries)} entries, {new} new, {too_old} pre-{MIN_BUILT_YEAR} skipped, numberOfHits={num_hits}, total_so_far={len(all_listings)}")
            if page * 20 >= num_hits:
                break
    return list(all_listings.values())


FETCH_WATCHDOG_SECONDS = 45  # StealthyFetcher's own timeout=30000 is a page-load
# timeout, not a guarantee against the underlying browser subprocess hanging
# without raising (observed live: a fetch stuck at 0% CPU with no child
# process, in ep_poll, for 46 minutes straight -- a real asyncio-level
# wait_for is the only thing that can force such a hang to give up).


async def fetch_expose_text(listing: RawListing, sem: asyncio.Semaphore) -> tuple[str, str]:
    async with sem:
        try:
            r = await asyncio.wait_for(
                StealthyFetcher.async_fetch(
                    listing.url, headless=True, disable_resources=True,
                    network_idle=True, timeout=30000,
                ),
                timeout=FETCH_WATCHDOG_SECONDS,
            )
        except Exception as e:
            return listing.is24_id, ""
        if r.status != 200:
            return listing.is24_id, ""
        # The expose page renders one expose-description-body span PER SECTION
        # (Objektbeschreibung, Sonstiges, Ausstattung, Lage, ...) -- re.search
        # only grabbed the first (usually the short teaser), silently dropping
        # every other section including "Sonstiges", which is exactly where
        # sellers disclose caveats (sitting tenant at below-market rent,
        # electrics needing renewal, etc.). Concatenate all of them.
        sections = re.findall(r'expose-description-body">(.*?)</span>', r.html_content, re.DOTALL)
        if not sections:
            return listing.is24_id, ""
        text = re.sub(r"<[^>]+>", " ", " ".join(sections))
        text = re.sub(r"\s+", " ", text).strip()
        return listing.is24_id, text


async def fetch_all_expose_texts(listings: list[RawListing]) -> dict[str, str]:
    sem = asyncio.Semaphore(CONCURRENCY)
    results = {}
    batch_size = 20
    # Group by region so each batch maps to (mostly) one VPN exit city rather
    # than an arbitrary mix -- scrape_search_pages() already inserts roughly
    # in per-city order, but sort defensively for any other caller.
    listings = sorted(listings, key=lambda l: l.bundesland or "")
    for i in range(0, len(listings), batch_size):
        batch = listings[i:i + batch_size]
        majority_bl = max({l.bundesland for l in batch}, key=lambda bl: sum(1 for l in batch if l.bundesland == bl))
        vpn_connect_for(majority_bl)
        t0 = time.time()
        pairs = await asyncio.gather(*[fetch_expose_text(l, sem) for l in batch])
        for lid, text in pairs:
            results[lid] = text
        ok = sum(1 for _, t in pairs if len(t) > 100)
        print(f"  expose batch {i}-{i+len(batch)}: {ok}/{len(batch)} with real text, {time.time()-t0:.0f}s")
    return results


def main():
    try:
        print("=== Phase 1: search result pages ===")
        listings = scrape_search_pages()  # connects VPN per-city as it goes
        print(f"\nTotal unique listings from search: {len(listings)}")

        with open("is24_listings_meta.json", "w") as f:
            json.dump([l.__dict__ for l in listings], f, ensure_ascii=False, indent=2)
        print("Saved metadata to is24_listings_meta.json")

        print("\n=== Phase 2: expose pages (real description text) ===")
        texts = asyncio.run(fetch_all_expose_texts(listings))
        with open("is24_expose_texts.json", "w") as f:
            json.dump(texts, f, ensure_ascii=False, indent=2)
        n_real = sum(1 for t in texts.values() if len(t) > 100)
        print(f"\nTotal with real description text (>100 chars): {n_real}/{len(listings)}")
        print("Saved to is24_expose_texts.json")
    finally:
        vpn_disconnect()


if __name__ == "__main__":
    main()
