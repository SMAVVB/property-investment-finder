#!/usr/bin/env python3
"""
Property Investment Finder — Navigator (Phase 2)

Uses Scrapling's Fetcher for fast, reliable page fetching and parses
the embedded JSON data from Kleinanzeigen search results.

Design principles:
- Respect robots.txt (Kleinanzeigen allows crawling per their robots.txt)
- Rate-limit: 3-5s between page loads
- Realistic User-Agent, no headless detection triggers
- No parallel sessions
- Uses Scrapling (not Playwright) for search results — much faster

Usage:
  python -m src.navigator --city "Leipzig" --min-price 80000 --max-price 150000 \\
      --min-area 30 --max-area 55 --output listings.json --max-pages 3
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import sys
import time
from dataclasses import dataclass, field, asdict
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
class SearchConfig:
    """Configuration for a portal search."""
    city: str = "Leipzig"
    min_price: int = 80000
    max_price: int = 150000
    min_area: float = 30.0
    max_area: float = 55.0
    property_type: str = "Wohnung"
    rooms_min: Optional[int] = None
    rooms_max: Optional[int] = None


@dataclass
class ListingURL:
    """A found listing URL with its search context."""
    url: str
    title: str = ""
    price: str = ""
    area: str = ""
    rooms: str = ""
    city: str = ""
    source: str = "kleinanzeigen"
    search_config: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Kleinanzeigen Navigator (Scrapling-based)
# ---------------------------------------------------------------------------

class KleinanzeigenNavigator:
    """
    Navigate eBay Kleinanzeigen to find property listings.

    Uses Scrapling's Fetcher for fast HTTP fetching and parses
    the embedded structured data from the HTML.
    """

    BASE_URL = "https://www.kleinanzeigen.de"

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

    def _build_search_url(self, config: SearchConfig, page: int = 0) -> str:
        """
        Build a Kleinanzeigen search URL.

        Format: https://www.kleinanzeigen.de/s-wohnung-kaufen-{city}/k{page}
        Note: Kleinanzeigen pagination uses k0, k1, etc. but often only k0
        returns results — the rest may be 404 or handled via JS.
        """
        city_slug = config.city.lower().replace(" ", "-")
        return f"{self.BASE_URL}/s-wohnung-kaufen-{city_slug}/k{page}"

    def _parse_search_page(self, html: str) -> list[dict]:
        """
        Parse a search results page and extract listing data.

        Kleinanzeigen embeds structured data in script tags as JSON.
        We extract listing IDs, titles, prices, and URLs from this data.
        """
        listings = []
        seen_urls = set()

        # Extract listing paths from href attributes
        # Format: href="/s-anzeige/<slug>/<id>-<num>-<num>"
        listing_href_pattern = r'href="(/s-anzeige/[^/]+/\d+-\d+-\d+)"'
        listing_paths = re.findall(listing_href_pattern, html)

        # Get unique paths
        unique_paths = list(set(listing_paths))

        # Extract ad_attributes
        attr_pattern = r'"ad_attributes"\s*:\s*"([^"]+)"'
        attrs_list = re.findall(attr_pattern, html)

        # Extract ad_title
        title_pattern = r'"ad_title"\s*:\s*"([^"]+)"'
        titles = re.findall(title_pattern, html)

        # Extract ad_price
        price_pattern = r'"ad_price"\s*:\s*"([^"]+)"'
        prices = re.findall(price_pattern, html)

        # Extract ad_id
        ad_id_pattern = r'"ad_id"\s*:\s*"(\d+)"'
        ad_ids = re.findall(ad_id_pattern, html)

        for path in unique_paths:
            # Check if it's a Wohnung (apartment) listing
            if "wohnung" not in path.lower():
                continue

            full_url = f"{self.BASE_URL}{path}"

            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            # Extract slug and ID for attribute matching
            slug_match = re.search(r'/s-anzeige/([^/]+)/(\d+)', path)
            if not slug_match:
                continue
            slug = slug_match.group(1)
            ad_id = slug_match.group(2)

            # Try to get title
            title = ""
            for t in titles:
                if "wohnung" in t.lower():
                    title = t
                    break

            # Try to get price
            price = ""
            for p in prices:
                try:
                    price_val = float(p.replace(".", "").replace(",", "."))
                    if 80000 <= price_val <= 150000:
                        price = p
                        break
                except ValueError:
                    continue

            # Parse attributes for area, rooms, etc.
            area = ""
            rooms = ""
            for attrs_str in attrs_list:
                attrs = {}
                for pair in attrs_str.split("|"):
                    if ":" in pair:
                        key, val = pair.split(":", 1)
                        attrs[key] = val
                if "qm_d" in attrs:
                    area = attrs["qm_d"]
                if "zimmer_d" in attrs:
                    rooms = attrs["zimmer_d"]

            listings.append({
                "url": full_url,
                "title": title,
                "price": price,
                "area": area,
                "rooms": rooms,
                "city": "",
                "ad_id": ad_id,
            })

        return listings

    def search(self, config: SearchConfig, max_pages: int = 3) -> list[ListingURL]:
        """
        Run a full search and return listing URLs.
        """
        all_listings = []
        seen_urls = set()

        # Kleinanzeigen often only returns results on k0
        # Try k0, then k1, etc. until we get results or max_pages
        for page in range(0, max_pages):
            url = self._build_search_url(config, page)
            logger.info("Fetching page %d: %s", page, url)

            try:
                page_obj = self._Fetcher.get(
                    url,
                    timeout=30000,
                    headers={"User-Agent": UA},
                    follow_redirects=True,
                    referer="https://www.google.com/",
                )

                if page_obj.status != 200:
                    logger.info("Page %d returned %d — stopping pagination", page, page_obj.status)
                    break

                html = page_obj.body.decode("utf-8", errors="ignore")
                raw_listings = self._parse_search_page(html)

                page_count = 0
                for listing in raw_listings:
                    if listing["url"] not in seen_urls:
                        seen_urls.add(listing["url"])
                        listing["search_config"] = {
                            "city": config.city,
                            "min_price": config.min_price,
                            "max_price": config.max_price,
                            "min_area": config.min_area,
                            "max_area": config.max_area,
                        }
                        all_listings.append(listing)
                        page_count += 1

                logger.info(
                    "Page %d: %d new listings (%d total)",
                    page, page_count, len(all_listings),
                )

                # Rate limit between pages
                if page < max_pages - 1:
                    self._wait()

            except Exception as e:
                logger.error("Error fetching page %d: %s", page, e)
                break

        # Convert to ListingURL objects
        results = []
        for raw in all_listings:
            results.append(ListingURL(
                url=raw["url"],
                title=raw.get("title", ""),
                price=raw.get("price", ""),
                area=raw.get("area", ""),
                rooms=raw.get("rooms", ""),
                city=config.city,
                source="kleinanzeigen",
                search_config=raw.get("search_config", {}),
            ))

        logger.info("Search complete: %d listings found", len(results))
        return results


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Kleinanzeigen Navigator")
    parser.add_argument("--city", default="Leipzig")
    parser.add_argument("--min-price", type=int, default=80000)
    parser.add_argument("--max-price", type=int, default=150000)
    parser.add_argument("--min-area", type=float, default=30.0)
    parser.add_argument("--max-area", type=float, default=55.0)
    parser.add_argument("--output", default="listings.json")
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    config = SearchConfig(
        city=args.city,
        min_price=args.min_price,
        max_price=args.max_price,
        min_area=args.min_area,
        max_area=args.max_area,
    )

    nav = KleinanzeigenNavigator()
    listings = nav.search(config, max_pages=args.max_pages)

    output_data = [asdict(l) for l in listings]
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"\nFound {len(listings)} listings → {args.output}")
    for i, l in enumerate(listings, 1):
        print(f"  {i}. {l.url}")
        print(f"     Title: {l.title[:80]}")
        print(f"     Price: {l.price} | Area: {l.area} | City: {l.city}")


if __name__ == "__main__":
    main()
