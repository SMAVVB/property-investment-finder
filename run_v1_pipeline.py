#!/usr/bin/env python3
"""
Property Investment Finder — v1 end-to-end runner.

Loads real scraped listings from data/listings.db, runs the Calculator
(Phase 1) against all of them, runs the Laya Judge (Phase 4-interim) against
the ones with real description text, stores both into financials/judgments,
and prints a ranked shortlist.

This is glue code run directly by hand for the first end-to-end pass --
not a new agent ticket, given the source data only just became consistent
(THE-514 schema fix landed minutes ago).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.calculator import Listing, load_criteria, calculate
from src.judge import run_judge, store_judgments

DB_PATH = str(PROJECT_ROOT / "data" / "listings.db")
CRITERIA_PATH = str(PROJECT_ROOT / "criteria.yaml")


def load_rent_index(conn: sqlite3.Connection) -> dict[str, float]:
    """kreis_ags -> rent_index_eur_m2, for listings with no real rent_monthly."""
    cur = conn.cursor()
    cur.execute("SELECT kreis_ags, rent_index_eur_m2 FROM location WHERE rent_index_eur_m2 IS NOT NULL")
    return {k: v for k, v in cur.fetchall()}


def load_listings(conn: sqlite3.Connection) -> list[Listing]:
    cur = conn.cursor()
    cur.execute("""
        SELECT listing_id, price, living_space, rent_monthly, rooms, floor,
               built_year, condition, plz, city, kreis_ags, bundesland, address,
               latitude, longitude, is_erbpacht, is_vacation, is_auction,
               is_care_apartment, is_social_binding, property_type, url,
               scraped_at, raw_data
        FROM listing
    """)
    listings = []
    for row in cur.fetchall():
        (listing_id, price, living_space, rent_monthly, rooms, floor, built_year,
         condition, plz, city, kreis_ags, bundesland, address, latitude, longitude,
         is_erbpacht, is_vacation, is_auction, is_care_apartment, is_social_binding,
         property_type, url, scraped_at, raw_data) = row
        listings.append((Listing(
            listing_id=listing_id,
            price=price or 0.0,
            living_space=living_space or 0.0,
            rent_monthly=rent_monthly or 0.0,
            rooms=rooms or 0,
            floor=floor or 0,
            built_year=built_year or 0,
            condition=condition or "unknown",
            plz=plz or "",
            city=city or "",
            kreis_ags=kreis_ags,
            bundesland=bundesland or "",
            address=address or "",
            latitude=latitude,
            longitude=longitude,
            is_erbpacht=bool(is_erbpacht),
            is_vacation=bool(is_vacation),
            is_auction=bool(is_auction),
            is_care_apartment=bool(is_care_apartment),
            is_social_binding=bool(is_social_binding),
            property_type=property_type or "apartment",
            url=url or "",
            scraped_at=scraped_at or "",
        ), raw_data or ""))
    return listings


def estimate_missing_rents(listings: list, rent_index: dict[str, float]) -> int:
    """Fill in rent_monthly (in place) for any (Listing, raw_data) pair that
    doesn't already have it, using size x local kreis_ags rent index.
    Returns how many listings got an estimate. Shared by main() below and by
    scripts/autotune.py -- both need this before running the Calculator,
    otherwise every listing with no scraped rent_monthly shows a 0 gross
    yield and fails every yield-based filter regardless of any other
    criteria being tuned.

    Build-plan fallback: size x local rent index when not currently let.
    No separate Mietspiegel figure available in location_data.csv yet, so
    the "+10% cap" from the build plan can't be applied here -- documented
    gap, not silently ignored.
    """
    estimated = 0
    for listing, _raw in listings:
        if not listing.rent_monthly and listing.kreis_ags in rent_index and listing.living_space:
            listing.rent_monthly = round(listing.living_space * rent_index[listing.kreis_ags], 2)
            estimated += 1
    return estimated


def store_financials(conn: sqlite3.Connection, result) -> None:
    """Write only the financials row (schema.sql) -- never touches `listing`.

    src.calculator.store_result() also rewrites the `listing` row and blanks
    `title` to "" and expects geo-detail columns THE-514's migration never
    added -- avoided here on purpose.
    """
    conn.execute("""
        INSERT OR REPLACE INTO financials (
            listing_id, purchase_costs_eur, all_in_costs, annual_rent,
            gross_yield, net_yield, kaufpreisfaktor,
            loan_amount, monthly_interest, monthly_amortization,
            total_monthly_mortgage, monthly_nk, monthly_nk_non_alloc,
            annual_loan_costs, monthly_surplus, monthly_top_up,
            equity_required, renovation_budget,
            outlier_tier, stress_test_passed, stress_monthly_surplus,
            stress_6month_loss, score, passed_filter, rejection_reasons
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        result.listing_id, result.purchase_costs_eur, result.all_in_costs,
        result.annual_rent, result.gross_yield, result.net_yield,
        result.kaufpreisfaktor, result.loan_amount, result.monthly_interest,
        result.monthly_amortization, result.total_monthly_mortgage,
        result.monthly_nk, result.monthly_nk_non_alloc, result.annual_loan_costs,
        result.monthly_surplus, result.monthly_top_up, result.equity_required,
        result.renovation_budget, result.outlier_tier,
        1 if result.stress_test_passed else 0, result.stress_monthly_surplus,
        result.stress_6month_loss, result.score,
        1 if result.passed_filter else 0, json.dumps(result.rejection_reasons),
    ))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--judge", choices=["laya", "finetuned"], default="laya",
                         help="laya: original zero-shot Laya judge (default, kept for comparison). "
                              "finetuned: linear heads trained on ground-truth labels "
                              "(models/finetune_v1/) -- see scripts/train_finetune.py.")
    args = parser.parse_args()

    if args.judge == "finetuned":
        from src.finetuned_judge import run_judge_finetuned as run_judge_impl
        judge_model_version = "finetuned-v1"
    else:
        run_judge_impl = run_judge
        judge_model_version = "laya-0.1.0"

    criteria = load_criteria(CRITERIA_PATH)
    # financials/judgments already match schema.sql (fixed by hand before this run);
    # avoid calc_init_db's CREATE TABLE IF NOT EXISTS + CREATE INDEX combo, which
    # fails if an older/stale table shape is ever present again.
    conn = sqlite3.connect(DB_PATH)

    listings = load_listings(conn)
    print(f"Loaded {len(listings)} listings from {DB_PATH}")

    rent_index = load_rent_index(conn)
    estimated = estimate_missing_rents(listings, rent_index)
    print(f"Estimated rent for {estimated}/{len(listings)} listings via kreis_ags rent_index "
          f"(no rent_monthly in scrape + kreis_ags matched location table)")

    calc_results = {}
    for listing, _raw in listings:
        result = calculate(listing, criteria)
        store_financials(conn, result)
        calc_results[listing.listing_id] = result
    conn.commit()
    print(f"Calculator ran on {len(calc_results)} listings, stored in financials table")

    judged = 0
    judge_errors = 0
    for listing, raw in listings:
        if len(raw) <= 100:
            continue
        try:
            jr = run_judge_impl(raw)
            store_judgments(conn, listing.listing_id, jr, judge_model_version)
            judged += 1
        except Exception as e:
            judge_errors += 1
            print(f"  judge failed for {listing.listing_id}: {e}", file=sys.stderr)
    conn.commit()
    print(f"Judge ran on {judged} listings ({judge_errors} errors), stored in judgments table")

    # Ranked shortlist: passed_filter first, then by score desc
    ranked = sorted(
        calc_results.items(),
        key=lambda kv: (not kv[1].passed_filter, -kv[1].score),
    )

    flag_questions = ["f_sonderumlage", "f_milieuschutz", "f_erbpacht", "f_staffelmiete",
                      "f_renovation", "f_heating_fossil", "f_small_weg", "f_tenant_issue"]
    cur = conn.cursor()

    def risk_flags(listing_id: str) -> str:
        q = ",".join("?" for _ in flag_questions)
        cur.execute(
            f"select question_id from judgments where listing_id=? and answer='true' and question_id in ({q})",
            [listing_id] + flag_questions,
        )
        return ", ".join(r[0] for r in cur.fetchall())

    lines = []
    lines.append("# Property Investment Finder — v1 Shortlist")
    lines.append("")
    lines.append(f"{len(listings)} real listings (Kleinanzeigen + poschmann-immobilien.com), "
                  f"{judged} judged by {'the fine-tuned judge (models/finetune_v1)' if args.judge == 'finetuned' else 'Laya (zero-shot)'}, "
                  f"ranked by score / passed_filter.")
    if args.judge == "finetuned":
        lines.append("")
        lines.append("Judge risk flags below come from linear heads trained on 360 ground-truth labels "
                      "(scripts/train_finetune.py). f_sonderumlage, f_milieuschutz, f_staffelmiete, "
                      "f_wg_layout, f_erbpacht, f_tenant_issue, f_small_weg had too few positive "
                      "examples (<15) to train reliably and currently always predict false "
                      "(majority-class fallback, see models/finetune_v1/metadata.json) -- known gap, "
                      "revisit once more labels exist. f_renovation and f_heating_fossil are trained "
                      "(held-out F1 0.21 and 0.39 respectively -- real signal, not perfect).")
    lines.append("")
    lines.append("| # | listing_id | city | price | m2 | rent/mo | kaufpreisfaktor | tier | passed | score | reasons | risk_flags |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for i, (lid, r) in enumerate(ranked, 1):
        listing = next(l for l, _ in listings if l.listing_id == lid)
        reasons = "; ".join(r.rejection_reasons) if r.rejection_reasons else ""
        lines.append(
            f"| {i} | {lid} | {listing.city or '?'} | {listing.price:.0f} | "
            f"{listing.living_space:.0f} | {listing.rent_monthly:.0f} | "
            f"{r.kaufpreisfaktor:.1f} | {r.outlier_tier} | "
            f"{'YES' if r.passed_filter else 'no'} | {r.score:.1f} | {reasons} | {risk_flags(lid)} |"
        )

    out = "\n".join(lines)
    out_path = PROJECT_ROOT / "data" / "v1_shortlist.md"
    out_path.write_text(out, encoding="utf-8")
    print(f"\nWrote shortlist to {out_path}")
    print("\n" + out)

    conn.close()


if __name__ == "__main__":
    main()
