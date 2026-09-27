#!/usr/bin/env python3
"""Autotune controller -- runs exactly one cycle of the autonomous
filter/region tuning loop per invocation (see
docs/superpowers/specs/2026-09-26-autonomous-filter-tuning-design.md).

Run: /home/vincent/laya_venv/bin/python scripts/autotune.py
Intended to be invoked repeatedly by a Multica scheduled autopilot
(see Task 7), not looped in-process.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(SCRIPTS_DIR)
sys.path.insert(0, os.path.join(REPO_DIR, "src"))

import yaml

from calculator import load_criteria
from regions import add_active, get_active_tracks, load_candidate_batch, load_regions

sys.path.insert(0, REPO_DIR)
from run_v1_pipeline import estimate_missing_rents, load_listings, load_rent_index
from threshold_search import search_best_criteria

DB_PATH = f"{REPO_DIR}/data/listings.db"
CRITERIA_PATH = f"{REPO_DIR}/criteria.yaml"
TUNING_HISTORY_PATH = f"{REPO_DIR}/data/tuning_history.md"

TOP_K_PROMOTE = 10
SCOUT_BATCH_SIZE = 20
MIN_SHORTLIST_SIZE = 20
IMPROVEMENT_MARGIN = 2.0
NON_IMPROVING_STOP_AFTER = 3

PARAM_GRID = {
    "built_year.min": [0, 1970, 1990, 2000],
    "yield.gross.min": [0.03, 0.035, 0.04, 0.045],
    "location_must_have.max_distance_to_station_minutes": [5, 10, 15, 999],
}


def should_stop(non_improving_streak: int) -> bool:
    return non_improving_streak >= NON_IMPROVING_STOP_AFTER


def get_state(conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        "SELECT mean_score FROM tuning_runs WHERE promoted = 1 ORDER BY id DESC LIMIT 1"
    ).fetchone()
    best_score = row[0] if row else 0.0
    recent = conn.execute(
        "SELECT promoted FROM tuning_runs ORDER BY id DESC LIMIT ?",
        (NON_IMPROVING_STOP_AFTER,),
    ).fetchall()
    streak = 0
    for (promoted,) in recent:
        if promoted:
            break
        streak += 1
    return {"best_score": best_score, "non_improving_streak": streak}


def rank_scouted_cities(conn: sqlite3.Connection, top_k: int) -> list[sqlite3.Row]:
    # Not fully redundant with run_cycle()'s conn.row_factory assignment:
    # tests/test_autotune_state.py (and any other direct caller) passes a
    # plain connection without that already set, and needs dict-style row
    # access here to work regardless.
    conn.row_factory = sqlite3.Row
    return conn.execute(
        """
        SELECT * FROM region_scouting
        WHERE status = 'ok' AND est_kaufpreisfaktor IS NOT NULL
        ORDER BY est_kaufpreisfaktor ASC
        LIMIT ?
        """,
        (top_k,),
    ).fetchall()


def _lookup_display_bundesland(bl_slug: str, city_slug: str) -> str:
    """region_scouting only stores kreis_ags as '{bl_slug}/{city_slug}' --
    it has no bundesland column. The display name lives in regions.yaml
    (active/candidates/scouted all carry it), so look it up there rather
    than guessing from the slug."""
    data = load_regions()
    for bucket in ("active", "candidates", "scouted"):
        for r in data.get(bucket, []):
            if r["bl_slug"] == bl_slug and r["city_slug"] == city_slug:
                return r["display_bundesland"]
    # Fall back to a slug-derived guess rather than crashing -- this can
    # only happen if regions.yaml was hand-edited out from under us.
    return bl_slug.replace("-", " ").title()


def promote_to_deep_dive(top_cities: list) -> None:
    """Add the given cities to regions.yaml's active list, then run the
    existing scrape -> import chain -- but ONLY for cities that are
    genuinely new this cycle, scoped via IS24_SCRAPE_CITIES.

    Without this scoping, immoscout_scraper.py re-scrapes every already-
    active city every single cycle (rank_scouted_cities() returns the same
    top-K almost every time once scouting has any 'ok' rows, so top_cities
    is essentially never empty) -- that's what blew past the Multica task
    execution timeout on the first live run once the active list grew.
    Refreshing already-active cities' listings periodically is a real need
    too, but out of scope here -- run src/immoscout_scraper.py by hand (no
    IS24_SCRAPE_CITIES set) for a full refresh when that's wanted.
    """
    already_active_keys = {(t[0], t[1]) for t in get_active_tracks()}
    newly_added_keys = []
    for row in top_cities:
        bl_slug, city_slug = row["kreis_ags"].split("/", 1)
        if (bl_slug, city_slug) not in already_active_keys:
            newly_added_keys.append(f"{bl_slug}/{city_slug}")
        display_bundesland = _lookup_display_bundesland(bl_slug, city_slug)
        add_active(bl_slug, city_slug, row["city"], display_bundesland)
    if not newly_added_keys:
        return
    scoped_env = {**os.environ, "IS24_SCRAPE_CITIES": ",".join(newly_added_keys)}
    subprocess.run(
        ["/home/vincent/multica-lab/venv-scrape/bin/python", "src/immoscout_scraper.py"],
        check=True, cwd=REPO_DIR, env=scoped_env,
    )
    subprocess.run(
        ["/home/vincent/laya_venv/bin/python", "scripts/import_immoscout.py"],
        check=True, cwd=REPO_DIR,
    )


def append_history(entry: dict, source: str = "autotune") -> None:
    with open(TUNING_HISTORY_PATH, "a", encoding="utf-8") as f:
        f.write(
            f"\n## {entry['cycle_at']} [{source}]\n\n"
            f"- Shortlist size: {entry['shortlist_size']}\n"
            f"- Mean score: {entry['mean_score']:.2f}\n"
            f"- Promoted: {'yes' if entry['promoted'] else 'no'}\n"
            f"- Preset: `{json.dumps(entry['preset'])}`\n"
        )


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True, cwd=REPO_DIR
    ).stdout.strip()


def _commit_and_push_or_rollback(paths: list[str], message: str) -> str | None:
    """git add+commit+push the given paths. On any failure (push rejected,
    network blip, etc.) roll the repo back to the pre-existing HEAD rather
    than leaving a committed-but-unpushed change sitting on local main --
    that would permanently wedge every future cycle with no record of
    what happened. Returns the new commit hash, or None if nothing landed."""
    pre_sha = _git("rev-parse", "HEAD")
    try:
        _git("add", *paths)
        _git("commit", "-m", message)
        commit_hash = _git("rev-parse", "HEAD")
        _git("push", "origin", "main")
        return commit_hash
    except subprocess.CalledProcessError as e:
        print(f"autotune: commit of {paths} failed to land ({e}); rolling back to {pre_sha}", file=sys.stderr)
        _git("reset", "--hard", pre_sha)
        return None


def run_cycle() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    state = get_state(conn)
    if should_stop(state["non_improving_streak"]):
        print(f"Plateau reached ({NON_IMPROVING_STOP_AFTER} consecutive non-improving cycles) -- stopping.")
        conn.close()
        return

    candidates = load_candidate_batch(batch_size=SCOUT_BATCH_SIZE)
    if candidates:
        subprocess.run(
            ["/home/vincent/multica-lab/venv-scrape/bin/python", "scripts/scout.py"],
            check=True, cwd=REPO_DIR,
        )

    top_cities = rank_scouted_cities(conn, TOP_K_PROMOTE)
    promote_to_deep_dive(top_cities)

    # regions.yaml changes are committed/pushed independently of the
    # criteria grid-search outcome below -- a region promotion can
    # trigger a real, costly scrape and must not sit uncommitted for
    # cycles just because this cycle's criteria didn't clear the
    # improvement margin.
    regions_changed = bool(_git("status", "--porcelain", "regions.yaml").strip())
    if regions_changed:
        _commit_and_push_or_rollback(
            ["regions.yaml"],
            f"autotune: promote {len(top_cities)} scouted region(s) to active deep-scraping\n\n"
            "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>\n"
            "Claude-Session: https://claude.ai/code/session_011mDK3TmcgpPLGPpzCaGB93",
        )

    # load_listings' own type hint says list[Listing], but it actually returns
    # list[tuple[Listing, raw_data]] (see run_v1_pipeline.main()'s own
    # "for listing, _raw in listings" usage). Estimate missing rents the same
    # way main() does BEFORE unpacking -- otherwise every listing with no
    # scraped rent_monthly shows a 0 gross yield and fails every yield-based
    # filter regardless of anything else being tuned (caught by a live run:
    # 422/422 listings failing on "Brutto-Yield" alone).
    listing_pairs = load_listings(conn)
    estimate_missing_rents(listing_pairs, load_rent_index(conn))
    listings = [listing for listing, _raw in listing_pairs]
    base_criteria = load_criteria(CRITERIA_PATH)

    best_criteria, mean_score, shortlist_size = search_best_criteria(
        listings, base_criteria, PARAM_GRID, MIN_SHORTLIST_SIZE
    )

    promoted = mean_score > state["best_score"] + IMPROVEMENT_MARGIN
    cycle_at = datetime.now(timezone.utc).isoformat()
    commit_hash = None
    if promoted:
        with open(CRITERIA_PATH, "w", encoding="utf-8") as f:
            yaml.dump(best_criteria, f, allow_unicode=True, sort_keys=False)
        commit_hash = _commit_and_push_or_rollback(
            ["criteria.yaml"],
            f"autotune: new best preset (mean score {mean_score:.2f}, shortlist {shortlist_size})\n\n"
            "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>\n"
            "Claude-Session: https://claude.ai/code/session_011mDK3TmcgpPLGPpzCaGB93",
        )
        promoted = commit_hash is not None

    conn.execute(
        """
        INSERT INTO tuning_runs (cycle_at, preset_json, shortlist_size, mean_score, promoted, commit_hash, source)
        VALUES (?, ?, ?, ?, ?, ?, 'autotune')
        """,
        (cycle_at, json.dumps(best_criteria), shortlist_size, mean_score, promoted, commit_hash),
    )
    conn.commit()
    append_history({
        "cycle_at": cycle_at, "shortlist_size": shortlist_size,
        "mean_score": mean_score, "promoted": promoted, "preset": best_criteria,
    })
    conn.close()

    # Every cycle appends to tuning_history.md (not just promoted ones) --
    # commit/push it every time too, or the human-readable audit trail this
    # loop's whole "no approval gate" premise depends on only ever exists
    # locally, never actually reaching origin/main.
    # data/listings.db holds the tuning_runs row this cycle just wrote --
    # same "audit trail stays local-only" problem as tuning_history.md,
    # just on the SQL side. Commit both together.
    _commit_and_push_or_rollback(
        ["data/tuning_history.md", "data/listings.db"],
        f"autotune: log cycle {cycle_at} (mean score {mean_score:.2f}, "
        f"shortlist {shortlist_size}, promoted={promoted})\n\n"
        "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>\n"
        "Claude-Session: https://claude.ai/code/session_011mDK3TmcgpPLGPpzCaGB93",
    )
    print(f"Cycle done: mean_score={mean_score:.2f} shortlist_size={shortlist_size} promoted={promoted}")


if __name__ == "__main__":
    run_cycle()
