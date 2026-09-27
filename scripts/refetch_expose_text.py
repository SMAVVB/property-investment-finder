#!/usr/bin/env python3
"""One-off backfill: re-fetch expose-page description text for every listing
already in data/listings.db and overwrite `listing.raw_data`.

Needed because src/immoscout_scraper.py's fetch_expose_text() used to only
capture the FIRST "expose-description-body" span on a page -- IS24 expose
pages render one such span per section (Objektbeschreibung, Sonstiges,
Ausstattung, Lage), so most of the historical dataset is missing everything
after the first section (see e.g. is24-167951332, whose real "Sonstiges"
section disclosed a sitting tenant and end-of-life electrics that never made
it into raw_data). That extraction bug is fixed now (concatenates all
sections) -- this script re-runs the fixed fetcher against the URLs already
on file, it does not re-run the search-page scrape.

Crash-safe / resumable: commits and checkpoints after EVERY SINGLE listing
(not batched -- a batched version of this hid a real bug: kleinanzeigen.de
fetches take ~32s each, so a 5-item batch could take ~160s, longer than the
external supervisor's kill window, so the process was being killed mid-batch
before its one commit-at-the-end ever ran -- looked exactly like an
indefinite hang, for HOURS, when it was actually silently discarding real
progress on every single restart). Per-item commits make checkpoint
granularity match reality regardless of how slow any given site's fetch is.

Run: /home/vincent/multica-lab/venv-scrape/bin/python scripts/refetch_expose_text.py
Follow with: /home/vincent/laya_venv/bin/python run_v1_pipeline.py --judge finetuned
  to recompute financials/judgments/shortlist on the corrected text.
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
import time

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(SCRIPTS_DIR)
sys.path.insert(0, os.path.join(REPO_DIR, "src"))

from immoscout_scraper import RawListing, fetch_expose_text  # noqa: E402
from vpn import connect_for as vpn_connect_for, disconnect as vpn_disconnect  # noqa: E402

DB_PATH = f"{REPO_DIR}/data/listings.db"
PROGRESS_PATH = f"{REPO_DIR}/data/.refetch_progress.json"
PER_ITEM_TIMEOUT = 60  # generous margin over fetch_expose_text's own internal 45s watchdog


def load_progress() -> set[str]:
    if not os.path.exists(PROGRESS_PATH):
        return set()
    with open(PROGRESS_PATH, encoding="utf-8") as f:
        return set(json.load(f))


def save_progress(done: set[str]) -> None:
    tmp_path = PROGRESS_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(sorted(done), f)
    os.replace(tmp_path, PROGRESS_PATH)  # atomic -- never leaves a half-written progress file


async def fetch_one(lid: str, url: str) -> str:
    listing = RawListing(
        is24_id=lid, title="", price=None, living_space=None, rooms=None,
        plz=None, city="", bundesland="", built_year=None, energy_class=None,
        broker_fee_pct=None, url=url,
    )
    sem = asyncio.Semaphore(1)
    _lid, text = await asyncio.wait_for(fetch_expose_text(listing, sem), timeout=PER_ITEM_TIMEOUT)
    return text


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    all_rows = conn.execute(
        "SELECT listing_id, url, bundesland FROM listing WHERE url IS NOT NULL AND url != ''"
    ).fetchall()

    done = load_progress()
    pending = [(lid, url, bl) for lid, url, bl in all_rows if lid not in done]
    pending.sort(key=lambda row: row[2] or "")  # group by region for VPN city matching (currently disabled)
    print(f"{len(all_rows)} listings total, {len(done)} already done, {len(pending)} remaining")

    grew = 0
    try:
        for lid, url, bl in pending:
            vpn_connect_for(bl)
            t0 = time.time()
            try:
                new_text = asyncio.run(fetch_one(lid, url))
            except asyncio.TimeoutError:
                print(f"  {lid}: TIMED OUT after {PER_ITEM_TIMEOUT}s, skipping -- will retry next run")
                continue
            elapsed = time.time() - t0
            if not new_text:
                print(f"  {lid}: no text ({elapsed:.0f}s)")
                continue  # leave raw_data untouched, don't mark done -- retry next run
            old_len = conn.execute(
                "SELECT LENGTH(raw_data) FROM listing WHERE listing_id = ?", (lid,)
            ).fetchone()[0] or 0
            conn.execute("UPDATE listing SET raw_data = ? WHERE listing_id = ?", (new_text, lid))
            conn.commit()  # persist THIS listing before touching progress file
            if len(new_text) > old_len:
                grew += 1
            done.add(lid)
            save_progress(done)
            print(f"  {lid}: {len(new_text)} chars ({elapsed:.0f}s), {len(done)}/{len(all_rows)} done overall")
    finally:
        if pending:
            vpn_disconnect()

    conn.close()
    if len(done) >= len(all_rows):
        print(f"Complete: {grew} listings' raw_data grew in length. Removing progress checkpoint.")
        if os.path.exists(PROGRESS_PATH):
            os.remove(PROGRESS_PATH)
    else:
        print(f"Stopped with {len(all_rows) - len(done)} remaining -- re-run this script to continue.")


if __name__ == "__main__":
    main()
