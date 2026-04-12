"""
Makelaar-website scrapers — panden staan hier vaak eerder online dan Funda.

Woningmakelaars:
  - Meesters Makelaars (Den Haag) — WordPress, server-rendered
  - Waltmann Makelaars (Dordrecht/Zuid-Holland) — Topsite.nl, server-rendered

Zakelijke makelaars:
  - COG Makelaars (Den Haag) — Laravel, server-rendered
  - NDRP Real Estate (Den Haag/Rijswijk) — WordPress + Elementor
"""
import logging
import re
import time
import random
from typing import List

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from models import Property

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "nl-NL,nl;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _parse_prijs(tekst: str) -> int:
    if not tekst or "aanvraag" in tekst.lower() or "n.o.t.k" in tekst.lower():
        return 0
    schoon = tekst.replace(".", "").replace(",", "").replace("\u20ac", "")
    schoon = schoon.replace("EUR", "").replace("k.k.", "").replace("v.o.n.", "")
    schoon = schoon.replace(",-", "").replace("-", "").strip()
    match = re.search(r'\d+', schoon)
    return int(match.group()) if match else 0


def _parse_opp(tekst: str) -> int:
    schoon = tekst.replace(".", "")
    match = re.search(r'(\d+)\s*m', schoon)
    return int(match.group(1)) if match else 0


# ── Meesters Makelaars (Den Haag) ────────────────────────────────────────────

def scrape_meesters(max_pages: int = 5) -> List[Property]:
    """Scrape Meesters Makelaars — WordPress, server-rendered HTML."""
    results: List[Property] = []
    base = "https://www.meestersmakelaars.nl"

    for page_num in range(1, max_pages + 1):
        url = f"{base}/woningen/page/{page_num}/" if page_num > 1 else f"{base}/woningen/"
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                break
            soup = BeautifulSoup(r.text, "lxml")

            items = soup.select("div.item-col.item-list div.item-inner, div.col-md-12.item-col div.item-inner")
            if not items:
                break

            for item in items:
                try:
                    # Status check
                    status_el = item.select_one("p.avaiable, p.available")
                    if status_el:
                        status = status_el.get_text(strip=True).lower()
                        if "verkocht" in status or "verhuurd" in status:
                            continue

                    # Adres
                    title_el = item.select_one("a.h5")
                    adres = title_el.get_text(strip=True) if title_el else ""
                    href = title_el.get("href", "") if title_el else ""
                    full_url = href if href.startswith("http") else base + href

                    # Postcode/stad
                    location_el = item.select_one("div.item-col-header p")
                    if not location_el:
                        # Probeer de p tag na het adres
                        ps = item.select("p")
                        location_el = ps[0] if ps else None
                    location_txt = location_el.get_text(strip=True) if location_el else ""
                    postcode = ""
                    stad = "Den Haag"
                    pc_match = re.match(r'(\d{4}\s*[A-Z]{2})\s+(.*)', location_txt)
                    if pc_match:
                        postcode = pc_match.group(1)
                        stad = pc_match.group(2)

                    # Prijs
                    prijs_el = item.select_one("p.price")
                    prijs = _parse_prijs(prijs_el.get_text()) if prijs_el else 0

                    # Oppervlakte
                    opp_el = item.select_one("span.living-square-meters")
                    opp = _parse_opp(opp_el.get_text()) if opp_el else 0

                    # Kamers
                    kamers_el = item.select_one("span.rooms-count")
                    kamers_txt = kamers_el.get_text() if kamers_el else ""
                    kamers_match = re.search(r'(\d+)', kamers_txt)
                    kamers = int(kamers_match.group(1)) if kamers_match else 0

                    if prijs <= 0 or opp <= 0:
                        continue

                    prop = Property(
                        source="meesters_makelaars",
                        url=full_url,
                        adres=adres,
                        stad=stad,
                        postcode=postcode,
                        prijs=prijs,
                        opp_m2=opp,
                        prijs_per_m2=round(prijs / opp, 0) if opp > 0 else 0,
                        kamers=kamers,
                    )
                    results.append(prop)

                except Exception as e:
                    logger.debug("Meesters parse fout: %s", e)

            time.sleep(random.uniform(0.8, 1.5))

        except Exception as e:
            logger.error("Meesters fout pagina %d: %s", page_num, e)

    logger.info("Meesters Makelaars: %d panden gevonden", len(results))
    return results


# ── Waltmann Makelaars (Dordrecht/ZH) ────────────────────────────────────────

