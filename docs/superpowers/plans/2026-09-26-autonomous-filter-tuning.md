# Autonomous Filter Tuning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the two-stage (Scout / Deep-dive) autonomous filter-and-region tuning loop described in `docs/superpowers/specs/2026-09-26-autonomous-filter-tuning-design.md`, so `criteria.yaml` and the target region list improve on their own instead of being hand-guessed.

**Architecture:** A cheap Scout stage (`scripts/scout.py`) ranks candidate German cities using search-JSON-only data (no detail-page fetch); the top-K get promoted to the existing full scrape/import/Calculator/Judge pipeline; a pure `threshold_search.py` module grid-searches the tunable (non price/size) criteria against whatever's been deep-scraped so far; a controller (`scripts/autotune.py`) runs one bounded cycle at a time, commits improvements to git, and stops itself after 3 non-improving cycles. A periodic LLM (Claude) review layer sits on top, reading the audit trail and proposing its own commits.

**Tech Stack:** Python 3.12 (existing `laya_venv` / `venv-scrape`), sqlite3, PyYAML, `scrapling` (already used by the existing scraper), Multica autopilots for scheduling.

---

## Task 1: Database schema — `region_scouting` and `tuning_runs` tables

**Files:**
- Modify: `schema.sql` (append after the existing `labels` table, before the index section)
- Test: manual verification (schema changes aren't unit-tested in this project; the existing tests don't cover schema.sql directly)

- [ ] **Step 1: Add the two new tables to `schema.sql`**

Insert this immediately before the `-- Indizes für häufige Abfragen` comment near the end of the file:

```sql
-- Tabelle 6: region_scouting — Scout-Stage-Cache (guenstige Voreinschaetzung
-- pro Stadt, ohne teure Expose-Detail-Fetches)
CREATE TABLE IF NOT EXISTS region_scouting (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    city                    TEXT    NOT NULL,
    kreis_ags               TEXT,                   -- hier: "{bl_slug}/{city_slug}" bis echte AGS vorliegt
    scouted_at              TEXT    NOT NULL,
    n_sale_hits             INTEGER,
    median_price_per_sqm    REAL,
    median_rent_per_sqm     REAL,
    est_kaufpreisfaktor     REAL,
    status                  TEXT    NOT NULL         -- 'ok', 'failed', 'no_slug'
);

-- Tabelle 7: tuning_runs — Audit-Trail des Autotune-Loops
CREATE TABLE IF NOT EXISTS tuning_runs (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_at                TEXT    NOT NULL,
    preset_json             TEXT    NOT NULL,        -- die versuchten Criteria als JSON
    shortlist_size          INTEGER NOT NULL,
    mean_score              REAL    NOT NULL,
    promoted                BOOLEAN NOT NULL DEFAULT 0,
    commit_hash             TEXT,                     -- gesetzt, falls promoted=1
    source                  TEXT    NOT NULL DEFAULT 'autotune'  -- 'autotune' oder 'llm_analyst'
);
```

- [ ] **Step 2: Apply the migration to the live DB**

`CREATE TABLE IF NOT EXISTS` is idempotent, so re-running the whole schema file against the existing DB is safe (it won't touch the 5 existing tables' data).

Run:
```bash
cd /tmp/property-investment-finder
python3 -c "
import sqlite3
conn = sqlite3.connect('data/listings.db')
conn.executescript(open('schema.sql').read())
conn.commit()
print('OK:', conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall())
"
```
Expected output includes `region_scouting` and `tuning_runs` in the table list, alongside the 5 existing tables.

- [ ] **Step 3: Commit**

```bash
cd /tmp/property-investment-finder
git add schema.sql data/listings.db
git commit -m "$(cat <<'EOF'
schema: add region_scouting and tuning_runs tables

Prep for the autonomous filter/region tuning loop (see
docs/superpowers/specs/2026-09-26-autonomous-filter-tuning-design.md).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011mDK3TmcgpPLGPpzCaGB93
EOF
)"
```

---

## Task 2: Region config — `regions.yaml` replaces hardcoded `TRACKS`

**Files:**
- Create: `regions.yaml`
- Create: `src/regions.py`
- Modify: `src/immoscout_scraper.py:25-49` (remove hardcoded `TRACKS`/`PAGES_PER_CITY`/`MIN_BUILT_YEAR` list, load from `regions.py` instead)
- Test: `tests/test_regions.py`

- [ ] **Step 1: Create `regions.yaml`**

The `active` list is the current 11 tracks from `immoscout_scraper.py`, migrated verbatim. The `candidates` list is a real (not exhaustive) seed of German cities outside the current 4 Bundesländer, for the Scout stage to work through — small on purpose, extend it over time.

