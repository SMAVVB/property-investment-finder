#!/usr/bin/env python3
"""Extract full Immowelt listings with detailed data."""

import json
import os
import re

os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/home/vincent/.cache/ms-playwright")

from playwright.sync_api import sync_playwright

def extract_from_card_text(text):
    """Extract structured data from card text."""
    data = {}
    
    # Price
    price_match = re.search(r'([\d.]+)\s*€', text)
    if price_match:
        val = price_match.group(1).replace('.', '').replace(',', '.')
        try:
            data['price'] = float(val)
        except:
            pass
    
    # Area
    area_match = re.search(r'([\d.]+)\s*m²', text)
    if area_match:
        val = area_match.group(1).replace('.', '').replace(',', '.')
        try:
            data['living_space'] = float(val)
        except:
            pass
    
    # Rooms
    rooms_match = re.search(r'(\d+)\s*Zimmer', text)
    if rooms_match:
        data['rooms'] = int(rooms_match.group(1))
    
    # Address
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if re.search(r'\d+\s*,\s*\w+', line) and '€' not in line and 'Zimmer' not in line and 'm²' not in line and 'Monat' not in line:
            data['address'] = line
            break
    
    return data

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        locale="de-DE",
    )
    page = context.new_page()
    
    print("Navigating to Immowelt...")
    page.goto(
        "https://www.immowelt.de/suche/kaufen/wohnung/deutschland/ad02de1",
        wait_until="networkidle",
        timeout=60000
    )
    page.wait_for_timeout(3000)
    
    # Get covering links
    covering_links = page.query_selector_all('[data-testid*="covering-link"]')
    print(f"\nCovering links: {len(covering_links)}")
    
    # Get card texts
    cards = page.query_selector_all('[data-testid*="cardmfe-container"]')
    print(f"Cards: {len(cards)}")
    
    listings = []
    for i, (link_el, card_el) in enumerate(zip(covering_links, cards)):
        href = link_el.get_attribute('href') or ""
        text = card_el.inner_text() or ""
        
        data = extract_from_card_text(text)
        data['url'] = href
        data['card_index'] = i
        
        if data.get('price') and data.get('living_space'):
            listings.append(data)
    
    print(f"\nListings with price+area: {len(listings)}")
    
    # Show sample
    print("\n=== Sample ===")
    for l in listings[:3]:
        print(json.dumps(l, ensure_ascii=False, indent=2))
    
    # Price distribution
    if listings:
        prices = [l['price'] for l in listings]
        areas = [l['living_space'] for l in listings]
        print(f"\n=== Summary ===")
        print(f"Total: {len(listings)}")
        print(f"Price: {min(prices):.0f}€ - {max(prices):.0f}€ (avg: {sum(prices)/len(prices):.0f}€)")
        print(f"Area: {min(areas):.0f}m² - {max(areas):.0f}m² (avg: {sum(areas)/len(areas):.0f}m²)")
        
        # Filter by criteria
        filtered = [l for l in listings if 80000 <= l['price'] <= 150000 and 30 <= l['living_space'] <= 55]
        print(f"\nFiltered (80-150k€, 30-55m²): {len(filtered)}")
        for l in filtered[:3]:
            print(f"  {l['price']}€ | {l['living_space']}m² | {l.get('address', '')[:50]}")
    
    browser.close()