def scrape_waltmann(max_pages: int = 5) -> List[Property]:
    """Scrape Waltmann Makelaars — Topsite.nl platform, server-rendered."""
    results: List[Property] = []
    base = "https://www.waltmann.com"

    for page_num in range(1, max_pages + 1):
        url = f"{base}/aanbod/?page={page_num}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                break
            soup = BeautifulSoup(r.text, "lxml")

            cards = soup.select("a.property.d-flex")
            if not cards:
                cards = soup.select("a.property")
            if not cards:
                break

            for card in cards:
                try:
                    href = card.get("href", "")
                    full_url = base + href if href.startswith("/") else href

                    # Adres
                    title_el = card.select_one("span.title")
                    adres = title_el.get_text(strip=True) if title_el else ""

                    # Stad
                    stad_el = card.select_one("span.city")
                    stad = stad_el.get_text(strip=True).title() if stad_el else ""

                    # Prijs
                    prijs_el = card.select_one("span.price")
                    prijs = _parse_prijs(prijs_el.get_text()) if prijs_el else 0

                    # Oppervlakte — in info-specs naast icon-x
                    specs = card.select("div.info-specs span")
                    opp = 0
                    kamers = 0
                    for spec in specs:
                        txt = spec.get_text(strip=True)
                        if "m2" in txt.lower() or "m\u00b2" in txt.lower():
                            opp = _parse_opp(txt)
                        elif re.match(r'^\d+$', txt.strip()):
                            # Waarschijnlijk kamers als het een los getal is
                            icon = spec.select_one("i.icon-bed")
                            if icon:
                                kamers = int(txt.strip())

                    # Fallback: zoek m2 in alle tekst
                    if opp == 0:
                        all_text = card.get_text()
                        m2_match = re.search(r'(\d+)\s*m', all_text)
                        if m2_match:
                            opp = int(m2_match.group(1))

                    if prijs <= 0 or opp <= 0:
                        continue

                    # Filter: alleen Zuid-Holland steden
                    stad_lower = stad.lower()
                    zh_steden = ["dordrecht", "rotterdam", "den haag", "delft", "leiden",
                                 "zoetermeer", "schiedam", "rijswijk", "westland",
                                 "pijnacker", "sliedrecht", "zwijndrecht", "papendrecht",
                                 "gorinchem", "hendrik-ido-ambacht", "barendrecht"]
                    if not any(s in stad_lower for s in zh_steden):
                        continue

                    prop = Property(
                        source="waltmann",
                        url=full_url,
                        adres=adres,
                        stad=stad,
                        prijs=prijs,
                        opp_m2=opp,
                        prijs_per_m2=round(prijs / opp, 0) if opp > 0 else 0,
                        kamers=kamers,
                    )
                    results.append(prop)

                except Exception as e:
                    logger.debug("Waltmann parse fout: %s", e)

            time.sleep(random.uniform(0.8, 1.5))

        except Exception as e:
            logger.error("Waltmann fout pagina %d: %s", page_num, e)

    logger.info("Waltmann: %d panden gevonden", len(results))
    return results


# ── COG Makelaars (Commercieel, Den Haag) ────────────────────────────────────

def scrape_cog(max_pages: int = 5) -> List[Property]:
    """Scrape COG Makelaars — Laravel, server-rendered, cleanste structuur."""
    results: List[Property] = []
    base = "https://www.cogmakelaars.nl"

    for page_num in range(1, max_pages + 1):
        url = f"{base}/aanbod/koop?page={page_num}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                break
            soup = BeautifulSoup(r.text, "lxml")

            section = soup.select_one("section.overview-aanbod")
            if not section:
                break
            cards = section.select("ul.card-regular > li")
            if not cards:
                cards = section.select("li")
            if not cards:
                break

            for card in cards:
                try:
                    a_tag = card.select_one('a[href*="/aanbod/id/"]')
                    if not a_tag:
                        a_tag = card.select_one("a")
                    if not a_tag:
                        continue

                    href = a_tag.get("href", "")
                    full_url = base + href if href.startswith("/") else href

                    # Status
                    status = a_tag.get("status", "").lower()
                    if "verhuurd" in status or "verkocht" in status:
                        continue

                    # Adres
                    h2 = a_tag.select_one("div.description h2")
                    adres = h2.get_text(strip=True) if h2 else ""

                    # Postcode + stad
                    h3 = a_tag.select_one("div.description h3")
                    location_txt = h3.get_text(strip=True) if h3 else ""
                    postcode = ""
                    stad = "Den Haag"
                    pc_match = re.match(r'(\d{4}\s*[A-Z]{2})\s+(.*)', location_txt)
                    if pc_match:
                        postcode = pc_match.group(1)
                        stad = pc_match.group(2)

                    # Prijs
                    detail_divs = a_tag.select("div.detail-list div")
                    prijs = 0
                    for div in detail_divs:
                        strong = div.select_one("strong")
                        if strong:
                            txt = strong.get_text(strip=True)
                            if "\u20ac" in txt or "EUR" in txt.upper():
                                prijs = _parse_prijs(txt)
                                break

                    # Oppervlakte + type
                    opp = 0
                    type_woning = ""
                    for div in detail_divs:
                        spans = div.select("span strong")
                        for s in spans:
                            txt = s.get_text(strip=True)
                            if "m2" in txt.lower() or "m\u00b2" in txt.lower():
                                opp = _parse_opp(txt)
                        type_spans = div.select("span span")
                        for s in type_spans:
                            txt = s.get_text(strip=True)
                            if txt and "m2" not in txt.lower():
                                type_woning = txt

                    if prijs <= 0 or opp <= 0:
                        continue

                    prop = Property(
                        source="cog_makelaars",
                        url=full_url,
                        adres=adres,
                        stad=stad,
                        postcode=postcode,
                        prijs=prijs,
                        opp_m2=opp,
                        prijs_per_m2=round(prijs / opp, 0) if opp > 0 else 0,
                        type_woning=type_woning,
                        is_commercieel=True,
                    )
                    results.append(prop)

                except Exception as e:
                    logger.debug("COG parse fout: %s", e)

            time.sleep(random.uniform(0.8, 1.5))

        except Exception as e:
            logger.error("COG fout pagina %d: %s", page_num, e)

    logger.info("COG Makelaars: %d panden gevonden", len(results))
    return results


