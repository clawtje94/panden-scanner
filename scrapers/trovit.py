"""
Trovit.nl scraper — aggregator met veel bronnen.
Server-rendered HTML, vereist volledige browser headers.
"""
import logging
import re
import time
import random
from typing import List
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup
from models import Property
from config import STEDEN_FUNDA, FIX_FLIP

logger = logging.getLogger(__name__)

BASE = "https://huizen.trovit.nl"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Upgrade-Insecure-Requests": "1",
}


def _parse_prijs(tekst: str) -> int:
    if not tekst:
        return 0
    t = tekst.lower()
    if any(kw in t for kw in ["maand", "jaar", "per m"]):
        return 0
    schoon = re.sub(r'[^\d]', '', tekst)
    prijs = int(schoon) if schoon else 0
    return prijs if prijs >= 25_000 else 0


def _parse_opp(tekst: str) -> int:
    if not tekst:
        return 0
    match = re.search(r'(\d+)\s*m', tekst.replace(".", ""))
    return int(match.group(1)) if match else 0


def scrape_trovit(max_pages: int = 3) -> List[Property]:
    """Scrape Trovit voor alle steden in STEDEN_FUNDA."""
    results: List[Property] = []
    gezien_urls = set()

    for stad in STEDEN_FUNDA:
        stad_query = stad.replace("-", " ")
        for page in range(1, max_pages + 1):
            url = f"{BASE}/search?type=1&text={quote_plus(stad_query)}&page={page}"
            try:
                logger.info("Trovit: %s pagina %d", stad, page)
                r = requests.get(url, headers=HEADERS, timeout=20)
                if r.status_code != 200:
                    logger.debug("Trovit HTTP %d voor %s", r.status_code, stad)
                    break

                soup = BeautifulSoup(r.text, "lxml")
                articles = soup.select("article.snippet-listing")
                if not articles:
                    break

                for art in articles:
                    try:
                        a = art.select_one("a.js-listing")
                        if not a:
                            continue
                        title = a.get("title", "") or ""
                        tracker_url = a.get("href", "") or ""

                        # Prijs
                        prijs_el = art.select_one("span.price__actual")
                        prijs = _parse_prijs(prijs_el.get_text() if prijs_el else "")
                        if prijs < 25_000 or prijs > FIX_FLIP["max_aankoopprijs"] * 2:
                            continue

                        # Adres + type
                        addr_el = art.select_one("span.address_property-type")
                        if not addr_el:
                            continue
                        type_el = addr_el.select_one("b")
                        type_w = type_el.get_text(strip=True) if type_el else ""
                        loc_txt = re.sub(r"^.*?in\s+", "", addr_el.get_text(" ", strip=True))
                        parts = [x.strip() for x in loc_txt.split(",")]
                        postcode = parts[0] if len(parts) > 0 else ""
                        stad_parsed = parts[1] if len(parts) > 1 else stad.title()

                        # Oppervlakte uit icons
                        opp = 0
                        for li in art.select("div.snippet-listing-content-header-icons li p"):
                            txt = li.get_text(strip=True)
                            if "m" in txt and any(c.isdigit() for c in txt):
                                opp = _parse_opp(txt)
                                if opp > 0:
                                    break

                        if opp < 30:
                            continue

                        # Parse adres uit title (format: "Woning te koop: Straat 123 1234AB Stad ...")
                        adres_match = re.search(r':\s*(.+?)(?:\s+\d{4}\s?[A-Z]{2}|\s+in)', title)
                        adres = adres_match.group(1).strip() if adres_match else title[:80]

                        if tracker_url in gezien_urls:
                            continue
                        gezien_urls.add(tracker_url)

                        # Filter: huur eruit
                        if "huur" in title.lower() or "per maand" in title.lower():
                            continue

                        prop = Property(
                            source="trovit",
                            url=tracker_url,
                            adres=adres,
                            stad=stad_parsed,
                            postcode=postcode,
                            prijs=prijs,
                            opp_m2=opp,
                            prijs_per_m2=round(prijs / opp, 0) if opp > 0 else 0,
                            type_woning=type_w,
                        )
                        results.append(prop)

                    except Exception as e:
                        logger.debug("Trovit parse fout: %s", e)

                time.sleep(random.uniform(1.5, 3.0))  # wees beleefd

            except Exception as e:
                logger.error("Trovit fout %s p%d: %s", stad, page, e)
                break

    logger.info("Trovit: %d panden gevonden", len(results))
    return results
