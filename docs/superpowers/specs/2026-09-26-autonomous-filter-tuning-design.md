# Autonomous Filter Tuning — Design

## Problem

`criteria.yaml` thresholds (yield floor, built_year, exclusions, location
must-haves, target regions) were all picked by hand, with no real feedback
loop on whether they're any good. Vincent has said outright he doesn't know
if the current filters are correct or whether they're finding significant
opportunities — he wants the system itself to search the filter/region space,
evaluate what it finds, and keep adjusting, rather than him guessing at
numbers.

## Fixed vs. tunable

- **Fixed, never touched by the loop:** `purchase_price` (80k-150k),
  `living_space` (30-55m² allowed, 35-50m² target). Vincent's explicit
  instruction — a preset that "wins" by drifting into a €500k penthouse is
  not a valid result regardless of its KPIs.
- **Tunable by the loop:** target regions/cities (any city in Germany, not
  just the current Sachsen/Sachsen-Anhalt/Brandenburg/Berlin set),
  `built_year` cutoff, energy class, yield thresholds, exclusions, city-
  specific limits, location must-haves (station distance, travel time).

## Objective function

Reuse the Calculator's existing `_compute_score()` (0-100, already
yield/return-weighted: gross yield 25%, net yield 20%, kaufpreisfaktor 20%,
stress test 15%, top-up 10%, location 10% — no new scoring logic needed).

Preset objective = **mean `score` across the passing shortlist**, subject to
a **minimum shortlist-size floor** (default 20) so the optimizer can't "win"
by shrinking to one perfect listing. A preset that fails the floor is
rejected outright regardless of its mean score.

## Architecture — two-stage funnel

### Stage 1: Scout (cheap, wide)

New `scripts/scout.py`. For a candidate city: one search-JSON-only fetch
against IS24's `wohnung-kaufen` (sale) listings for the fixed price/size
band, and one against `wohnung-mieten` (rental) listings in the same size
band, to get a real median rent/m² for that city instead of the current
3-bucket guess (`berlin`/`brandenburg`/`other` in `criteria.yaml`). No
expose-page (detail) fetches at this stage — same cost profile as the
existing search-results pagination, nothing new.

Writes to a new `region_scouting` table (city, kreis_ags, scouted_at,
n_sale_hits, median_price_per_sqm, median_rent_per_sqm,
est_kaufpreisfaktor, status: `ok`/`failed`/`no_slug`).

Candidate city list: a static seed list of ~400 German cities/towns
(population-ranked), consumed a batch at a time per cycle, prioritized
toward cities near already-good-scoring regions once some data exists.

### Stage 2: Deep dive (expensive, narrow)

The existing pipeline, unchanged: `immoscout_scraper.py` (now driven by a
`regions.yaml` config instead of the hardcoded `TRACKS` Python list, so the
loop can add/remove regions programmatically) → `import_immoscout.py` →
Calculator → fine-tuned Judge (`src/finetuned_judge.py`, from today's
earlier work — frozen bge-m3 embeddings + trained linear heads, no LLM
inference cost per listing).

Only the top-K scouted cities (by `est_kaufpreisfaktor`, default K=5) get
promoted to this stage per cycle.

### Controller: `scripts/autotune.py`

One cycle:
1. Scout a batch of not-yet-scouted cities (default batch size: 20).
2. Rank all scouted cities by `est_kaufpreisfaktor`.
3. Promote current top-K to deep-dive (real scrape + import + Calculator +
   Judge).
4. On the accumulated deep-scraped pool, hill-climb/grid-search over the
   tunable non-price/size thresholds to maximize the objective function.
5. If this cycle's best preset beats the previous best by more than a
   small margin (default 2 points mean score, configurable), commit
   `criteria.yaml` + `regions.yaml` + regenerated `data/v1_shortlist.md`
   to git. Otherwise, this cycle counts as non-improving.

**Stopping rule:** after **3 consecutive non-improving cycles**, the loop
halts itself and reports — this is "continuous until it plateaus."

**Safety cap:** a hard per-cycle limit on scrape requests (scout +
deep-dive combined), to bound worst-case load against IS24 and reduce
bot-detection/ban risk. Configurable, generous default.

**Runs as:** a Multica scheduled autopilot, not one long-lived process —
each cycle is a bounded, resumable unit. State (scouted cities so far,
current best preset, non-improving-cycle counter) lives in the DB, so a
crashed/killed cycle resumes cleanly.

**Full autonomy:** per Vincent's explicit instruction, the loop commits
`criteria.yaml`/`regions.yaml` changes and triggers real scrapes on its own
— no approval gate. It reports what it did after the fact via the audit
trail below, it does not ask first.

### Audit trail

New `tuning_runs` table (cycle timestamp, preset tried as JSON, shortlist
size, mean score, promoted/rejected, git commit hash if committed) plus a
human-readable `data/tuning_history.md`, appended and committed alongside
every `criteria.yaml`/`regions.yaml` change, so every autonomous decision
has a plain-English trail Vincent can read without querying the DB.

### LLM analyst layer

On top of the mechanical hill-climb, a separate scheduled task (Claude,
via a Multica scheduled cloud agent) reads `data/tuning_history.md`, the
`tuning_runs` table, the current shortlist, and `criteria.yaml`/
`regions.yaml`, and produces concrete recommendations — catching things a
pure numeric optimizer would miss (e.g. a region that scores well
numerically but whose descriptions keep tripping the same Judge red flag,
or a threshold combination worth trying that the grid search hasn't
reached yet).

Consistent with "full autonomy": its recommendations are applied the same
way as the mechanical optimizer's — committed to git, logged to
`tuning_history.md` tagged `[LLM analyst]` so they're distinguishable from
the mechanical optimizer's own changes in the audit trail.

**Cadence:** daily for the first ~2 weeks, then reduced to every 2-3 days.
Implemented as a Multica scheduled autopilot/cron, adjustable without code
changes.

## Error handling

- Per-city fetch failures (WAF challenge, timeout, 404 slug) are isolated
  — logged as `failed` in `region_scouting`/deep-dive results, retried
  next cycle, don't abort the cycle.
- If failures cluster across multiple cities in a short window (signal of
  a rate-limit/ban rather than one bad city), the cycle aborts early and
  backs off rather than grinding through the rest of the candidate batch.
- Every committed change is a normal git commit — reverting a bad preset
  is `git revert`, nothing bespoke.

## Testing

- `scout.py`'s scoring math (median price/rent → `est_kaufpreisfaktor`)
  gets unit tests against synthetic search-JSON fixtures, matching the
  existing style in `tests/test_calculator.py`.
- The threshold hill-climb/grid-search gets unit tests against a small
  fixed synthetic dataset with a known best answer.
- No live-network tests (matches existing project convention — the real
  scraper is validated by hand, not in CI).

## Out of scope for this pass

- Changing the fixed price/size band.
- Building a UI/dashboard for the tuning history (the markdown file +
  DB is sufficient for now).
- Deeper exploration algorithms (bandits/UCB) beyond top-K-by-score
  promotion — revisit only if naive ranking turns out to waste scrape
  budget in practice.
