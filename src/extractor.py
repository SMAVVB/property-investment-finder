#!/usr/bin/env python3
"""
Property Investment Finder — Extractor (Phase 2)

Extracts structured property data from listing pages on eBay Kleinanzeigen.
Uses Scrapling's Fetcher for fast HTTP fetching and parses the embedded
structured data (ad_attributes, ad_price, etc.) from the HTML.

Extracted fields (matching schema.sql listing table):
  - listing_id, title, price, living_space, rent_monthly, rooms, floor
  - built_year, condition, location_city, location_state
  - is_erbpacht, is_vacation, is_auction, is_care_apartment, is_social_binding
  - url, scraped_at, raw_data

Usage:
  python -m src.extractor --input listings.json --output extracted.json
  python -m src.extractor --url "https://..." --verbose
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import random
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ExtractedListing:
    """Structured property data extracted from a listing page."""
    listing_id: str = ""
    title: str = ""
    price: float = 0.0
    living_space: float = 0.0
    rent_monthly: float = 0.0
    rent_per_sqm: float = 0.0
    rooms: int = 0
    floor: int = 0
    built_year: int = 0
    condition: str = "unknown"
    location_city: str = ""
    location_state: str = ""
    location_address: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_erbpacht: bool = False
    is_vacation: bool = False
    is_auction: bool = False
    is_care_apartment: bool = False
    is_social_binding: bool = False
    property_type: str = "apartment"
    url: str = ""
    scraped_at: str = ""
    raw_data: str = ""
    source: str = "kleinanzeigen"
    description: str = ""
    features: list = field(default_factory=list)
    extraction_success: bool = False
    extraction_notes: str = ""


# ---------------------------------------------------------------------------
# Kleinanzeigen Page Extractor (Scrapling-based)
# ---------------------------------------------------------------------------

class KleinanzeigenExtractor:
    """
    Extract structured data from Kleinanzeigen listing pages.

    Uses Scrapling's Fetcher for HTTP fetching and parses the embedded
    structured data (ad_attributes, ad_price, etc.) from the HTML.
    """

    def __init__(self, slow_mo: float = 3.0):
        self.slow_mo = slow_mo
        self._import_scrapling()

    def _import_scrapling(self):
        """Import Scrapling."""
        from scrapling.fetchers import Fetcher as SF
        self._Fetcher = SF

    def _wait(self, min_ms: int = 3000, max_ms: int = 5000):
        """Random wait for rate-limiting."""
        time.sleep(random.uniform(min_ms / 1000, max_ms / 1000))

    def _generate_listing_id(self, url: str) -> str:
        """Generate a unique listing ID from URL."""
        match = re.search(r'/anzeige/([^/]+)/', url)
        if match:
            return f"klz-{match.group(1)}"
        return f"klz-{hashlib.md5(url.encode()).hexdigest()[:12]}"

    def _parse_attributes(self, attrs_str: str) -> dict:
        """Parse Kleinanzeigen ad_attributes string."""
        attrs = {}
        if not attrs_str:
            return attrs
        for pair in attrs_str.split('|'):
            if ':' in pair:
                key, val = pair.split(':', 1)
                attrs[key] = val
        return attrs

    def _extract_city_from_url(self, url: str) -> str:
        """Extract city from Kleinanzeigen URL."""
        match = re.search(r'/s-wohnung-kaufen-([^/]+)/', url)
        if match:
            return match.group(1).replace('-', ' ').title()
        return ""

    def extract(self, url: str, source_info: Optional[dict] = None) -> ExtractedListing:
        """
        Extract structured data from a single listing page.
        """
        listing = ExtractedListing(
            url=url,
            scraped_at=datetime.now(timezone.utc).isoformat(),
            source="kleinanzeigen",
        )

        if source_info:
            listing.location_city = source_info.get("city", "")

        try:
            page = self._Fetcher.get(
                url,
                timeout=30000,
                headers={'User-Agent': UA},
                follow_redirects=True,
                referer='https://www.google.com/'
            )

            if page.status != 200:
                raise Exception(f"HTTP {page.status}")

            html = page.body.decode('utf-8', errors='ignore')
            listing.raw_data = html[:5000]

            # --- Extract structured data from embedded JSON ---

            # ad_id
            ad_id_match = re.search(r'"ad_id"\s*:\s*"(\d+)"', html)
            if ad_id_match:
                listing.listing_id = f"klz-{ad_id_match.group(1)}"

            # ad_title
            title_match = re.search(r'"ad_title"\s*:\s*"([^"]+)"', html)
            if title_match:
                listing.title = title_match.group(1)

            # ad_price (US format: 123000.00 = 123,000.00 EUR)
            price_match = re.search(r'"ad_price"\s*:\s*"([^"]+)"', html)
            if price_match:
                try:
                    listing.price = float(price_match.group(1))
                except ValueError:
                    pass

            # ad_attributes
            attrs_match = re.search(r'"ad_attributes"\s*:\s*"([^"]+)"', html)
            if attrs_match:
                attrs = self._parse_attributes(attrs_match.group(1))

                # Living space (qm_d)
                if 'qm_d' in attrs:
                    listing.living_space = float(attrs['qm_d'])

                # Rooms (zimmer_d)
                if 'zimmer_d' in attrs:
                    listing.rooms = int(float(attrs['zimmer_d']))

                # Bedrooms (schlafzimmer_d)
                if 'schlafzimmer_d' in attrs:
                    listing.features.append(f"Schlafzimmer: {attrs['schlafzimmer_d']}")

                # Bathrooms (badezimmer_d)
                if 'badezimmer_d' in attrs:
                    listing.features.append(f"Badezimmer: {attrs['badezimmer_d']}")

                # Built year (baujahr_i)
                if 'baujahr_i' in attrs:
                    listing.built_year = int(attrs['baujahr_i'])

                # Property type (wohnungstyp_s)
                if 'wohnungstyp_s' in attrs:
                    wtyp = attrs['wohnungstyp_s']
                    if wtyp == 'etagenwohnung':
                        listing.property_type = 'apartment'
                    elif wtyp == 'haus':
                        listing.property_type = 'house'
                    elif wtyp == 'wohnung':
                        listing.property_type = 'apartment'

                # Features
                if attrs.get('balcony_b') == 't':
                    listing.features.append("Balkon/Terrasse")
                if attrs.get('garage_b') == 't':
                    listing.features.append("Garage")
                if attrs.get('celler_loft_b') == 't':
                    listing.features.append("Keller")
                if attrs.get('lift_b') == 't':
                    listing.features.append("Aufzug")
                if attrs.get('bathtub_b') == 't':
                    listing.features.append("Badewanne")
                if attrs.get('provision_s') == 'f':
                    listing.features.append("Keine Provision")
                if attrs.get('provision_s') == 't':
                    listing.features.append("Provision")

            # --- Extract from HTML text (fallbacks) ---

            # Living space from text
            if listing.living_space == 0:
                area_match = re.search(r'(\d[\d.]*)\s*m²', html)
                if area_match:
                    listing.living_space = float(area_match.group(1).replace('.', ''))

            # Rooms from text
            if listing.rooms == 0:
                zimmer_match = re.search(r'(\d+)\s*Zimmer', html)
                if zimmer_match:
                    listing.rooms = int(zimmer_match.group(1))

            # Built year from text
            if listing.built_year == 0:
                jahr_match = re.search(r'Baujahr[^"]*[:\s]+(\d{4})', html)
                if jahr_match:
                    listing.built_year = int(jahr_match.group(1))

            # Description
            desc_match = re.search(r'Lagebeschreibung:\s*(.+?)(?:\n\n|$)', html, re.DOTALL)
            if desc_match:
                listing.description = desc_match.group(1).strip()[:3000]

            # --- Exclusion flags ---
            full_text = html.lower()
            listing.is_erbpacht = 'erbbaurecht' in full_text or 'erbpacht' in full_text
            listing.is_vacation = 'ferienwohnung' in full_text
            listing.is_auction = 'zwangsversteigerung' in full_text or 'zvg' in full_text
            listing.is_care_apartment = 'betreutes wohnen' in full_text
            listing.is_social_binding = 'sozialbindung' in full_text or 'gefördert' in full_text

            # --- City from URL ---
            if not listing.location_city:
                listing.location_city = self._extract_city_from_url(url)

            # --- Rent (if available) ---
            rent_match = re.search(r'(\d[\d.]*)\s*m²\s*-\s*([\d.,]+)\s*€\s*Kaltmiete', html)
            if rent_match:
                listing.rent_monthly = float(rent_match.group(2).replace('.', '').replace(',', '.'))

            # Rent per sqm
            if listing.living_space > 0 and listing.rent_monthly > 0:
                listing.rent_per_sqm = round(listing.rent_monthly / listing.living_space, 2)

            # --- Success check ---
            listing.extraction_success = listing.price > 0 and listing.living_space > 0

            # Build extraction note
            notes = []
            if listing.title:
                notes.append(f"title='{listing.title[:50]}'")
            if listing.price:
                notes.append(f"price={listing.price:.0f}€")
            if listing.living_space:
                notes.append(f"area={listing.living_space:.0f}m²")
            if listing.rooms:
                notes.append(f"rooms={listing.rooms}")
            if listing.built_year:
                notes.append(f"year={listing.built_year}")
            listing.extraction_notes = ", ".join(notes) if notes else "no fields extracted"

            logger.info("Extracted: %s", listing.extraction_notes)

        except Exception as e:
            logger.error("Extraction failed for %s: %s", url, e)
            listing.extraction_success = False
            listing.extraction_notes = f"error: {e}"

        return listing

    def extract_batch(self, urls: list, source_info: Optional[dict] = None) -> list[ExtractedListing]:
        """Extract from multiple URLs with rate limiting."""
        results = []
        for i, url in enumerate(urls):
            logger.info("Extracting listing %d/%d: %s", i + 1, len(urls), url)
            listing = self.extract(url, source_info)
            results.append(listing)

            # Rate limit between extractions
            if i < len(urls) - 1:
                self._wait()

        return results


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Kleinanzeigen Extractor")
    parser.add_argument("--input", help="Input JSON file with listing URLs")
    parser.add_argument("--url", help="Single URL to extract")
    parser.add_argument("--output", default="extracted.json")
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    extractor = KleinanzeigenExtractor()

    if args.url:
        listing = extractor.extract(args.url)
        results = [listing]
    elif args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            listings = json.load(f)

        urls = []
        source_info = None
        for item in listings:
            urls.append(item["url"])
            if item.get("search_config"):
                source_info = item["search_config"]

        results = extractor.extract_batch(urls, source_info)
    else:
        parser.error("Provide --url or --input")

    # Write output
    output_data = [asdict(r) for r in results]
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    # Summary
    success = sum(1 for r in results if r.extraction_success)
    print(f"\nExtracted {len(results)} listings ({success} successful) → {args.output}")
    for i, r in enumerate(results, 1):
        status = "OK" if r.extraction_success else "FAIL"
        print(f"  {i}. [{status}] {r.extraction_notes}")
        if r.url:
            print(f"     {r.url}")


if __name__ == "__main__":
    main()