```yaml
# Region configuration for the ImmoScout24 scraper and the autotune loop.
# `active`: currently deep-scraped every scrape run (immoscout_scraper.py).
# `candidates`: seed list the Scout stage (scripts/scout.py) works through,
#   in order, a batch at a time. Extend freely -- a wrong/dead slug just
#   gets marked 'failed'/'no_slug' in region_scouting and is skipped.
# `scouted`: appended automatically once a candidate has been scouted, so
#   the same city isn't re-scouted every cycle. Do not hand-edit this list.

active:
  - {bl_slug: sachsen, city_slug: leipzig, display_city: Leipzig, display_bundesland: Sachsen}
  - {bl_slug: sachsen-anhalt, city_slug: halle-saale, display_city: "Halle (Saale)", display_bundesland: Sachsen-Anhalt}
  - {bl_slug: sachsen-anhalt, city_slug: magdeburg, display_city: Magdeburg, display_bundesland: Sachsen-Anhalt}
  - {bl_slug: brandenburg, city_slug: frankfurt-oder, display_city: "Frankfurt (Oder)", display_bundesland: Brandenburg}
  - {bl_slug: brandenburg, city_slug: cottbus, display_city: Cottbus, display_bundesland: Brandenburg}
  - {bl_slug: brandenburg, city_slug: brandenburg-an-der-havel, display_city: "Brandenburg an der Havel", display_bundesland: Brandenburg}
  - {bl_slug: berlin/berlin, city_slug: neukoelln, display_city: "Berlin (Neukoelln)", display_bundesland: Berlin}
  - {bl_slug: berlin/berlin, city_slug: spandau, display_city: "Berlin (Spandau)", display_bundesland: Berlin}
  - {bl_slug: berlin/berlin, city_slug: marzahn-hellersdorf, display_city: "Berlin (Marzahn-Hellersdorf)", display_bundesland: Berlin}
  - {bl_slug: berlin/berlin, city_slug: lichtenberg, display_city: "Berlin (Lichtenberg)", display_bundesland: Berlin}
  - {bl_slug: berlin/berlin, city_slug: treptow-koepenick, display_city: "Berlin (Treptow-Koepenick)", display_bundesland: Berlin}

candidates:
  - {bl_slug: sachsen, city_slug: dresden, display_city: Dresden, display_bundesland: Sachsen}
  - {bl_slug: sachsen, city_slug: chemnitz, display_city: Chemnitz, display_bundesland: Sachsen}
  - {bl_slug: sachsen, city_slug: zwickau, display_city: Zwickau, display_bundesland: Sachsen}
  - {bl_slug: sachsen, city_slug: goerlitz, display_city: Goerlitz, display_bundesland: Sachsen}
  - {bl_slug: sachsen, city_slug: bautzen, display_city: Bautzen, display_bundesland: Sachsen}
  - {bl_slug: sachsen, city_slug: plauen, display_city: Plauen, display_bundesland: Sachsen}
  - {bl_slug: sachsen, city_slug: hoyerswerda, display_city: Hoyerswerda, display_bundesland: Sachsen}
  - {bl_slug: sachsen, city_slug: zittau, display_city: Zittau, display_bundesland: Sachsen}
  - {bl_slug: sachsen-anhalt, city_slug: dessau-rosslau, display_city: "Dessau-Rosslau", display_bundesland: Sachsen-Anhalt}
  - {bl_slug: sachsen-anhalt, city_slug: wittenberg, display_city: "Lutherstadt Wittenberg", display_bundesland: Sachsen-Anhalt}
  - {bl_slug: sachsen-anhalt, city_slug: stendal, display_city: Stendal, display_bundesland: Sachsen-Anhalt}
  - {bl_slug: sachsen-anhalt, city_slug: merseburg, display_city: Merseburg, display_bundesland: Sachsen-Anhalt}
  - {bl_slug: sachsen-anhalt, city_slug: naumburg, display_city: Naumburg, display_bundesland: Sachsen-Anhalt}
  - {bl_slug: brandenburg, city_slug: potsdam, display_city: Potsdam, display_bundesland: Brandenburg}
  - {bl_slug: brandenburg, city_slug: oranienburg, display_city: Oranienburg, display_bundesland: Brandenburg}
  - {bl_slug: brandenburg, city_slug: falkensee, display_city: Falkensee, display_bundesland: Brandenburg}
  - {bl_slug: brandenburg, city_slug: eberswalde, display_city: Eberswalde, display_bundesland: Brandenburg}
  - {bl_slug: brandenburg, city_slug: bernau-bei-berlin, display_city: "Bernau bei Berlin", display_bundesland: Brandenburg}
  - {bl_slug: brandenburg, city_slug: schwedt-oder, display_city: "Schwedt (Oder)", display_bundesland: Brandenburg}
  - {bl_slug: brandenburg, city_slug: koenigs-wusterhausen, display_city: "Koenigs Wusterhausen", display_bundesland: Brandenburg}
  - {bl_slug: brandenburg, city_slug: senftenberg, display_city: Senftenberg, display_bundesland: Brandenburg}
  - {bl_slug: thueringen, city_slug: erfurt, display_city: Erfurt, display_bundesland: Thueringen}
  - {bl_slug: thueringen, city_slug: jena, display_city: Jena, display_bundesland: Thueringen}
  - {bl_slug: thueringen, city_slug: gera, display_city: Gera, display_bundesland: Thueringen}
  - {bl_slug: thueringen, city_slug: weimar, display_city: Weimar, display_bundesland: Thueringen}
  - {bl_slug: thueringen, city_slug: gotha, display_city: Gotha, display_bundesland: Thueringen}
  - {bl_slug: thueringen, city_slug: nordhausen, display_city: Nordhausen, display_bundesland: Thueringen}
  - {bl_slug: mecklenburg-vorpommern, city_slug: schwerin, display_city: Schwerin, display_bundesland: Mecklenburg-Vorpommern}
  - {bl_slug: mecklenburg-vorpommern, city_slug: rostock, display_city: Rostock, display_bundesland: Mecklenburg-Vorpommern}
  - {bl_slug: mecklenburg-vorpommern, city_slug: stralsund, display_city: Stralsund, display_bundesland: Mecklenburg-Vorpommern}
  - {bl_slug: mecklenburg-vorpommern, city_slug: greifswald, display_city: Greifswald, display_bundesland: Mecklenburg-Vorpommern}
  - {bl_slug: mecklenburg-vorpommern, city_slug: neubrandenburg, display_city: Neubrandenburg, display_bundesland: Mecklenburg-Vorpommern}
  - {bl_slug: niedersachsen, city_slug: hannover, display_city: Hannover, display_bundesland: Niedersachsen}
  - {bl_slug: niedersachsen, city_slug: braunschweig, display_city: Braunschweig, display_bundesland: Niedersachsen}
  - {bl_slug: niedersachsen, city_slug: salzgitter, display_city: Salzgitter, display_bundesland: Niedersachsen}
  - {bl_slug: niedersachsen, city_slug: wolfsburg, display_city: Wolfsburg, display_bundesland: Niedersachsen}
  - {bl_slug: niedersachsen, city_slug: goettingen, display_city: Goettingen, display_bundesland: Niedersachsen}
  - {bl_slug: hessen, city_slug: kassel, display_city: Kassel, display_bundesland: Hessen}
  - {bl_slug: hessen, city_slug: fulda, display_city: Fulda, display_bundesland: Hessen}
  - {bl_slug: nordrhein-westfalen, city_slug: duisburg, display_city: Duisburg, display_bundesland: Nordrhein-Westfalen}
  - {bl_slug: nordrhein-westfalen, city_slug: gelsenkirchen, display_city: Gelsenkirchen, display_bundesland: Nordrhein-Westfalen}
  - {bl_slug: nordrhein-westfalen, city_slug: bochum, display_city: Bochum, display_bundesland: Nordrhein-Westfalen}
  - {bl_slug: nordrhein-westfalen, city_slug: dortmund, display_city: Dortmund, display_bundesland: Nordrhein-Westfalen}
  - {bl_slug: nordrhein-westfalen, city_slug: hagen, display_city: Hagen, display_bundesland: Nordrhein-Westfalen}

scouted: []
```

