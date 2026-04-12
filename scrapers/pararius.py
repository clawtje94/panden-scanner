"""
Pararius.nl scraper — alternatief voor Funda, geen bot-detectie.
"""
import logging
import re
import time
import random
from typing import List
from bs4 import BeautifulSoup
import requests
from models import Property
from config import STEDEN_FUNDA, FIX_FLIP

logger = logging.getLogger(__name__)

BASE = "https://www.pararius.nl"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "nl-NL,nl;q=0.9",
}


def scrape_pararius(max_pages: int = 2) -> List[Property]:
    results: List[Property] = []

    for stad in STEDEN_FUNDA[:5]:
        for page in range(1, max_pages + 1):
            url = f"{BASE}/koopwoningen/{stad}/page-{page}"
            try:
                r = requests.get(url, headers=HEADERS, timeout=15)
                if r.status_code != 200:
                    break
                soup = BeautifulSoup(r.text, "lxml")
                listings = soup.select("li.search-list__item--listing")
                if not listings:
                    break

                for li in listings:
                    try:
                        a = li.select_one("a.listing-search-item__link")
                        href = a["href"] if a else ""
                        full_url = BASE + href if href.startswith("/") else href

                        prijs_el = li.select_one(".listing-search-item__price")
                        prijs_txt = prijs_el.get_text(strip=True) if prijs_el else ""
                        prijs_match = re.search(r"[\d\.]+", prijs_txt.replace(".", ""))
                        prijs = int(prijs_match.group().replace(".", "")) if prijs_match else 0

                        opp_el = li.select_one(".listing-search-item__surface")
                        opp_txt = opp_el.get_text(strip=True) if opp_el else ""
                        opp_match = re.search(r"(\d+)", opp_txt)
                        opp = int(opp_match.group(1)) if opp_match else 0

                        adres_el = li.select_one(".listing-search-item__title")
                        adres = adres_el.get_text(strip=True) if adres_el else ""

                        if prijs <= 0 or opp <= 0:
                            continue
                        if prijs > FIX_FLIP["max_aankoopprijs"] * 1.5:
                            continue

                        prop = Property(
                            source="pararius",
                            url=full_url,
                            adres=adres,
                            stad=stad,
                            prijs=prijs,
                            opp_m2=opp,
                            prijs_per_m2=round(prijs / opp, 0) if opp > 0 else 0,
                        )
                        results.append(prop)

                    except Exception as e:
                        logger.debug("Pararius parse fout: %s", e)

                time.sleep(random.uniform(1.0, 2.0))

            except Exception as e:
                logger.error("Pararius fout %s: %s", stad, e)

    logger.info("Pararius: %d panden gevonden", len(results))
    return results
