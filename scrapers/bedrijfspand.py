"""
Bedrijfspand.com scraper — commercieel vastgoed.
Selectors: div.clickable-div met data-url attribuut.
"""
import logging
import re
import time
import random
from typing import List

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from models import Property
from config import TRANSFORMATIE

logger = logging.getLogger(__name__)

BASE = "https://www.bedrijfspand.com"
STEDEN = ["den-haag", "rotterdam", "delft", "leiden", "zoetermeer", "dordrecht",
          "schiedam", "rijswijk"]
TYPES = ["winkelruimte", "kantoorruimte", "bedrijfsruimte"]


def _parse_prijs(tekst: str) -> int:
    if "maand" in tekst.lower() or "jaar" in tekst.lower() or "p.j." in tekst.lower():
        return 0  # huur, niet koop
    schoon = tekst.replace(".", "").replace(",", "").replace("\u20ac", "").replace("k.k.", "").strip()
    match = re.search(r'\d+', schoon)
    return int(match.group()) if match else 0


def _parse_opp(tekst: str) -> int:
    match = re.search(r'([\d.]+)\s*m2', tekst.replace(".", ""))
    return int(match.group(1)) if match else 0


def scrape_bedrijfspand() -> List[Property]:
    results: List[Property] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
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
        page = context.new_page()

        for stad in STEDEN:
            for obj_type in TYPES:
                url = f"{BASE}/plaats/{stad}/{obj_type}/?tt=2"  # tt=2 = koop
                try:
                    logger.info("Bedrijfspand: scraping %s/%s", stad, obj_type)
                    page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                    time.sleep(random.uniform(1.0, 2.0))

                    cards = page.query_selector_all('div.clickable-div')
                    if not cards:
                        # Fallback: probeer andere selectors
                        cards = page.query_selector_all('a.property-card')

                    for card in cards:
                        try:
                            # URL via data-url attribuut
                            href = card.get_attribute('data-url') or ''
                            if not href:
                                href = card.get_attribute('href') or ''
                            full_url = BASE + href if href.startswith('/') else href

                            # Adres
                            adres_el = card.query_selector('h4')
                            if not adres_el:
                                adres_el = card.query_selector('.property-card__address')
                            adres = adres_el.inner_text().strip() if adres_el else ""

                            # Prijs + oppervlakte (gecombineerd in <p>)
                            p_el = card.query_selector('p')
                            p_txt = p_el.inner_text().strip() if p_el else ""

                            prijs = _parse_prijs(p_txt)
                            opp = _parse_opp(p_txt)

                            # Skip huur
                            if prijs <= 0 or opp <= 0:
                                continue
                            if prijs > TRANSFORMATIE["max_aankoopprijs"]:
                                continue

                            prop = Property(
                                source="bedrijfspand",
                                url=full_url,
                                adres=adres,
                                stad=stad,
                                prijs=prijs,
                                opp_m2=opp,
                                prijs_per_m2=round(prijs / opp, 0) if opp > 0 else 0,
                                type_woning=obj_type,
                                is_commercieel=True,
                            )
                            results.append(prop)

                        except Exception as e:
                            logger.debug("Bedrijfspand parse fout: %s", e)

                    time.sleep(random.uniform(0.8, 1.5))

                except PWTimeout:
                    logger.warning("Bedrijfspand timeout %s/%s", stad, obj_type)
                except Exception as e:
                    logger.error("Bedrijfspand fout %s/%s: %s", stad, obj_type, e)

        browser.close()

    logger.info("Bedrijfspand: %d panden gevonden", len(results))
    return results