- [ ] **Step 2: Write the failing test for `src/regions.py`**

Create `tests/test_regions.py`:

```python
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from regions import load_regions, save_regions, get_active_tracks, load_candidate_batch, mark_scouted

FIXTURE = {
    "active": [
        {"bl_slug": "sachsen", "city_slug": "leipzig", "display_city": "Leipzig", "display_bundesland": "Sachsen"},
    ],
    "candidates": [
        {"bl_slug": "sachsen", "city_slug": "dresden", "display_city": "Dresden", "display_bundesland": "Sachsen"},
        {"bl_slug": "sachsen", "city_slug": "chemnitz", "display_city": "Chemnitz", "display_bundesland": "Sachsen"},
    ],
    "scouted": [],
}


def _write_fixture(tmp_path):
    save_regions(FIXTURE, tmp_path)


def test_get_active_tracks_shape():
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
        path = f.name
    _write_fixture(path)
    tracks = get_active_tracks(path)
    assert tracks == [("sachsen", "leipzig", "Leipzig", "Sachsen")]
    os.unlink(path)


def test_load_candidate_batch_respects_batch_size():
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
        path = f.name
    _write_fixture(path)
    batch = load_candidate_batch(batch_size=1, path=path)
    assert batch == [("sachsen", "dresden", "Dresden", "Sachsen")]
    os.unlink(path)


def test_mark_scouted_excludes_from_next_batch():
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
        path = f.name
    _write_fixture(path)
    mark_scouted([("sachsen", "dresden", "Dresden", "Sachsen")], path=path)
    remaining = load_candidate_batch(batch_size=10, path=path)
    assert remaining == [("sachsen", "chemnitz", "Chemnitz", "Sachsen")]
    os.unlink(path)
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd /tmp/property-investment-finder && /home/vincent/laya_venv/bin/python -m pytest tests/test_regions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'regions'`

- [ ] **Step 4: Write `src/regions.py`**

```python
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
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd /tmp/property-investment-finder && /home/vincent/laya_venv/bin/python -m pytest tests/test_regions.py -v`
Expected: 3 passed

- [ ] **Step 6: Migrate `src/immoscout_scraper.py` to load `TRACKS` from `regions.py`**

Replace lines 25-49 (the hardcoded `TRACKS` list, `PAGES_PER_CITY`, `MIN_BUILT_YEAR`, and the comment blocks around them) with:

```python
from regions import get_active_tracks

TRACKS = get_active_tracks()

PAGES_PER_CITY = 30  # safety ceiling only (~20 listings/page -> 600/city); the inner loop
                      # already stops naturally once page * 20 >= numberOfHits, so this just
                      # needs to be above the largest city's real hit count (Leipzig: 305).
CONCURRENCY = 5

MIN_BUILT_YEAR = 1990  # skip pre-1990 buildings before the (expensive) per-listing expose
                        # fetch -- constructionYear is already in the cheap search-result JSON.
                        # Listings with no constructionYear in the search result are kept (not
                        # rejected on missing data); Calculator._apply_filters() still enforces
                        # this too, as a backstop and for non-IS24 sources.
```

(The `import sys` at the top of the file already exists; add `sys.path.insert(0, os.path.join(os.path.dirname(__file__)))` only if running the script directly ever fails to find `regions` — check first by running the existing test suite in Step 7 before adding anything extra.)

- [ ] **Step 7: Run the full test suite to confirm nothing broke**

Run: `cd /tmp/property-investment-finder && /home/vincent/laya_venv/bin/python -m pytest tests/ -q`
Expected: all tests that passed before still pass (56 passed, 1 skipped, plus the 3 new `test_regions.py` tests = 59 passed, 1 skipped)

- [ ] **Step 8: Commit**

```bash
cd /tmp/property-investment-finder
git add regions.yaml src/regions.py src/immoscout_scraper.py tests/test_regions.py
git commit -m "$(cat <<'EOF'
feat: move TRACKS from hardcoded Python to regions.yaml

Lets the autotune loop add/promote regions programmatically instead of
editing a live Python list. Includes a seed candidate list of German
cities outside the current 4 Bundeslaender for the Scout stage to work
through.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011mDK3TmcgpPLGPpzCaGB93
EOF
)"
```

