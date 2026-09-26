#!/usr/bin/env python3
"""
Immowelt Scraper — Playwright-based (JS-rendered SPA).

Scrapes apartment listings from immowelt.de for purchase ("Wohnung kaufen").
Uses Playwright to render JavaScript and extract listing data from search results.

Usage:
    python src/immowelt_scraper.py --city "Berlin" --max-pages 5 --output immowelt_listings.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import random
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/home/vincent/.cache/ms-playwright")

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Listing:
    listing_id: str = ""
    url: str = ""
    title: str = ""
    price: float = 0.0
    living_space: float = 0.0
    rooms: int = 0
    floor: str = ""
    address: str = ""
    city: str = ""
    source: str = "immowelt"
    scraped_at: str = ""
    raw_data: str = ""
    extraction_success: bool = False
    extraction_notes: str = ""


# ---------------------------------------------------------------------------
# Immowelt Scraper
# ---------------------------------------------------------------------------

class ImmoweltScraper:
    """Scrape apartment listings from Immowelt.de using Playwright."""

    BASE_URL = "https://www.immowelt.de"

    def __init__(self, slow_mo: float = 2.0):
        self.slow_mo = slow_mo
        self._import_playwright()

    def _import_playwright(self):
        from playwright.sync_api import sync_playwright
        self._playwright = sync_playwright

    def _wait(self, min_ms: int = 2000, max_ms: int = 4000):
        time.sleep(random.uniform(min_ms / 1000, max_ms / 1000))

    def _generate_listing_id(self, url: str) -> str:
        """Generate a unique listing ID from URL."""
        match = re.search(r'/immobilie/kaufen/wohnung/[^/]+/(\d+)', url)
        if match:
            return f"iw-{match.group(1)}"
        return f"iw-{hashlib.md5(url.encode()).hexdigest()[:12]}"

    def _extract_city_from_url(self, url: str) -> str:
        """Extract city from Immowelt URL."""
        match = re.search(r'/wohnung/([^/]+?)/', url)
        if match:
            return match.group(1).replace('-', ' ').title()
        return ""

    def _extract_price(self, text: str) -> Optional[float]:
        """Extract price from listing text."""
        # Match prices like "298.000 €" or "128.000,00 €"
        match = re.search(r'([\d.]+)\s*€', text)
        if match:
            val = match.group(1).replace('.', '').replace(',', '.')
            try:
                return float(val)
            except ValueError:
                return None
        return None

    def _extract_area(self, text: str) -> Optional[float]:
        """Extract living space from listing text."""
        match = re.search(r'([\d.]+)\s*m²', text)
        if match:
            val = match.group(1).replace('.', '').replace(',', '.')
            try:
                return float(val)
            except ValueError:
                return None
        return None

    def _extract_rooms(self, text: str) -> Optional[int]:
        """Extract number of rooms from listing text."""
        match = re.search(r'(\d+)\s*Zimmer', text)
        if match:
            return int(match.group(1))
        return None

    def _extract_address(self, text: str) -> str:
        """Extract address from listing text."""
        # Look for address patterns
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            # Match address patterns like "Street 12, City, District (PLZ)"
            if re.search(r'\d+\s*,\s*\w+', line) and '€' not in line and 'Zimmer' not in line and 'm²' not in line:
                return line
        return ""

    def _extract_listing_from_card(self, card) -> Optional[Listing]:
        """Extract structured data from a single listing card."""
        listing = Listing(scraped_at=datetime.now(timezone.utc).isoformat(), source="immowelt")

        try:
            text = card.inner_text() or ""
            if not text.strip():
                return None

            # Get the link
            link_el = card.query_selector('a[href*="/immobilie/"]')
            if link_el:
                href = link_el.get_attribute('href')
                if href:
                    listing.url = 'https://www.immowelt.de' + href if not href.startswith('http') else href
                    listing.listing_id = self._generate_listing_id(listing.url)

            listing.title = text[:100]

            listing.price = self._extract_price(text) or 0.0
            listing.living_space = self._extract_area(text) or 0.0
            listing.rooms = self._extract_rooms(text) or 0
            listing.address = self._extract_address(text)

            # Extract city from URL
            if listing.url:
                listing.city = self._extract_city_from_url(listing.url)

            if listing.price > 0 and listing.living_space > 0:
                listing.extraction_success = True
                listing.extraction_notes = "extracted"
                return listing
            else:
                return None

        except Exception as e:
            logger.debug(f"Error extracting card: {e}")
            return None

    def _get_search_url(self, city: str, page: int = 0) -> str:
        """Build Immowelt search URL."""
        if city and city.lower() != "deutschland":
            city_slug = city.lower().replace(" ", "-")
            return f"{self.BASE_URL}/suche/kaufen/wohnung/{city_slug}/ad02de1"
        return f"{self.BASE_URL}/suche/kaufen/wohnung/deutschland/ad02de1"

    def _get_next_page_url(self, page) -> Optional[str]:
        """Get the next page URL from the pagination."""
        try:
            next_btn = page.query_selector('a[aria-label="nächste Seite"], .pagination-next a, .serp-pagination-next a')
            if next_btn:
                href = next_btn.get_attribute('href')
                if href:
                    return href if href.startswith('http') else f"{self.BASE_URL}{href}"
        except:
            pass
        return None

    def scrape(self, city: str = "Deutschland", max_pages: int = 5,
               min_price: int = 80000, max_price: int = 150000,
               min_area: float = 30.0, max_area: float = 55.0) -> list[Listing]:
        """
        Scrape listings from Immowelt.
        
        Returns filtered listings matching the criteria.
        """
        all_listings = []
        seen_urls = set()
        
        with self._playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                locale="de-DE",
            )
            page = context.new_page()

            for page_num in range(max_pages):
                search_url = self._get_search_url(city, page_num)
                logger.info("Fetching page %d: %s", page_num, search_url)

                try:
                    page.goto(search_url, wait_until="networkidle", timeout=60000)
                    page.wait_for_timeout(3000)  # Wait for dynamic content

                    # Find listing cards
                    listing_cards = page.query_selector_all('[data-testid*="card"]')
                    logger.info("Page %d: found %d cards", page_num, len(listing_cards))

                    for card in listing_cards:
                        listing = self._extract_listing_from_card(card)
                        if listing and listing.url not in seen_urls:
                            seen_urls.add(listing.url)
                            # Apply price/area filters
                            if (min_price <= listing.price <= max_price and
                                    min_area <= listing.living_space <= max_area):
                                all_listings.append(listing)

                    # Check for next page
                    next_url = self._get_next_page_url(page)
                    if not next_url:
                        logger.info("No more pages")
                        break

                    self._wait()

                except Exception as e:
                    logger.error("Error on page %d: %s", page_num, e)
                    break

            browser.close()

        logger.info("Scrape complete: %d listings found (filtered)", len(all_listings))
        return all_listings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Immowelt Scraper")
    parser.add_argument("--city", default="Deutschland")
    parser.add_argument("--min-price", type=int, default=80000)
    parser.add_argument("--max-price", type=int, default=150000)
    parser.add_argument("--min-area", type=float, default=30.0)
    parser.add_argument("--max-area", type=float, default=55.0)
    parser.add_argument("--output", default="immowelt_listings.json")
    parser.add_argument("--max-pages", type=int, default=5)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    scraper = ImmoweltScraper()
    listings = scraper.scrape(
        city=args.city,
        max_pages=args.max_pages,
        min_price=args.min_price,
        max_price=args.max_price,
        min_area=args.min_area,
        max_area=args.max_area,
    )

    output_data = [asdict(l) for l in listings]
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"\nFound {len(listings)} listings → {args.output}")
    for i, l in enumerate(listings, 1):
        print(f"  {i}. {l.url}")
        print(f"     {l.title[:60]}")
        print(f"     Price: {l.price}€ | Area: {l.living_space}m² | City: {l.city}")


if __name__ == "__main__":
    main()
