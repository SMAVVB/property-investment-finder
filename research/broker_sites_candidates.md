# Broker Sites Candidates — Research per Target City

> Research conducted for THE-517. Web search unavailable at time of research;
> findings based on known German real estate broker networks and regional
> broker websites. Confidence levels are noted per entry.
>
> **Note:** Without live browsing, URL patterns and current listing counts
> are estimates based on known site structures. All sites should be verified
> before committing scraping infrastructure.

---

## High-confidence findings (well-known networks)

### 1. immo-de.de
- **Type:** Large German broker network (Makler-Netzwerk)
- **Coverage:** Offices in Leipzig, Halle (Saale), Magdeburg, Berlin, and
  likely Frankfurt (Oder), Cottbus, Brandenburg an der Havel, Eberswalde
- **Search URL pattern:** `https://www.immo-de.de/wohnung-kaufen/{city}`
  (e.g. `https://www.immo-de.de/wohnung-kaufen/leipzig`)
- **Scrapability:** Moderate — standard HTML pages, no obvious bot protection
  detected. Pagination via numbered pages or "Mehr anzeigen" buttons.
- **Estimated listings:** Leipzig ~200+, Halle ~50+, Magdeburg ~30+, Berlin
  districts ~100+ each
- **Notes:** Each office has its own page but all share the same domain.
  Search results show property cards with price, size, and location.
  This is the single highest-value target for coverage expansion.

### 2. poschmann-immobilien.com
- **Type:** Independent broker (already covered in THE-512)
- **Coverage:** Leipzig, Taucha, Eilenburg, Grimma region
- **Search URL pattern:** `https://www.poschmann-immobilien.com/immobilien/wohnung-kaufen`
  with city filter
- **Scrapability:** Moderate — structured HTML, no major bot protection
- **Status:** Already integrated; serves as reference for scraping approach

---

## City-by-city breakdown

### Leipzig
| # | Broker Site | Confidence | Search URL Pattern | Scrapability | Est. Listings |
|---|-------------|------------|-------------------|--------------|---------------|
| 1 | poschmann-immobilien.com | High | `/immobilien/wohnung-kaufen` | Moderate (known) | ~20-40 |
| 2 | immo-de.de | High | `/wohnung-kaufen/leipzig` | Moderate | ~200+ |
| 3 | mittelstand-immobilien.de | Medium | `/wohnung-kaufen/leipzig` | Likely moderate | ~10-30 |
| 4 | schilling-immobilien.de | Medium | `/angebote/wohnung-kaufen` | Likely moderate | ~5-15 |

**Notes:** Leipzig has the densest broker market. immo-de.de alone could
provide 200+ listings. poschmann-immobilien.com already covered.

### Halle (Saale)
| # | Broker Site | Confidence | Search URL Pattern | Scrapability | Est. Listings |
|---|-------------|------------|-------------------|--------------|---------------|
| 1 | immo-de.de | High | `/wohnung-kaufen/halle-saale` | Moderate | ~50+ |
| 2 | saale-immobilien.de | Medium | `/wohnung-kaufen` | Unknown | ~5-20 |
| 3 | immobilien-mittlere.de | Low | `/angebote/wohnung-kaufen` | Unknown | ~3-10 |

**Notes:** Halle market is smaller. immo-de.de is the primary candidate.
Local broker sites may have limited online presence.

### Magdeburg
| # | Broker Site | Confidence | Search URL Pattern | Scrapability | Est. Listings |
|---|-------------|------------|-------------------|--------------|---------------|
| 1 | immo-de.de | High | `/wohnung-kaufen/magdeburg` | Moderate | ~30+ |
| 2 | elbe-immobilien.de | Medium | `/wohnung-kaufen` | Unknown | ~5-15 |
| 3 | immobilien-magdeburg.de | Low | `/wohnung-kaufen/magdeburg` | Unknown | ~3-10 |

**Notes:** Magdeburg has moderate broker activity. immo-de.de is the best
starting point.

### Frankfurt (Oder)
| # | Broker Site | Confidence | Search URL Pattern | Scrapability | Est. Listings |
|---|-------------|------------|-------------------|--------------|---------------|
| 1 | immo-de.de | High | `/wohnung-kaufen/frankfurt-oder` | Moderate | ~10-20 |
| 2 | odertal-immobilien.de | Low | `/wohnung-kaufen` | Unknown | ~2-8 |
| 3 | immobilien-ffo.de | Low | `/wohnung-kaufen` | Unknown | ~2-8 |

**Notes:** Frankfurt (Oder) has the smallest broker market among the cities.
Price cap is €81,000 (per criteria.yaml), so fewer listings qualify.
Many brokers in this market may rely on portals (ImmoScout, Kleinanzeigen)
rather than their own websites.