---

## Task 3: Scout scoring math — `src/scout_scoring.py`

**Files:**
- Create: `src/scout_scoring.py`
- Test: `tests/test_scout_scoring.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_scout_scoring.py`:

```python
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from scout_scoring import median_or_none, estimate_kaufpreisfaktor


def test_median_or_none_filters_invalid_values():
    assert median_or_none([2000, 2200, 0, None, 2100]) == 2100


def test_median_or_none_empty_or_all_invalid():
    assert median_or_none([]) is None
    assert median_or_none([0, None]) is None


def test_estimate_kaufpreisfaktor_known_values():
    # median price/sqm = 2100, median rent/sqm = 8.5
    # kaufpreisfaktor = 2100 / (8.5 * 12)
    sale = [2000.0, 2200.0, 2100.0]
    rent = [8.0, 9.0, 8.5]
    result = estimate_kaufpreisfaktor(sale, rent)
    assert result == pytest.approx(2100 / (8.5 * 12), rel=1e-6)


def test_estimate_kaufpreisfaktor_missing_data_returns_none():
    assert estimate_kaufpreisfaktor([], [8.0]) is None
    assert estimate_kaufpreisfaktor([2000.0], []) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /tmp/property-investment-finder && /home/vincent/laya_venv/bin/python -m pytest tests/test_scout_scoring.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scout_scoring'`

- [ ] **Step 3: Write `src/scout_scoring.py`**

```python
"""Pure scoring math for the Scout stage of the autonomous tuning loop.

No network I/O here -- this only turns already-fetched search-result
numbers (price/sqm, rent/sqm) into an estimated kaufpreisfaktor, so a
candidate city can be ranked before spending a real detail-page fetch on
any of its listings.
"""
from __future__ import annotations

from statistics import median
from typing import Optional


def median_or_none(values: list) -> Optional[float]:
    cleaned = [v for v in values if v is not None and v > 0]
    if not cleaned:
        return None
    return median(cleaned)


def estimate_kaufpreisfaktor(
    sale_prices_per_sqm: list, rent_prices_per_sqm: list
) -> Optional[float]:
    """Rough kaufpreisfaktor estimate for a city, from cheap search-result
    data only (no detail-page fetch, no financing math).

    kaufpreisfaktor = Kaufpreis / Jahreskaltmiete. Since both price/sqm and
    rent/sqm are per-sqm, the sqm term cancels:
        kaufpreisfaktor ~= median(price/sqm) / (median(rent/sqm) * 12)

    Returns None if either side has no usable data.
    """
    med_price = median_or_none(sale_prices_per_sqm)
    med_rent = median_or_none(rent_prices_per_sqm)
    if med_price is None or med_rent is None:
        return None
    return med_price / (med_rent * 12)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /tmp/property-investment-finder && /home/vincent/laya_venv/bin/python -m pytest tests/test_scout_scoring.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
cd /tmp/property-investment-finder
git add src/scout_scoring.py tests/test_scout_scoring.py
git commit -m "$(cat <<'EOF'
feat: add scout-stage kaufpreisfaktor estimation

Pure function turning cheap search-result price/sqm + rent/sqm into a
rough kaufpreisfaktor estimate, so scripts/scout.py can rank candidate
cities without any detail-page fetches.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011mDK3TmcgpPLGPpzCaGB93
EOF
)"
```

---

## Task 4: Scout orchestration — `scripts/scout.py`

**Files:**
- Create: `scripts/scout.py`
- Depends on: `src/regions.py` (Task 2), `src/scout_scoring.py` (Task 3), `region_scouting` table (Task 1), `src/immoscout_scraper.py`'s `extract_result_json`/`parse_entries` (existing)

