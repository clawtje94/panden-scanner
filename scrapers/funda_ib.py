"""
Funda In Business scraper — commercieel vastgoed voor transformatie.
Gebruikt requests + BeautifulSoup (minder strikt dan Funda.nl).
"""
import logging
import re
import time
import random
from typing import List
from bs4 import BeautifulSoup
import requests
from models import Property
from config import STEDEN_FUNDA, TRANSFORMATIE

logger = logging.getLogger(__name__)

BASE = "https://www.fundainbusiness.nl"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "nl-NL,nl;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Referer": "https://www.fundainbusiness.nl/",
}


def _haal_pagina(url: str) -> BeautifulSoup | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            return BeautifulSoup(r.text, "lxml")
        logger.warning("FiB HTTP %d voor %s", r.status_code, url)
    except Exception as e:
        logger.error("FiB fout: %s", e)
    return None


def _parse_prijs(tekst: str) -> int:
    nrs = re.findall(r"[\d\.]+", tekst.replace(".", "").replace(",", ""))
    return int(nrs[0]) if nrs else 0


def scrape_funda_ib(max_pages: int = 3) -> List[Property]:
    results: List[Property] = []
    types = ["kantoor", "winkel", "bedrijfsruimte"]

    for stad in STEDEN_FUNDA[:6]:  # top 6 steden
        for obj_type in types:
            for page in range(1, max_pages + 1):
                url = f"{BASE}/{obj_type}/{stad}/koop/p{page}/"
                soup = _haal_pagina(url)
                if not soup:
                    break

                listings = soup.select("li.search-result")
                if not listings:
                    break

                for li in listings:
                    try:
                        a_tag = li.select_one("a.search-result__header-title")
                        if not a_tag:
                            continue
                        href = a_tag.get("href", "")
                        full_url = BASE + href if href.startswith("/") else href

                        adres_el = li.select_one(".search-result__header-title")
                        adres = adres_el.get_text(strip=True) if adres_el else ""

                        prijs_el = li.select_one(".search-result-price")
                        prijs_txt = prijs_el.get_text(strip=True) if prijs_el else ""
                        prijs = _parse_prijs(prijs_txt)

                        opp_el = li.select_one(".search-result-kenmerken")
                        opp_txt = opp_el.get_text() if opp_el else ""
                        opp_match = re.search(r"(\d+)\s*m", opp_txt)
                        opp = int(opp_match.group(1)) if opp_match else 0

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
                            type_woning=obj_type,
                            is_commercieel=True,
                        )
                        results.append(prop)

                    except Exception as e:
                        logger.debug("FiB parse fout: %s", e)

                time.sleep(random.uniform(1.0, 2.5))

    logger.info("FiB: %d panden gevonden", len(results))
    return results
