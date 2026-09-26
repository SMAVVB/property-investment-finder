#!/usr/bin/env python3
"""
Property Investment Finder — Multi-Source Scraper (Phase 2c)

Scrapes apartment listings from multiple German property portals:
1. Kleinanzeigen (existing)
2. Immowelt (new - Playwright-based)
3. ImmoScout24 (new - Playwright-based, may require login)

Usage:
    python src/multi_source_scraper.py --output data/all_listings.json
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
    rent_monthly: float = 0.0
    rooms: int = 0
    floor: str = ""
    plz: str = ""
    city: str = ""
    bundesland: str = ""
    address: str = ""
    source: str = ""
    scraped_at: str = ""
    raw_data: str = ""
    extraction_success: bool = False
    extraction_notes: str = ""


# ---------------------------------------------------------------------------
# Immowelt Scraper
# ---------------------------------------------------------------------------

class ImmoweltScraper:
    """Scrape apartment listings from Immowelt.de using Playwright."""

    def __init__(self):
        from playwright.sync_api import sync_playwright
        self._playwright = sync_playwright

    def _extract_from_text(self, text: str) -> dict:
        """Extract structured data from card text."""
        data = {}

        # Price
        price_match = re.search(r'([\d.]+)\s*€', text)
        if price_match:
            val = price_match.group(1).replace('.', '').replace(',', '.')
            try:
                data['price'] = float(val)
            except ValueError:
                pass

        # Area
        area_match = re.search(r'([\d.]+)\s*m²', text)
        if area_match:
            val = area_match.group(1).replace('.', '').replace(',', '.')
            try:
                data['living_space'] = float(val)
            except ValueError:
                pass

        # Rooms
        rooms_match = re.search(r'(\d+)\s*Zimmer', text)
        if rooms_match:
            data['rooms'] = int(rooms_match.group(1))

        # Address
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if (re.search(r'\d+\s*,\s*\w+', line) and
                    '€' not in line and 'Zimmer' not in line and
                    'm²' not in line and 'Monat' not in line and
                    'Geschoss' not in line):
                data['address'] = line
                break

        return data

    def _extract_city_from_address(self, address: str) -> str:
        """Extract city from address string."""
        if not address:
            return ""
        # Match patterns like "Street, City, District (PLZ)"
        parts = address.split(',')
        if len(parts) >= 2:
            return parts[-2].strip()
        return ""

    def _extract_plz_from_address(self, address: str) -> str:
        """Extract PLZ from address string."""
        if not address:
            return ""
        match = re.search(r'\((\d{5})\)', address)
        if match:
            return match.group(1)
        return ""

    def scrape_city(self, city: str, max_pages: int = 3,
                    min_price: int = 80000, max_price: int = 150000,
                    min_area: float = 30.0, max_area: float = 55.0) -> list[Listing]:
        """Scrape listings for a specific city."""
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
                if city.lower() != "deutschland":
                    city_slug = city.lower().replace(" ", "-")
                    search_url = f"https://www.immowelt.de/suche/kaufen/wohnung/{city_slug}/ad02de1"
                else:
                    search_url = "https://www.immowelt.de/suche/kaufen/wohnung/deutschland/ad02de1"

                logger.info("  Immowelt %s page %d: %s", city, page_num, search_url)

                try:
                    page.goto(search_url, wait_until="networkidle", timeout=60000)
                    page.wait_for_timeout(3000)

                    # Get covering links and cards
                    covering_links = page.query_selector_all('[data-testid*="covering-link"]')
                    cards = page.query_selector_all('[data-testid*="cardmfe-container"]')

                    logger.info("  Found %d links, %d cards", len(covering_links), len(cards))

                    for link_el, card_el in zip(covering_links, cards):
                        href = link_el.get_attribute('href') or ""
                        text = card_el.inner_text() or ""

                        if not href or not text.strip():
                            continue

                        # Generate unique ID from expose UUID in URL
                        uuid_match = re.search(r'/expose/([a-f0-9-]+)', href)
                        if uuid_match:
                            listing_id = f"iw-{uuid_match.group(1)[:12]}"
                        else:
                            listing_id = f"iw-{hashlib.md5(href.encode()).hexdigest()[:12]}"
                        
                        if listing_id in seen_urls:
                            continue
                        seen_urls.add(listing_id)

                        data = self._extract_from_text(text)
                        if not data.get('price') or not data.get('living_space'):
                            continue

                        # Apply filters
                        if not (min_price <= data['price'] <= max_price and
                                min_area <= data['living_space'] <= max_area):
                            continue

                        address = data.get('address', '')
                        city_from_addr = self._extract_city_from_address(address)
                        plz = self._extract_plz_from_address(address)

                        listing = Listing(
                            listing_id=listing_id,
                            url=href,
                            title=text[:100],
                            price=data['price'],
                            living_space=data['living_space'],
                            rooms=data.get('rooms', 0),
                            city=city_from_addr or city,
                            plz=plz,
                            address=address,
                            source="immowelt",
                            scraped_at=datetime.now(timezone.utc).isoformat(),
                            extraction_success=True,
                            extraction_notes="extracted",
                        )
                        all_listings.append(listing)

                    # Check for next page
                    try:
                        next_btn = page.query_selector('a[aria-label="nächste Seite"]')
                        if not next_btn:
                            break
                    except:
                        break

                    time.sleep(random.uniform(2, 4))

                except Exception as e:
                    logger.error("  Error: %s", e)
                    break

            browser.close()

        return all_listings


# ---------------------------------------------------------------------------
# ImmoScout24 Scraper (Playwright-based, may be blocked)
# ---------------------------------------------------------------------------

class ImmoScout24Scraper:
    """Scrape apartment listings from ImmoScout24.de using Playwright."""

    def __init__(self):
        from playwright.sync_api import sync_playwright
        self._playwright = sync_playwright

    def scrape_city(self, city: str, max_pages: int = 2,
                    min_price: int = 80000, max_price: int = 150000,
                    min_area: float = 30.0, max_area: float = 55.0) -> list[Listing]:
        """Scrape listings from ImmoScout24 for a specific city."""
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
                city_slug = city.lower().replace(" ", "-")
                search_url = f"https://www.immobilienscout24.de/Suche/{city_slug}/deutschland/wohnung-kaufen"

                logger.info("  ImmoScout24 %s page %d: %s", city, page_num, search_url)

                try:
                    response = page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                    status = response.status if response else 0

                    if status in [401, 403, 404]:
                        logger.warning("  ImmoScout24 blocked (status %d) — requires login", status)
                        break

                    page.wait_for_timeout(3000)

                    # Try to extract listing data
                    # ImmoScout24 uses different selectors
                    listings_on_page = page.query_selector_all('.result-list-listing')
                    if not listings_on_page:
                        # Try alternative selectors
                        listings_on_page = page.query_selector_all('.listing')
                    if not listings_on_page:
                        listings_on_page = page.query_selector_all('[data-test-case="listing"]')

                    logger.info("  Found %d listing elements", len(listings_on_page))

                    for el in listings_on_page:
                        try:
                            text = el.inner_text() or ""
                            if not text.strip():
                                continue

                            # Generate ID
                            listing_id = f"is24-{hashlib.md5(text.encode()).hexdigest()[:12]}"
                            if listing_id in seen_urls:
                                continue
                            seen_urls.add(listing_id)

                            # Extract data
                            price_match = re.search(r'([\d.]+)\s*€', text)
                            area_match = re.search(r'([\d.]+)\s*m²', text)

                            if not price_match or not area_match:
                                continue

                            price = float(price_match.group(1).replace('.', '').replace(',', '.'))
                            area = float(area_match.group(1).replace('.', '').replace(',', '.'))

                            if not (min_price <= price <= max_price and min_area <= area <= max_area):
                                continue

                            listing = Listing(
                                listing_id=listing_id,
                                url=search_url,
                                title=text[:100],
                                price=price,
                                living_space=area,
                                source="immoscout24",
                                scraped_at=datetime.now(timezone.utc).isoformat(),
                                extraction_success=True,
                                extraction_notes="extracted",
                            )
                            all_listings.append(listing)

                        except Exception:
                            continue

                    time.sleep(random.uniform(2, 4))

                except Exception as e:
                    logger.error("  Error: %s", e)
                    break

            browser.close()

        return all_listings


# ---------------------------------------------------------------------------
# Main Runner
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Multi-Source Property Scraper")
    parser.add_argument("--output", default="data/all_listings.json")
    parser.add_argument("--min-price", type=int, default=80000)
    parser.add_argument("--max-price", type=int, default=150000)
    parser.add_argument("--min-area", type=float, default=30.0)
    parser.add_argument("--max-area", type=float, default=55.0)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # Target cities from criteria.yaml — expanded list
    target_cities = [
        # Berlin outer districts
        "Berlin",
        # Brandenburg towns
        "Leipzig",
        "Cottbus",
        "Frankfurt (Oder)",
        "Potsdam",
        "Dessau-Roßlau",
        "Wittenberg",
        "Senftenberg",
        "Brandenburg an der Havel",
        # S-Bahn belt towns
        "Königs Wusterhausen",
        "Falkensee",
        "Eberswalde",
        "Bernau",
        "Schwedt",
        "Oranienburg",
        "Kleinmachnow",
        "Stahnsdorf",
        "Ketzin",
        "Wandlitz",
        "Hennigsdorf",
        "Teltow",
        "Zossen",
        "Ludwigsfelde",
        "Rathenow",
        # Additional smaller towns with lower prices
        "Halle",
        "Magdeburg",
        "Bautzen",
        "Görlitz",
        "Chemnitz",
        "Dresden",
        "Meißen",
        "Riesa",
        "Delitzsch",
        "Nauen",
        "Prenzlau",
        "Angermünde",
        "Neuruppin",
        "Falkenberg",
        "Bad Belzig",
        "Jüterbog",
        "Schönefeld",
        "Lichterfeld",
    ]

    logger.info("=" * 60)
    logger.info("Starting multi-source property scraper")
    logger.info("Price range: %d-%d€, Area: %.0f-%.0fm²",
                args.min_price, args.max_price, args.min_area, args.max_area)
    logger.info(f"Target cities: {len(target_cities)}")
    logger.info("=" * 60)

    all_listings = []

    # --- Immowelt (broad search, no filtering at scrape time) ---
    logger.info("\n=== Scraping Immowelt (broad) ===")
    iw_scraper = ImmoweltScraper()

    for city in target_cities:
        logger.info("City: %s", city)
        listings = iw_scraper.scrape_city(
            city=city,
            max_pages=5,
            min_price=50000,   # Very broad
            max_price=300000,
            min_area=15.0,
            max_area=100.0,
        )
        logger.info("  → %d listings (broad)", len(listings))
        all_listings.extend(listings)

    # --- ImmoScout24 (may be blocked) ---
    logger.info("\n=== Scraping ImmoScout24 ===")
    is24_scraper = ImmoScout24Scraper()

    for city in target_cities[:5]:  # Try first 5 cities only
        logger.info("City: %s", city)
        listings = is24_scraper.scrape_city(
            city=city,
            max_pages=2,
            min_price=args.min_price,
            max_price=args.max_price,
            min_area=args.min_area,
            max_area=args.max_area,
        )
        logger.info("  → %d listings", len(listings))
        all_listings.extend(listings)

    # --- Deduplicate by listing_id ---
    seen_ids = set()
    unique_listings = []
    for l in all_listings:
        if l.listing_id not in seen_ids:
            seen_ids.add(l.listing_id)
            unique_listings.append(l)
    all_listings = unique_listings
    
    logger.info("\nAfter deduplication: %d unique listings", len(all_listings))

    # --- Save results ---
    output_data = [asdict(l) for l in all_listings]
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    # --- Summary ---
    print("\n" + "=" * 60)
    print("SCRAPING SUMMARY")
    print("=" * 60)
    print(f"Total listings: {len(all_listings)}")
    print(f"  Immowelt: {sum(1 for l in all_listings if l.source == 'immowelt')}")
    print(f"  ImmoScout24: {sum(1 for l in all_listings if l.source == 'immoscout24')}")
    print(f"Output: {args.output}")

    if all_listings:
        prices = [l.price for l in all_listings]
        areas = [l.living_space for l in all_listings]
        print(f"\nPrice range: {min(prices):.0f}€ - {max(prices):.0f}€")
        print(f"Area range: {min(areas):.0f}m² - {max(areas):.0f}m²")

    return all_listings


if __name__ == "__main__":
    main()