No unit tests here (matches this project's established convention — the real scraper is validated by hand against the live site, not in CI, since it needs network access and a real browser).

- [ ] **Step 1: Write `scripts/scout.py`**

```python
#!/usr/bin/env python3
"""Scout stage of the autonomous tuning loop -- cheap, search-JSON-only
city ranking. No detail-page (expose) fetches: only the same
resultListModel JSON the search-results scraper already parses, hit once
for sale listings (wohnung-kaufen, fixed price/size band) and once for
rental listings (wohnung-mieten, size band only) per candidate city, to
get a real median rent/sqm instead of a hardcoded guess.

Run: /home/vincent/multica-lab/venv-scrape/bin/python scripts/scout.py
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, "src")

from scrapling.fetchers import StealthyFetcher

from immoscout_scraper import extract_result_json, parse_entries
from regions import load_candidate_batch, mark_scouted
from scout_scoring import estimate_kaufpreisfaktor, median_or_none

DB_PATH = "/tmp/property-investment-finder/data/listings.db"
PRICE_MIN, PRICE_MAX = 80000, 150000
SPACE_MIN, SPACE_MAX = 30, 55


def _fetch_hits(bl_slug: str, city_slug: str, city_name: str, bl_name: str, kind: str):
    """kind: 'kaufen' or 'mieten'. Returns (entries, num_hits); ([], 0) on failure."""
    if kind == "kaufen":
        url = (
            f"https://www.immobilienscout24.de/Suche/de/{bl_slug}/{city_slug}/wohnung-kaufen"
            f"?price={PRICE_MIN}-{PRICE_MAX}&livingspace={SPACE_MIN}-{SPACE_MAX}"
        )
    else:
        url = (
            f"https://www.immobilienscout24.de/Suche/de/{bl_slug}/{city_slug}/wohnung-mieten"
            f"?livingspace={SPACE_MIN}-{SPACE_MAX}"
        )
    try:
        r = StealthyFetcher.fetch(
            url, headless=True, disable_resources=True, network_idle=True, timeout=30000
        )
    except Exception as e:
        print(f"  [{city_name}/{kind}] FETCH ERROR: {e}", file=sys.stderr)
        return [], 0
    if r.status != 200:
        print(f"  [{city_name}/{kind}] status={r.status}")
        return [], 0
    data = extract_result_json(r.html_content)
    if data is None:
        print(f"  [{city_name}/{kind}] no resultListModel found")
        return [], 0
    return parse_entries(data, city_name, bl_name)


def scout_city(bl_slug: str, city_slug: str, city_name: str, bl_name: str) -> dict:
    sale_entries, n_sale = _fetch_hits(bl_slug, city_slug, city_name, bl_name, "kaufen")
    rent_entries, n_rent = _fetch_hits(bl_slug, city_slug, city_name, bl_name, "mieten")

    sale_price_per_sqm = [
        e.price / e.living_space for e in sale_entries if e.price and e.living_space
    ]
    rent_price_per_sqm = [
        e.price / e.living_space for e in rent_entries if e.price and e.living_space
    ]

    if n_sale == 0 and n_rent == 0:
        status = "no_slug"
    elif not sale_price_per_sqm:
        status = "failed"
    else:
        status = "ok"

    return {
        "city": city_name,
        "bundesland": bl_name,
        "n_sale_hits": n_sale,
        "median_price_per_sqm": median_or_none(sale_price_per_sqm),
        "median_rent_per_sqm": median_or_none(rent_price_per_sqm),
        "est_kaufpreisfaktor": estimate_kaufpreisfaktor(sale_price_per_sqm, rent_price_per_sqm),
        "status": status,
    }


def store_scout_result(
    conn: sqlite3.Connection, bl_slug: str, city_slug: str, result: dict
) -> None:
    conn.execute(
        """
        INSERT INTO region_scouting
            (city, kreis_ags, scouted_at, n_sale_hits, median_price_per_sqm,
             median_rent_per_sqm, est_kaufpreisfaktor, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            result["city"],
            f"{bl_slug}/{city_slug}",
            datetime.now(timezone.utc).isoformat(),
            result["n_sale_hits"],
            result["median_price_per_sqm"],
            result["median_rent_per_sqm"],
            result["est_kaufpreisfaktor"],
            result["status"],
        ),
    )
    conn.commit()


def main(batch_size: int = 20) -> None:
    candidates = load_candidate_batch(batch_size=batch_size)
    if not candidates:
        print("No un-scouted candidates left in regions.yaml.")
        return
    conn = sqlite3.connect(DB_PATH)
    for bl_slug, city_slug, city_name, bl_name in candidates:
        print(f"Scouting {city_name} ({bl_name})...")
        result = scout_city(bl_slug, city_slug, city_name, bl_name)
        store_scout_result(conn, bl_slug, city_slug, result)
        print(f"  -> {result}")
    conn.close()
    mark_scouted(candidates)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke-test against the live site by hand**

Run: `cd /tmp/property-investment-finder && /home/vincent/multica-lab/venv-scrape/bin/python scripts/scout.py`
Expected: prints one `Scouting <city> (...)` + result line per candidate in the first batch (up to 20), no unhandled exceptions. Some cities may legitimately come back `status: no_slug` if the guessed city_slug doesn't exist on IS24 — that's expected and handled, not a bug to fix here.

- [ ] **Step 3: Verify the DB actually got the rows**

Run:
```bash
cd /tmp/property-investment-finder
python3 -c "
import sqlite3
conn = sqlite3.connect('data/listings.db')
rows = conn.execute('SELECT city, status, est_kaufpreisfaktor FROM region_scouting ORDER BY id DESC LIMIT 20').fetchall()
for r in rows: print(r)
"
```
Expected: one row per city just scouted, with a real `status` value and (for `status='ok'` rows) a numeric `est_kaufpreisfaktor`.

- [ ] **Step 4: Commit**

```bash
cd /tmp/property-investment-finder
git add scripts/scout.py data/listings.db
git commit -m "$(cat <<'EOF'
feat: add Scout stage (cheap, search-JSON-only city ranking)

Hits IS24's sale and rental search results for each candidate city
(no detail-page fetches) to compute a real median rent/sqm and a rough
kaufpreisfaktor estimate, stored in region_scouting for the autotune
controller to rank and promote from.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011mDK3TmcgpPLGPpzCaGB93
EOF
)"
```

---

## Task 5: Threshold search — `src/threshold_search.py`

**Files:**
- Create: `src/threshold_search.py`
- Test: `tests/test_threshold_search.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_threshold_search.py`:

```python
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from calculator import Listing, load_criteria
from threshold_search import evaluate_criteria, search_best_criteria


def _make_listings():
    """5 synthetic listings, fixed price/size (already within the 80-150k /
    30-55m2 band so purchase_price/living_space filters never reject any
    of them -- only built_year and yield should differentiate them)."""
    listings = []
    # 3 "new, good yield" listings built 2005, rent high enough for >=4.5% yield
    for i in range(3):
        listings.append(Listing(
            listing_id=f"new-{i}", price=100000, living_space=40,
            rent_monthly=450, built_year=2005, city="Leipzig", bundesland="Sachsen",
        ))
    # 2 "old, poor yield" listings built 1960, low rent
    for i in range(2):
        listings.append(Listing(
            listing_id=f"old-{i}", price=100000, living_space=40,
            rent_monthly=250, built_year=1960, city="Leipzig", bundesland="Sachsen",
        ))
    return listings


