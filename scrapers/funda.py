"""
Funda.nl scraper — gebruikt Playwright voor bot-detectie.
Zoekt via JSON-LD listing URLs + HTML selectors voor data.
"""
import json
import logging
import re
import time
import random
from typing import List
from datetime import date

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from models import Property
from config import STEDEN_FUNDA, FIX_FLIP, SPLITSING

logger = logging.getLogger(__name__)

FUNDA_BASE = "https://www.funda.nl"


def _bouw_url(stad: str, max_prijs: int, min_m2: int, page: int = 1) -> str:
    return (
        f"{FUNDA_BASE}/zoeken/koop/"
        f"?selected_area=%5B%22{stad}%22%5D"
        f"&price=%22-{max_prijs}%22"
        f"&floor_area=%22{min_m2}-%22"
        f"&sort=%22date_down%22"
        f"&search_result={page}"
    )


def _extract_json_ld_urls(html: str) -> List[str]:
    """Haal listing URLs uit JSON-LD itemListElement."""
    urls = []
    for match in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL):
        try:
            data = json.loads(match.group(1))
            items = data.get("itemListElement", [])
            for item in items:
                url = item.get("url", "")
                if url and "/koop/" in url:
                    urls.append(url)
        except (json.JSONDecodeError, AttributeError):
            continue
    return urls


def _parse_listing_cards(page) -> List[dict]:
    """Parse listing cards uit de zoekresultaten pagina."""
    listings = []
    cards = page.query_selector_all('[data-test-id="search-result-item"], .flex.flex-col.sm\\:flex-row')
    if not cards:
        cards = page.query_selector_all('div.border-b.pb-3')

    for card in cards:
        try:
            info = {}

            # Adres
            title_el = card.query_selector('h2 a span.truncate')
            if title_el:
                info["adres"] = title_el.inner_text().strip()

            # Postcode + stad
            sub_el = card.query_selector('h2 a div.truncate.text-neutral-80')
            if sub_el:
                sub_text = sub_el.inner_text().strip()
                pc_match = re.match(r'(\d{4}\s*[A-Z]{2})\s+(.*)', sub_text)
                if pc_match:
                    info["postcode"] = pc_match.group(1)
                    info["stad"] = pc_match.group(2)

            # Prijs
            prijs_el = card.query_selector('div.font-semibold div.truncate')
            if prijs_el:
                prijs_txt = prijs_el.inner_text().strip()
                prijs_clean = re.sub(r'[^\d]', '', prijs_txt.split('k.k.')[0].split('v.o.n.')[0])
                if prijs_clean:
                    info["prijs"] = int(prijs_clean)

            # URL
            link_el = card.query_selector('h2 a')
            if link_el:
                href = link_el.get_attribute('href') or ''
                info["url"] = FUNDA_BASE + href if href.startswith('/') else href

            # Features (m², kamers, energielabel)
            features = card.query_selector_all('ul.flex.flex-wrap li')
            for feat in features:
                txt = feat.inner_text().strip()
                m2_match = re.search(r'(\d+)\s*m', txt)
                if m2_match and "opp_m2" not in info:
                    info["opp_m2"] = int(m2_match.group(1))
                label_match = re.match(r'^[A-G][+\-]*$', txt.strip())
                if label_match:
                    info["energie_label"] = txt.strip()

            # Status (verkocht = skip)
            status_el = card.query_selector('span.rounded.px-2.py-0\\.5.text-xs.font-semibold')
            if status_el:
                status_txt = status_el.inner_text().strip().lower()
                if 'verkocht' in status_txt or 'verhuurd' in status_txt:
                    continue

            if info.get("prijs") and info.get("url"):
                listings.append(info)

        except Exception as e:
            logger.debug("Funda card parse fout: %s", e)

    return listings


def scrape_funda(max_pages: int = 3) -> List[Property]:
    """Scrape Funda voor fix & flip en splitsing kansen."""
    results: List[Property] = []
    max_prijs = max(FIX_FLIP["max_aankoopprijs"], SPLITSING["max_aankoopprijs"])
    min_m2 = min(FIX_FLIP["min_opp_m2"], SPLITSING["min_opp_m2"])

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage",
                   "--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
            locale="nl-NL",
        )
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)
        page = context.new_page()

        for stad in STEDEN_FUNDA:
            for p_num in range(1, max_pages + 1):
                url = _bouw_url(stad, max_prijs, min_m2, p_num)
                try:
                    logger.info("Funda: scraping %s pagina %d", stad, p_num)
                    page.goto(url, wait_until="domcontentloaded", timeout=25_000)
                    time.sleep(random.uniform(2.0, 4.0))

                    # Cookie banner
                    try:
                        page.click('button:has-text("Accepteren")', timeout=3_000)
                        time.sleep(0.5)
                    except PWTimeout:
                        pass

                    # Check voor CAPTCHA
                    if page.query_selector('#fundaCaptchaInput'):
                        logger.warning("Funda CAPTCHA gedetecteerd voor %s — skip", stad)
                        break

                    # Methode 1: parse listing cards
                    listings = _parse_listing_cards(page)

                    # Methode 2: fallback naar JSON-LD URLs
                    if not listings:
                        html = page.content()
                        ld_urls = _extract_json_ld_urls(html)
                        for ld_url in ld_urls:
                            listings.append({"url": ld_url, "stad": stad})

                    if not listings:
                        logger.info("Geen resultaten voor %s pagina %d", stad, p_num)
                        break

                    for info in listings:
                        try:
                            prijs = info.get("prijs", 0)
                            opp = info.get("opp_m2", 0)
                            prop = Property(
                                source="funda",
                                url=info.get("url", ""),
                                adres=info.get("adres", ""),
                                stad=info.get("stad", stad),
                                postcode=info.get("postcode", ""),
                                prijs=prijs,
                                opp_m2=opp,
                                prijs_per_m2=round(prijs / opp, 0) if opp > 0 else 0,
                                energie_label=info.get("energie_label", ""),
                                datum_online=date.today(),
                            )
                            if prop.prijs > 0 and prop.opp_m2 > 0:
                                results.append(prop)
                        except Exception as e:
                            logger.debug("Funda property fout: %s", e)

                    time.sleep(random.uniform(2.0, 5.0))

                except PWTimeout:
                    logger.warning("Timeout voor %s pagina %d", stad, p_num)
                except Exception as e:
                    logger.error("Funda scrape fout %s: %s", stad, e)

        browser.close()

    logger.info("Funda: %d panden gevonden", len(results))
    return results
