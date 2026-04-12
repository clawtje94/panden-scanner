"""
Funda In Business scraper — commercieel vastgoed voor transformatie.
Gebruikt Playwright (Funda blokkeert headless requests met Akamai).
Selectors: li.search-result met data-test-* attributen.
"""
import logging
import re
import time
import random
from typing import List

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from models import Property
from config import STEDEN_FUNDA, TRANSFORMATIE

logger = logging.getLogger(__name__)

BASE = "https://www.fundainbusiness.nl"
TYPES = ["kantoor", "winkel", "bedrijfsruimte"]


def _parse_prijs(tekst: str) -> int:
    if not tekst or "aanvraag" in tekst.lower() or "n.o.t.k" in tekst.lower():
        return 0
    schoon = tekst.replace(".", "").replace(",", "").replace("\u20ac", "").replace("k.k.", "").strip()
    match = re.search(r'\d+', schoon)
    return int(match.group()) if match else 0


def _parse_opp(tekst: str) -> int:
    schoon = tekst.replace(".", "")
    match = re.search(r'(\d+)\s*m', schoon)
    return int(match.group(1)) if match else 0


def scrape_funda_ib(max_pages: int = 3) -> List[Property]:
    results: List[Property] = []

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

        for stad in STEDEN_FUNDA[:6]:
            for obj_type in TYPES:
                for p_num in range(1, max_pages + 1):
                    url = f"{BASE}/{obj_type}/{stad}/koop/p{p_num}/"
                    try:
                        logger.info("FiB: scraping %s/%s pagina %d", stad, obj_type, p_num)
                        page.goto(url, wait_until="domcontentloaded", timeout=25_000)
                        time.sleep(random.uniform(1.5, 3.0))

                        # Cookie banner
                        try:
                            page.click('button:has-text("Accepteren")', timeout=3_000)
                            time.sleep(0.5)
                        except PWTimeout:
                            pass

                        # CAPTCHA check
                        if page.query_selector('#fundaCaptchaInput'):
                            logger.warning("FiB CAPTCHA voor %s/%s — skip", stad, obj_type)
                            break

                        listings = page.query_selector_all('li.search-result')
                        if not listings:
                            break

                        for li in listings:
                            try:
                                # URL
                                a_tag = li.query_selector('a[data-search-result-item-anchor]')
                                if not a_tag:
                                    a_tag = li.query_selector('a[data-object-url-tracking]')
                                if not a_tag:
                                    continue
                                href = a_tag.get_attribute('href') or ''
                                full_url = href if href.startswith('http') else BASE + href

                                # Adres
                                adres_el = li.query_selector('h2.search-result__header-title, [data-test-search-result-header-title]')
                                adres = adres_el.inner_text().strip() if adres_el else ""

                                # Subtype
                                type_el = li.query_selector('h4.search-result__header-subtitle, [data-test-search-result-header-subtitle]')
                                type_txt = type_el.inner_text().strip() if type_el else obj_type

                                # Prijs
                                prijs_el = li.query_selector('span.search-result-price')
                                prijs_txt = prijs_el.inner_text().strip() if prijs_el else ""
                                prijs = _parse_prijs(prijs_txt)

                                # Oppervlakte
                                opp_el = li.query_selector('ul.search-result-kenmerken span[title="Oppervlakte"]')
                                if not opp_el:
                                    opp_el = li.query_selector('ul.search-result-kenmerken span')
                                opp_txt = opp_el.inner_text().strip() if opp_el else ""
                                opp = _parse_opp(opp_txt)

                                if prijs <= 0 or opp < TRANSFORMATIE["min_opp_m2"]:
                                    continue
                                if prijs > TRANSFORMATIE["max_aankoopprijs"]:
                                    continue
                                if opp > 0 and (prijs / opp) > TRANSFORMATIE["max_prijs_per_m2"]:
                                    continue

                                prop = Property(
                                    source="funda_ib",
                                    url=full_url,
                                    adres=adres,
                                    stad=stad,
                                    prijs=prijs,
                                    opp_m2=opp,
                                    prijs_per_m2=round(prijs / opp, 0) if opp > 0 else 0,
                                    type_woning=type_txt,
                                    is_commercieel=True,
                                )
                                results.append(prop)

                            except Exception as e:
                                logger.debug("FiB parse fout: %s", e)

                        time.sleep(random.uniform(1.5, 3.0))

                    except PWTimeout:
                        logger.warning("FiB timeout %s/%s pagina %d", stad, obj_type, p_num)
                    except Exception as e:
                        logger.error("FiB fout %s/%s: %s", stad, obj_type, e)

        browser.close()

    logger.info("FiB: %d panden gevonden", len(results))
    return results
