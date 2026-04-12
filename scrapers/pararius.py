"""
Pararius.nl scraper — gebruikt Playwright (403 op requests).
Selectors: section.listing-search-item
"""
import logging
import re
import time
import random
from typing import List

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from models import Property
from config import STEDEN_FUNDA, FIX_FLIP, SPLITSING

logger = logging.getLogger(__name__)

BASE = "https://www.pararius.nl"


def scrape_pararius(max_pages: int = 3) -> List[Property]:
    results: List[Property] = []
    max_prijs = max(FIX_FLIP["max_aankoopprijs"], SPLITSING["max_aankoopprijs"])

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage",
                   "--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
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
                url = f"{BASE}/koopwoningen/{stad}/page-{p_num}"
                try:
                    logger.info("Pararius: scraping %s pagina %d", stad, p_num)
                    page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                    time.sleep(random.uniform(1.5, 3.0))

                    # Cookie banner
                    try:
                        page.click('button:has-text("Accepteren"), #onetrust-accept-btn-handler', timeout=3_000)
                        time.sleep(0.5)
                    except PWTimeout:
                        pass

                    listings = page.query_selector_all('section.listing-search-item')
                    if not listings:
                        # Fallback selector
                        listings = page.query_selector_all('li.search-list__item--listing section')
                    if not listings:
                        logger.info("Pararius: geen resultaten %s pagina %d", stad, p_num)
                        break

                    for section in listings:
                        try:
                            # URL
                            a = section.query_selector('a.listing-search-item__link--title')
                            if not a:
                                a = section.query_selector('a.listing-search-item__link')
                            if not a:
                                continue
                            href = a.get_attribute('href') or ''
                            full_url = BASE + href if href.startswith('/') else href

                            # Adres
                            title_el = section.query_selector('.listing-search-item__link--title')
                            adres = title_el.inner_text().strip() if title_el else ""

                            # Postcode + stad
                            sub_el = section.query_selector('.listing-search-item__sub-title')
                            sub_txt = sub_el.inner_text().strip() if sub_el else ""
                            postcode = ""
                            stad_parsed = stad
                            pc_match = re.match(r'(\d{4}\s*[A-Z]{2})\s+(.*)', sub_txt)
                            if pc_match:
                                postcode = pc_match.group(1)
                                stad_parsed = pc_match.group(2).split('(')[0].strip()

                            # Prijs
                            prijs_el = section.query_selector('.listing-search-item__price-main, .listing-search-item__price')
                            prijs_txt = prijs_el.inner_text().strip() if prijs_el else ""
                            prijs_clean = re.sub(r'[^\d]', '', prijs_txt.split('k.k.')[0].split('v.o.n.')[0])
                            prijs = int(prijs_clean) if prijs_clean else 0

                            # Oppervlakte
                            opp_el = section.query_selector('.illustrated-features__item--surface-area')
                            opp_txt = opp_el.inner_text().strip() if opp_el else ""
                            opp_match = re.search(r'(\d+)', opp_txt)
                            opp = int(opp_match.group(1)) if opp_match else 0

                            # Kamers
                            kamers_el = section.query_selector('.illustrated-features__item--number-of-rooms')
                            kamers_txt = kamers_el.inner_text().strip() if kamers_el else ""
                            kamers_match = re.search(r'(\d+)', kamers_txt)
                            kamers = int(kamers_match.group(1)) if kamers_match else 0

                            # Bouwjaar
                            bj_el = section.query_selector('.illustrated-features__item--construction-period')
                            bj_txt = bj_el.inner_text().strip() if bj_el else ""
                            bj_match = re.search(r'(\d{4})', bj_txt)
                            bouwjaar = int(bj_match.group(1)) if bj_match else 0

                            if prijs <= 0 or opp <= 0:
                                continue
                            if prijs > max_prijs * 1.2:
                                continue

                            prop = Property(
                                source="pararius",
                                url=full_url,
                                adres=adres,
                                stad=stad_parsed,
                                postcode=postcode,
                                prijs=prijs,
                                opp_m2=opp,
                                prijs_per_m2=round(prijs / opp, 0) if opp > 0 else 0,
                                kamers=kamers,
                                bouwjaar=bouwjaar,
                            )
                            results.append(prop)

                        except Exception as e:
                            logger.debug("Pararius parse fout: %s", e)

                    time.sleep(random.uniform(2.0, 4.0))

                except PWTimeout:
                    logger.warning("Pararius timeout %s pagina %d", stad, p_num)
                except Exception as e:
                    logger.error("Pararius fout %s: %s", stad, e)

        browser.close()

    logger.info("Pararius: %d panden gevonden", len(results))
    return results
