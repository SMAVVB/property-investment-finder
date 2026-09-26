#!/usr/bin/env python3
"""
run_v1_pipeline.py — Run the full investment analysis pipeline.

Reads listings from the database, runs financial calculations,
and generates the v1_shortlist.md report.
"""

import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

import sqlite3
import yaml
from datetime import datetime, timezone
from src.calculator import Listing, calculate, calculate_batch, filter_passed, sort_by_score


def load_criteria():
    """Load investment criteria from criteria.yaml."""
    with open(PROJECT_ROOT / "criteria.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_pipeline():
    """Run the full pipeline: calculate financials for all listings."""
    # Load criteria
    criteria = load_criteria()
    
    # Connect to database
    db_path = PROJECT_ROOT / "data" / "listings.db"
    conn = sqlite3.connect(str(db_path))
    
    # Read all listings
    rows = conn.execute("""
        SELECT listing_id, title, price, living_space, rent_monthly, rent_per_sqm,
               rooms, floor, built_year, condition, plz, city, bundesland, address,
               latitude, longitude, is_erbpacht, is_vacation, is_auction,
               is_care_apartment, is_social_binding, property_type, url, scraped_at,
               raw_data
        FROM listing
    """).fetchall()
    
    print(f"Loaded {len(rows)} listings from database")
    
    # Convert to Listing objects
    listing_objs = []
    for row in rows:
        listing_objs.append(Listing(
            listing_id=row[0],
            price=row[2],
            living_space=row[3],
            rent_monthly=row[4] or 0.0,
            rooms=row[5] or 0,
            floor=row[6] or 0,
            built_year=row[7] or 0,
            condition=row[8] or "unknown",
            plz=row[9] or "",
            city=row[10] or "",
            bundesland=row[11] or "",
            address=row[12] or "",
            url=row[21] or "",
        ))
    
    # Calculate financials for all listings
    results = calculate_batch(listing_objs, criteria)
    
    # Store financials in database and attach listing info to results
    for result, listing in zip(results, listing_objs):
        conn.execute("""
            INSERT OR REPLACE INTO financials (
                listing_id, purchase_costs_eur, all_in_costs, annual_rent,
                gross_yield, net_yield, kaufpreisfaktor, loan_amount,
                monthly_interest, monthly_amortization, total_monthly_mortgage,
                monthly_nk, monthly_nk_non_alloc, annual_loan_costs,
                monthly_surplus, monthly_top_up, equity_required,
                renovation_budget, outlier_tier, stress_test_passed,
                stress_monthly_surplus, stress_6month_loss, score,
                passed_filter, rejection_reasons
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            result.listing_id,
            result.purchase_costs_eur,
            result.all_in_costs,
            result.annual_rent,
            result.gross_yield,
            result.net_yield,
            result.kaufpreisfaktor,
            result.loan_amount,
            result.monthly_interest,
            result.monthly_amortization,
            result.total_monthly_mortgage,
            result.monthly_nk,
            result.monthly_nk_non_alloc,
            result.annual_loan_costs,
            result.monthly_surplus,
            result.monthly_top_up,
            result.equity_required,
            result.renovation_budget,
            result.outlier_tier,
            result.stress_test_passed,
            result.stress_monthly_surplus,
            result.stress_6month_loss,
            result.score,
            result.passed_filter,
            json.dumps(result.rejection_reasons) if result.rejection_reasons else None,
        ))
    conn.commit()
    conn.close()
    
    # Attach listing info to results for report generation
    listing_map = {l.listing_id: l for l in listing_objs}
    for r in results:
        if r.listing_id in listing_map:
            l = listing_map[r.listing_id]
            r.price = l.price
            r.living_space = l.living_space
            r.rooms = l.rooms
            r.city = l.city
            r.bundesland = l.bundesland
            r.address = l.address
            r.url = l.url
            r.plz = l.plz
    
    # Generate shortlist report
    generate_shortlist(results, criteria)
    
    return results


def generate_shortlist(results, criteria):
    """Generate v1_shortlist.md report."""
    # Filter passed listings
    passed = filter_passed(results)
    
    # Sort by score
    passed = sort_by_score(passed)
    
    output_path = PROJECT_ROOT / "data" / "v1_shortlist.md"
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# Property Investment Finder — v1 Shortlist\n")
        f.write(f"\nGenerated: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"\n## Summary\n")
        f.write(f"- Total listings analyzed: {len(results)}\n")
        f.write(f"- Listings passing all filters: {len(passed)}\n")
        f.write(f"- Filter criteria: {criteria['purchase_price']['min']}-{criteria['purchase_price']['max']}€ purchase price, "
                f"{criteria['living_space']['allowed_min']}-{criteria['living_space']['allowed_max']}m²\n")
        
        if passed:
            f.write(f"\n## Top Candidates\n")
            for i, r in enumerate(passed[:10], 1):
                f.write(f"\n### {i}. {r.listing_id}\n")
                f.write(f"- **Price:** {r.price:,.0f}€\n")
                f.write(f"- **Area:** {r.living_space:.0f}m²\n")
                f.write(f"- **Rooms:** {r.rooms}\n")
                f.write(f"- **Gross Yield:** {r.gross_yield*100:.1f}%\n")
                f.write(f"- **Net Yield:** {r.net_yield*100:.1f}%\n")
                f.write(f"- **Monthly Top-up:** {r.monthly_top_up:.0f}€\n")
                f.write(f"- **Score:** {r.score:.1f}/100\n")
                f.write(f"- **Outlier Tier:** {r.outlier_tier}\n")
                f.write(f"- **URL:** {r.url}\n")
        else:
            f.write(f"\n**No listings passed all filters.**\n")
            f.write(f"\n## All Analyzed Listings\n")
            sorted_results = sort_by_score(results)
            for i, r in enumerate(sorted_results[:20], 1):
                f.write(f"\n{i}. {r.listing_id} — {r.price:,.0f}€ | {r.living_space:.0f}m² | "
                        f"Score: {r.score:.1f} | Tier: {r.outlier_tier}")
                if r.rejection_reasons:
                    f.write(f" | Rejected: {', '.join(r.rejection_reasons[:3])}")
                f.write("\n")
    
    print(f"\nShortlist written to {output_path}")
    print(f"Total analyzed: {len(results)}")
    print(f"Passed filters: {len(passed)}")


if __name__ == "__main__":
    run_pipeline()