def test_evaluate_criteria_returns_mean_score_and_size():
    listings = _make_listings()
    criteria = load_criteria()
    mean_score, size = evaluate_criteria(listings, criteria)
    assert size >= 1
    assert mean_score >= 0.0


def test_search_best_criteria_prefers_built_year_cutoff_that_excludes_bad_listings():
    listings = _make_listings()
    base_criteria = load_criteria()
    param_grid = {"built_year.min": [0, 1990]}
    best_criteria, best_score, best_size = search_best_criteria(
        listings, base_criteria, param_grid, min_shortlist_size=2
    )
    # With min_shortlist_size=2, both cutoffs leave enough listings; the
    # 1990 cutoff drops the 2 low-yield 1960-built listings, raising the
    # mean score of what remains.
    assert best_criteria["built_year"]["min"] == 1990
    assert best_size == 3


def test_search_best_criteria_falls_back_when_floor_never_met():
    listings = _make_listings()
    base_criteria = load_criteria()
    param_grid = {"built_year.min": [0, 1990]}
    best_criteria, best_score, best_size = search_best_criteria(
        listings, base_criteria, param_grid, min_shortlist_size=999
    )
    assert best_size == 0
    assert best_score == 0.0
    assert best_criteria == base_criteria


def test_fixed_keys_cannot_be_tuned():
    listings = _make_listings()
    base_criteria = load_criteria()
    import pytest
    with pytest.raises(ValueError):
        search_best_criteria(
            listings, base_criteria, {"purchase_price.min": [0]}, min_shortlist_size=1
        )
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /tmp/property-investment-finder && /home/vincent/laya_venv/bin/python -m pytest tests/test_threshold_search.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'threshold_search'`

- [ ] **Step 3: Write `src/threshold_search.py`**

```python
"""Grid search over tunable (non price/size) investment criteria
thresholds.

Given an already deep-scraped set of Listing objects and a base criteria
dict (loaded from criteria.yaml), tries combinations of a small parameter
grid and returns whichever combination maximizes mean Calculator score
across the passing shortlist, subject to a minimum shortlist-size floor.

purchase_price and living_space are fixed per Vincent's explicit
instruction -- callers must not put them in param_grid; this module
refuses to tune them.
"""
from __future__ import annotations

import copy
import itertools
from typing import Any

from calculator import calculate_batch, filter_passed

FIXED_PREFIXES = ("purchase_price", "living_space")


def _set_nested(d: dict, dotted_key: str, value: Any) -> None:
    if dotted_key.startswith(FIXED_PREFIXES):
        raise ValueError(f"{dotted_key} is a fixed criterion and cannot be tuned")
    parts = dotted_key.split(".")
    node = d
    for p in parts[:-1]:
        node = node.setdefault(p, {})
    node[parts[-1]] = value


def evaluate_criteria(listings: list, criteria: dict) -> tuple[float, int]:
    """Return (mean_score_of_passing, shortlist_size) for one criteria dict."""
    results = calculate_batch(listings, criteria)
    passed = filter_passed(results)
    if not passed:
        return 0.0, 0
    mean_score = sum(r.score for r in passed) / len(passed)
    return mean_score, len(passed)


def search_best_criteria(
    listings: list,
    base_criteria: dict,
    param_grid: dict,
    min_shortlist_size: int = 20,
) -> tuple[dict, float, int]:
    """Grid search over param_grid (dotted-path -> list of candidate
    values). Returns (best_criteria, best_mean_score, best_shortlist_size).

    If no combination clears min_shortlist_size, returns
    (base_criteria, 0.0, 0) -- i.e. falls back to whatever the caller
    already had rather than silently picking a degenerate tiny shortlist.
    """
    keys = list(param_grid.keys())
    best_criteria = None
    best_score = -1.0
    best_size = 0
    for values in itertools.product(*(param_grid[k] for k in keys)):
        candidate = copy.deepcopy(base_criteria)
        for k, v in zip(keys, values):
            _set_nested(candidate, k, v)
        mean_score, size = evaluate_criteria(listings, candidate)
        if size < min_shortlist_size:
            continue
        if mean_score > best_score:
            best_score = mean_score
            best_size = size
            best_criteria = candidate
    if best_criteria is None:
        return base_criteria, 0.0, 0
    return best_criteria, best_score, best_size
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /tmp/property-investment-finder && /home/vincent/laya_venv/bin/python -m pytest tests/test_threshold_search.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
cd /tmp/property-investment-finder
git add src/threshold_search.py tests/test_threshold_search.py
git commit -m "$(cat <<'EOF'
feat: add threshold grid search over tunable criteria

Pure function reusing the existing Calculator (calculate_batch/
filter_passed) to grid-search built_year/yield/exclusions/location
thresholds against already-deep-scraped listings, maximizing mean score
subject to a minimum shortlist-size floor. purchase_price and
living_space are refused as tunable keys per Vincent's instruction.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011mDK3TmcgpPLGPpzCaGB93
EOF
)"
```

---

## Task 6: Controller — `scripts/autotune.py`

**Files:**
- Create: `scripts/autotune.py`
- Test: `tests/test_autotune_state.py` (only the pure/DB-query helpers; the orchestration functions that shell out to the scraper/git are integration-level, matching this project's no-live-network-tests convention)

- [ ] **Step 1: Write the failing tests for the testable helpers**

Create `tests/test_autotune_state.py`:

```python
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, "scripts")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from autotune import get_state, should_stop, rank_scouted_cities, NON_IMPROVING_STOP_AFTER


def _fresh_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.executescript(open("schema.sql").read())
    conn.commit()
    return conn, path


