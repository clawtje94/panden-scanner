"""
Funda.nl scraper — gebruikt Playwright om bot-detectie te omzeilen.
Zoekt naar woningen voor fix & flip en splitsing.
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
        f"&price=%22-%7B{max_prijs}%7D%22"
        f"&floor_area=%22{min_m2}-%22"
        f"&sort=%22date_down%22"
        f"&search_result={page}"
    )


def _parse_next_data(html: str) -> List[dict]:
    """Haal listings uit __NEXT_DATA__ JSON."""
    match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
        props = (
            data.get("props", {})
                .get("pageProps", {})
                .get("searchResult", {})
                .get("Properties", [])
        )
        return props or []
    except (json.JSONDecodeError, KeyError):
        return []


def _raw_to_property(raw: dict, stad: str) -> Property:
    prijs = raw.get("Price", {}).get("Sale", {}).get("Price", 0) or 0
    opp = raw.get("LivingArea", 0) or 0
    adres = f"{raw.get('Address', '')} {raw.get('HouseNumber', '')}".strip()
    pc = raw.get("ZipCode", "")
    url = FUNDA_BASE + "/detail/koop/" + raw.get("GlobalId", "")
    label = raw.get("EnergyLabel", "") or ""
    bouwjaar = raw.get("ConstructionYear") or 0
    kamers = raw.get("RoomCount") or 0
    foto = (raw.get("Photos") or [{}])[0].get("Uri", "")
    type_w = raw.get("ObjectType", "")

    p = Property(
        source="funda",
        url=url,
        adres=adres,
        stad=stad,
        postcode=pc,
        prijs=int(prijs),
        opp_m2=int(opp),
        prijs_per_m2=round(prijs / opp, 0) if opp > 0 else 0,
        type_woning=type_w,
        bouwjaar=int(bouwjaar) if bouwjaar else 0,
        energie_label=label,
        kamers=int(kamers) if kamers else 0,
        eigen_grond=raw.get("IsGroundFloor", True),
        datum_online=date.today(),
        foto_url=foto,
    )
    return p


def scrape_funda(max_pages: int = 3) -> List[Property]:
    """Scrape Funda voor fix & flip en splitsing kansen."""
    results: List[Property] = []

    # Combineer criteria: neem ruimste range
    max_prijs = max(FIX_FLIP["max_aankoopprijs"], SPLITSING["max_aankoopprijs"])
    min_m2 = min(FIX_FLIP["min_opp_m2"], SPLITSING["min_opp_m2"])

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
            viewport={"width": 390, "height": 844},
            locale="nl-NL",
        )
        # Verberg Playwright-fingerprint
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
        """)
        page = context.new_page()

        for stad in STEDEN_FUNDA:
            for p_num in range(1, max_pages + 1):
                url = _bouw_url(stad, max_prijs, min_m2, p_num)
                try:
                    logger.info("Funda: scraping %s pagina %d", stad, p_num)
                    page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                    time.sleep(random.uniform(1.5, 3.0))  # menselijk gedrag

                    # Sluit cookie-banner als aanwezig
                    try:
                        page.click('[data-testid="accept-cookies"]', timeout=2_000)
                    except PWTimeout:
                        pass

                    html = page.content()
                    raws = _parse_next_data(html)

                    if not raws:
                        logger.info("Geen resultaten voor %s pagina %d — stop", stad, p_num)
                        break

                    for raw in raws:
                        try:
                            prop = _raw_to_property(raw, stad)
                            if prop.prijs > 0 and prop.opp_m2 > 0:
                                results.append(prop)
                        except Exception as e:
                            logger.debug("Parse fout: %s", e)

                    time.sleep(random.uniform(2.0, 4.0))

                except PWTimeout:
                    logger.warning("Timeout voor %s pagina %d", stad, p_num)
                except Exception as e:
                    logger.error("Funda scrape fout %s: %s", stad, e)

        browser.close()

    logger.info("Funda: %d panden gevonden", len(results))
    return results