# ── NDRP Real Estate (Commercieel, Den Haag/Rijswijk) ────────────────────────

def scrape_ndrp() -> List[Property]:
    """Scrape NDRP — WordPress + Elementor, deels JS-rendered."""
    results: List[Property] = []
    base = "https://ndrp.nl"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(
            user_agent=HEADERS["User-Agent"],
            viewport={"width": 1440, "height": 900},
            locale="nl-NL",
        )
        page = context.new_page()

        try:
            logger.info("NDRP: scraping aanbod")
            page.goto(f"{base}/aanbod/", wait_until="networkidle", timeout=30_000)
            time.sleep(2)

            # Elementor jet listing grid items
            items = page.query_selector_all('.jet-listing-grid__item')
            if not items:
                items = page.query_selector_all('.click-block[data-url]')

            for item in items:
                try:
                    # URL
                    click_el = item.query_selector('.click-block[data-url]')
                    if click_el:
                        href = click_el.get_attribute('data-url') or ''
                    else:
                        a = item.query_selector('a[href*="/aanbod/"]')
                        href = a.get_attribute('href') if a else ''
                    full_url = href if href.startswith('http') else base + href

                    # Prijs
                    prijs_el = item.query_selector('.aanbod-price-wrapper .aanbod-price, .aanbod-price')
                    prijs_txt = prijs_el.inner_text().strip() if prijs_el else ""
                    prijs = _parse_prijs(prijs_txt)

                    # Oppervlakte — zoek in alle tekst
                    all_text = item.inner_text()
                    opp_match = re.search(r'(\d[\d.]*)\s*m2', all_text.replace(".", ""))
                    opp = int(opp_match.group(1)) if opp_match else 0

                    # Adres — uit URL of titel
                    title_el = item.query_selector('h2, h3, .elementor-heading-title')
                    adres = title_el.inner_text().strip() if title_el else ""
                    if not adres and href:
                        # Parse adres uit URL
                        slug = href.rstrip('/').split('/')[-1]
                        adres = slug.replace('-', ' ').title()

                    # Stad uit URL of tekst
                    stad = ""
                    zh_steden = ["den-haag", "rotterdam", "delft", "leiden",
                                 "rijswijk", "zoetermeer", "schiedam", "dordrecht"]
                    url_lower = href.lower()
                    for s in zh_steden:
                        if s in url_lower:
                            stad = s.replace("-", " ").title()
                            break

                    if prijs <= 0 or opp <= 0:
                        continue

                    prop = Property(
                        source="ndrp",
                        url=full_url,
                        adres=adres,
                        stad=stad or "Den Haag",
                        prijs=prijs,
                        opp_m2=opp,
                        prijs_per_m2=round(prijs / opp, 0) if opp > 0 else 0,
                        is_commercieel=True,
                    )
                    results.append(prop)

                except Exception as e:
                    logger.debug("NDRP parse fout: %s", e)

        except PWTimeout:
            logger.warning("NDRP timeout")
        except Exception as e:
            logger.error("NDRP fout: %s", e)
        finally:
            browser.close()

    logger.info("NDRP: %d panden gevonden", len(results))
    return results


# ── Gecombineerde makelaar scraper ────────────────────────────────────────────

def scrape_makelaars() -> List[Property]:
    """Scrape alle makelaars en combineer resultaten."""
    results: List[Property] = []

    scrapers = [
        ("Meesters Makelaars", scrape_meesters),
        ("Waltmann", scrape_waltmann),
        ("COG Makelaars", scrape_cog),
        ("NDRP", scrape_ndrp),
    ]

    for naam, scraper_fn in scrapers:
        try:
            panden = scraper_fn()
            results.extend(panden)
        except Exception as e:
            logger.error("%s scraper gefaald: %s", naam, e)

    logger.info("Makelaars totaal: %d panden gevonden", len(results))
    return results