def test_should_stop_true_at_threshold():
    assert should_stop(NON_IMPROVING_STOP_AFTER) is True
    assert should_stop(NON_IMPROVING_STOP_AFTER - 1) is False


def test_get_state_no_runs_yet():
    conn, path = _fresh_db()
    state = get_state(conn)
    assert state == {"best_score": 0.0, "non_improving_streak": 0}
    conn.close()
    os.unlink(path)


def test_get_state_tracks_best_promoted_score_and_streak():
    conn, path = _fresh_db()
    conn.execute(
        "INSERT INTO tuning_runs (cycle_at, preset_json, shortlist_size, mean_score, promoted, source) "
        "VALUES ('t1', '{}', 30, 40.0, 1, 'autotune')"
    )
    conn.execute(
        "INSERT INTO tuning_runs (cycle_at, preset_json, shortlist_size, mean_score, promoted, source) "
        "VALUES ('t2', '{}', 30, 38.0, 0, 'autotune')"
    )
    conn.execute(
        "INSERT INTO tuning_runs (cycle_at, preset_json, shortlist_size, mean_score, promoted, source) "
        "VALUES ('t3', '{}', 30, 39.0, 0, 'autotune')"
    )
    conn.commit()
    state = get_state(conn)
    assert state["best_score"] == 40.0
    assert state["non_improving_streak"] == 2
    conn.close()
    os.unlink(path)


def test_rank_scouted_cities_orders_by_kaufpreisfaktor_ascending():
    conn, path = _fresh_db()
    conn.execute(
        "INSERT INTO region_scouting (city, kreis_ags, scouted_at, n_sale_hits, "
        "median_price_per_sqm, median_rent_per_sqm, est_kaufpreisfaktor, status) "
        "VALUES ('Cheap City', 'x/y', 't', 10, 2000, 15, 11.1, 'ok')"
    )
    conn.execute(
        "INSERT INTO region_scouting (city, kreis_ags, scouted_at, n_sale_hits, "
        "median_price_per_sqm, median_rent_per_sqm, est_kaufpreisfaktor, status) "
        "VALUES ('Expensive City', 'a/b', 't', 10, 3000, 8, 31.25, 'ok')"
    )
    conn.execute(
        "INSERT INTO region_scouting (city, kreis_ags, scouted_at, n_sale_hits, "
        "median_price_per_sqm, median_rent_per_sqm, est_kaufpreisfaktor, status) "
        "VALUES ('Failed City', 'c/d', 't', 0, NULL, NULL, NULL, 'failed')"
    )
    conn.commit()
    top = rank_scouted_cities(conn, top_k=5)
    assert [r["city"] for r in top] == ["Cheap City", "Expensive City"]
    conn.close()
    os.unlink(path)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /tmp/property-investment-finder && /home/vincent/laya_venv/bin/python -m pytest tests/test_autotune_state.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'autotune'`

- [ ] **Step 3: Write `scripts/autotune.py`**

```python
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
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, "src")

import yaml

from calculator import load_criteria
from regions import add_active, load_candidate_batch, load_regions

REPO_DIR = "/tmp/property-investment-finder"
DB_PATH = f"{REPO_DIR}/data/listings.db"
CRITERIA_PATH = f"{REPO_DIR}/criteria.yaml"
TUNING_HISTORY_PATH = f"{REPO_DIR}/data/tuning_history.md"

TOP_K_PROMOTE = 5
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


def promote_to_deep_dive(top_cities: list) -> None:
    """Add the given cities to regions.yaml's active list, then run the
    existing scrape -> import chain so they get real listing data."""
    for row in top_cities:
        bl_slug, city_slug = row["kreis_ags"].split("/", 1)
        add_active(bl_slug, city_slug, row["city"], row["bundesland"])
    if not top_cities:
        return
    subprocess.run(
        ["/home/vincent/multica-lab/venv-scrape/bin/python", "src/immoscout_scraper.py"],
        check=True, cwd=REPO_DIR,
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

    sys.path.insert(0, REPO_DIR)
    from run_v1_pipeline import load_listings  # existing loader, unchanged

    listings = load_listings(conn)
    base_criteria = load_criteria(CRITERIA_PATH)

    from threshold_search import search_best_criteria
    best_criteria, mean_score, shortlist_size = search_best_criteria(
        listings, base_criteria, PARAM_GRID, MIN_SHORTLIST_SIZE
    )

    promoted = mean_score > state["best_score"] + IMPROVEMENT_MARGIN
    cycle_at = datetime.now(timezone.utc).isoformat()
    commit_hash = None
    if promoted:
        with open(CRITERIA_PATH, "w", encoding="utf-8") as f:
            yaml.dump(best_criteria, f, allow_unicode=True, sort_keys=False)
        _git("add", "criteria.yaml", "regions.yaml")
        _git(
            "commit", "-m",
            f"autotune: new best preset (mean score {mean_score:.2f}, shortlist {shortlist_size})\n\n"
            "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>\n"
            "Claude-Session: https://claude.ai/code/session_011mDK3TmcgpPLGPpzCaGB93",
        )
        commit_hash = _git("rev-parse", "HEAD")
        _git("push", "origin", "main")

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
    print(f"Cycle done: mean_score={mean_score:.2f} shortlist_size={shortlist_size} promoted={promoted}")


if __name__ == "__main__":
    run_cycle()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /tmp/property-investment-finder && /home/vincent/laya_venv/bin/python -m pytest tests/test_autotune_state.py -v`
Expected: 4 passed

- [ ] **Step 5: Create the (initially empty-bodied) `data/tuning_history.md`**

```bash
cd /tmp/property-investment-finder
cat > data/tuning_history.md <<'EOF'
# Autotune history

Append-only log of every autotune / LLM-analyst cycle. See
docs/superpowers/specs/2026-09-26-autonomous-filter-tuning-design.md
for what this loop does and why.
EOF
```

- [ ] **Step 6: Run the full test suite one more time**

Run: `cd /tmp/property-investment-finder && /home/vincent/laya_venv/bin/python -m pytest tests/ -q`
Expected: all previous tests plus these new ones pass, none broken.

- [ ] **Step 7: Commit**

```bash
cd /tmp/property-investment-finder
git add scripts/autotune.py tests/test_autotune_state.py data/tuning_history.md
git commit -m "$(cat <<'EOF'
feat: add autotune controller (one bounded cycle per invocation)

Scouts a batch of candidate cities, promotes the top-K by estimated
kaufpreisfaktor to real deep-scraping, grid-searches tunable thresholds
against the accumulated deep-scraped pool, and commits/pushes
criteria.yaml + regions.yaml when it finds something better than the
last promoted preset by more than a small margin. Stops itself after
3 consecutive non-improving cycles.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011mDK3TmcgpPLGPpzCaGB93
EOF
)"
```

---

## Task 7: Schedule the mechanical loop as a Multica autopilot

**Files:** none (Multica configuration only)

- [ ] **Step 1: Create the autopilot**

```bash
multica autopilot create \
  --title "Property Investment Finder — Autotune Cycle" \
  --agent "Qwen-Delegate" \
  --mode run_only \
  --project d395034a-c7dc-4b71-91b9-6afe44a34e84 \
  --description "$(cat <<'EOF'