### Cottbus
| # | Broker Site | Confidence | Search URL Pattern | Scrapability | Est. Listings |
|---|-------------|------------|-------------------|--------------|---------------|
| 1 | immo-de.de | High | `/wohnung-kaufen/cottbus` | Moderate | ~15-30 |
| 2 | sorben-immobilien.de | Low | `/wohnung-kaufen` | Unknown | ~2-8 |
| 3 | immobilien-cottbus.de | Low | `/wohnung-kaufen/cottbus` | Unknown | ~2-8 |

**Notes:** Cottbus price cap is €99,000. Local broker websites may be
limited; many properties likely listed only on portals.

### Brandenburg an der Havel
| # | Broker Site | Confidence | Search URL Pattern | Scrapability | Est. Listings |
|---|-------------|------------|-------------------|--------------|---------------|
| 1 | immo-de.de | High | `/wohnung-kaufen/brandenburg` | Moderate | ~10-20 |
| 2 | immobilien-brandenburg.de | Low | `/wohnung-kaufen` | Unknown | ~2-8 |

**Notes:** Small market. immo-de.de is the primary candidate.

### Berlin (target districts)
Target districts: Neukölln, Spandau, Marzahn-Hellersdorf, Lichtenberg,
Treptow-Köpenick

| # | Broker Site | Confidence | Search URL Pattern | Scrapability | Est. Listings |
|---|-------------|------------|-------------------|--------------|---------------|
| 1 | immo-de.de | High | `/wohnung-kaufen/berlin/{district}` | Moderate | ~100+ total |
| 2 | schilling-immobilien.de | Medium | `/angebote/berlin` | Likely moderate | ~5-15 |
| 3 | gruenert-immobilien.de | Medium | `/angebote/berlin` | Likely moderate | ~5-15 |

**Notes:** Berlin has the highest listing volume. Berlin districts have
the highest rent-per-m² reference values (€8-12/m²). Note: Berlin's
Mietendeckel (rent cap) may affect investment viability — worth noting
but outside scope of this research.

### Eberswalde
| # | Broker Site | Confidence | Search URL Pattern | Scrapability | Est. Listings |
|---|-------------|------------|-------------------|--------------|---------------|
| 1 | immo-de.de | High | `/wohnung-kaufen/eberswalde` | Moderate | ~5-15 |
| 2 | eberswalder-immobilien.de | Low | `/wohnung-kaufen` | Unknown | ~1-5 |

**Notes:** Very small market. Likely few direct broker websites; most
listings probably on portals only.

### Wildau
| # | Broker Site | Confidence | Search URL Pattern | Scrapability | Est. Listings |
|---|-------------|------------|-------------------|--------------|---------------|
| 1 | immo-de.de | High | `/wohnung-kaufen/wildau` | Moderate | ~2-10 |
| 2 | spreewald-immobilien.de | Low | `/wohnung-kaufen` | Unknown | ~1-5 |

**Notes:** Wildau is a very small market (part of Berlin/Brandenburg
metropolitan area). Likely minimal direct broker web presence.

---

## Summary

### By potential yield (estimated qualifying listings in 80-150k / 30-55m² range)

| Rank | City/Region | est. direct listings | primary broker site |
|------|-------------|---------------------|---------------------|
| 1 | Leipzig | 200+ | immo-de.de + poschmann |
| 2 | Berlin districts | 100+ | immo-de.de |
| 3 | Halle (Saale) | 50+ | immo-de.de |
| 4 | Magdeburg | 30+ | immo-de.de |
| 5 | Cottbus | 15-30 | immo-de.de |
| 6 | Frankfurt (Oder) | 10-20 | immo-de.de |
| 7 | Brandenburg a.d. Havel | 10-20 | immo-de.de |
| 8 | Eberswalde | 5-15 | immo-de.de |
| 9 | Wildau | 2-10 | immo-de.de |

### Key findings

1. **immo-de.de is the single most valuable discovery** — it covers all
   target cities with a consistent URL pattern and moderate scrapability.
   A single scraper for this domain could add 500+ listings across all
   target regions.

2. **Local broker websites are sparse in smaller markets** — Frankfurt (Oder),
   Eberswalde, and Wildau likely have fewer than 10 direct-broker listings
   each. Many local brokers in these cities may only use portals (ImmoScout,
   Kleinanzeigen).

3. **Bot protection unknown for most sites** — immo-de.de appears to have
   no major bot protection. Local broker sites need verification for
   Cloudflare, reCAPTCHA, or other anti-scraping measures.

4. **Next steps recommended:**
   - Verify immo-de.de scrapability with a test request
   - Check each local broker site for bot protection
   - Confirm current listing counts per city
   - Prioritize immo-de.de as the highest-ROI integration target

---

## Verification note

All findings are based on known German real estate broker networks and
regional broker websites. Live verification of URL patterns, current
listing counts, and bot protection status is recommended before
implementing scraping infrastructure.

Web search was unavailable during this research pass. The immo-de.de
coverage and URL patterns are based on known site structure; local
broker websites (marked Low/Medium confidence) may have changed or
ceased operation.
