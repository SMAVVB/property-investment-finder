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

Crash-safe / resumable: writes each batch to the DB immediately (not
buffered to the end) and records completed listing_ids in
data/.refetch_progress.json, so killing this process (deliberately, or via
a host reboot/shutdown) and re-running it later only re-fetches whatever
wasn't finished yet.

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
CONCURRENCY = 5
BATCH_SIZE = 20


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


async def refetch_batch(rows: list[tuple[str, str]], sem: asyncio.Semaphore) -> dict[str, str]:
    stub_listings = [RawListing(
        is24_id=lid, title="", price=None, living_space=None, rooms=None,
        plz=None, city="", bundesland="", built_year=None, energy_class=None,
        broker_fee_pct=None, url=url,
    ) for lid, url in rows]
    pairs = await asyncio.gather(*[fetch_expose_text(l, sem) for l in stub_listings])
    return dict(pairs)


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    all_rows = conn.execute(
        "SELECT listing_id, url, bundesland FROM listing WHERE url IS NOT NULL AND url != ''"
    ).fetchall()

    done = load_progress()
    pending = [(lid, url, bl) for lid, url, bl in all_rows if lid not in done]
    # Group by bundesland so each batch of 20 maps to (mostly) one VPN exit
    # city instead of an arbitrary mix -- the user wants the exit IP to look
    # locally-sourced for whatever region is actually being scraped.
    pending.sort(key=lambda row: row[2] or "")
    print(f"{len(all_rows)} listings total, {len(done)} already done, {len(pending)} remaining")

    sem = asyncio.Semaphore(CONCURRENCY)
    grew = 0
    try:
        for i in range(0, len(pending), BATCH_SIZE):
            batch_rows = pending[i:i + BATCH_SIZE]
            batch = [(lid, url) for lid, url, _bl in batch_rows]
            majority_bl = max({bl for _, _, bl in batch_rows}, key=lambda bl: sum(1 for *_, b in batch_rows if b == bl))
            vpn_connect_for(majority_bl)
            t0 = time.time()
            try:
                # Outer safety net on top of fetch_expose_text's own per-fetch
                # watchdog: 20 fetches / concurrency 5 capped at 45s each should
                # never exceed ~4*45=180s; give it a further margin before
                # giving up on the whole batch rather than hanging forever.
                texts = asyncio.run(asyncio.wait_for(refetch_batch(batch, sem), timeout=240))
            except asyncio.TimeoutError:
                print(f"  batch {i}-{i + len(batch)}: TIMED OUT after 240s, skipping -- will retry next run")
                texts = {}
            for listing_id, _url in batch:
                new_text = texts.get(listing_id, "")
                if not new_text:
                    continue  # leave raw_data untouched, don't mark done -- retry next run
                old_len = conn.execute(
                    "SELECT LENGTH(raw_data) FROM listing WHERE listing_id = ?", (listing_id,)
                ).fetchone()[0] or 0
                conn.execute("UPDATE listing SET raw_data = ? WHERE listing_id = ?", (new_text, listing_id))
                if len(new_text) > old_len:
                    grew += 1
                done.add(listing_id)
            conn.commit()  # persist this batch's raw_data before touching progress file
            save_progress(done)
            ok = sum(1 for _, t in texts.items() if len(t) > 100)
            print(f"  batch {i}-{i + len(batch)}: {ok}/{len(batch)} with real text, "
                  f"{time.time() - t0:.0f}s, {len(done)}/{len(all_rows)} done overall")
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