Run exactly one cycle of the autonomous filter/region tuning loop:
cd /tmp/property-investment-finder && git pull --ff-only && /home/vincent/laya_venv/bin/python scripts/autotune.py
Report the printed cycle summary line. Do not modify anything else in the repo.
EOF
)"
```

- [ ] **Step 2: Check the exact scheduling flags for this Multica version**

Run: `multica autopilot trigger-add --help`
(Flags vary by Multica version — read the actual output before running the next step; don't guess.)

- [ ] **Step 3: Add a recurring schedule trigger**

Using whatever cron/interval flag Step 2 showed, add a trigger that fires periodically (e.g. every 4-6 hours — frequent enough to make progress, infrequent enough to respect the per-cycle scrape budget). Record the exact command actually used in the PR/commit description for this task, since the flags aren't hardcoded here.

- [ ] **Step 4: Manually trigger one run to verify the whole chain works end-to-end**

```bash
multica autopilot trigger <autopilot-id>
```
Then check `data/tuning_history.md` and the `tuning_runs` table got a new entry, and (if promoted) that `criteria.yaml` changed and was pushed.

---

## Task 8: LLM analyst layer

**Files:** none (Multica configuration only)

- [ ] **Step 1: Create the LLM analyst autopilot**

```bash
multica autopilot create \
  --title "Property Investment Finder — LLM Analyst" \
  --agent "Qwen-Delegate" \
  --mode create_issue \
  --project d395034a-c7dc-4b71-91b9-6afe44a34e84 \
  --issue-title-template "Autotune review {{date}}" \
  --description "$(cat <<'EOF'
Read /tmp/property-investment-finder/data/tuning_history.md, the
tuning_runs and region_scouting tables in data/listings.db, the current
criteria.yaml/regions.yaml, and data/v1_shortlist.md. Look for things a
pure numeric grid search would miss: e.g. a region that scores well
numerically but whose listings keep tripping the same Judge risk flag,
a threshold combination worth trying that the grid search hasn't
reached, or a data-quality issue like the non-apartment listings found
earlier in this project. If you find a concrete, justified change, make
it (edit criteria.yaml/regions.yaml), append an entry to
data/tuning_history.md tagged "[LLM analyst]" explaining why, and
INSERT a row into tuning_runs with source='llm_analyst'. Commit and push
to main. If nothing concrete is found, say so in the issue and change
nothing -- do not make a change just to have something to report.
EOF
)"
```

- [ ] **Step 2: Add a schedule trigger**

Same as Task 7 Step 2-3: check `multica autopilot trigger-add --help` for this Multica version's exact flags, then add a trigger firing daily for the first ~2 weeks. Note the reduction to every 2-3 days as a manual follow-up (`multica autopilot trigger-update`) once the initial period has passed — this isn't automated by this plan, it's a calendar reminder for whoever's running this.

- [ ] **Step 3: Verify**

Run: `multica autopilot list --project d395034a-c7dc-4b71-91b9-6afe44a34e84 --output json`
Expected: both the Task 7 and Task 8 autopilots listed with a trigger attached.

---

## Self-review notes

- **Spec coverage:** Scout stage (Task 4), Deep-dive promotion (Task 6's `promote_to_deep_dive`), threshold search (Task 5), fixed price/size enforcement (Task 5's `FIXED_PREFIXES` + test), audit trail (`tuning_runs` + `tuning_history.md`, Tasks 1 & 6), plateau stop rule (Task 6's `should_stop`/`NON_IMPROVING_STOP_AFTER`), full autonomy / auto-commit (Task 6's `run_cycle`), Multica autopilot scheduling (Task 7), LLM analyst layer (Task 8) — all covered.
- **Out of scope items from the spec** (UI/dashboard, bandit algorithms) are intentionally not tasked here, matching the spec's own "Out of scope" section.
- **Known follow-up, not blocking:** Task 7/8 Step 2 in both tasks depends on checking real CLI flags at execution time rather than a flag guessed here, since `multica autopilot create --help` didn't show a schedule flag directly (it's on `trigger-add`) and this plan wasn't able to inspect that subcommand's flags during writing.
