"""
Bedrijfspand.com scraper — betrouwbaar, werkt goed.
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

BASE = "https://www.bedrijfspand.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "nl-NL,nl;q=0.9",
}
TYPES = ["winkelruimte", "kantoorruimte", "bedrijfsruimte"]


def _parse_prijs(tekst: str) -> int:
    schoon = tekst.replace(".", "").replace(",", "").replace("\u20ac", "").replace("k.k.", "").strip()
    match = re.search(r"\d+", schoon)
    return int(match.group()) if match else 0


def _parse_opp(tekst: str) -> int:
    match = re.search(r"(\d+)", tekst.replace(".", ""))
    return int(match.group(1)) if match else 0


def scrape_bedrijfspand() -> List[Property]:
    results: List[Property] = []
    steden = ["den-haag", "rotterdam", "delft", "leiden", "zoetermeer", "dordrecht"]

    for stad in steden:
        for obj_type in TYPES:
            url = f"{BASE}/plaats/{stad}/{obj_type}/?tt=2"  # tt=2 = koop
            try:
                r = requests.get(url, headers=HEADERS, timeout=15)
                if r.status_code != 200:
                    continue
                soup = BeautifulSoup(r.text, "lxml")

                for card in soup.select("a.property-card"):
                    try:
                        href = card.get("href", "")
                        full_url = BASE + href if href.startswith("/") else href

                        prijs_el = card.select_one(".property-card__price")
                        prijs = _parse_prijs(prijs_el.get_text()) if prijs_el else 0

                        opp_el = card.select_one(".property-card__surface")
                        opp = _parse_opp(opp_el.get_text()) if opp_el else 0

                        adres_el = card.select_one(".property-card__address")
                        adres = adres_el.get_text(strip=True) if adres_el else ""

                        # Filter: alleen koop, niet huur
                        if "maand" in (prijs_el.get_text() if prijs_el else "") or "jaar" in (prijs_el.get_text() if prijs_el else ""):
                            continue

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

                time.sleep(random.uniform(0.8, 1.8))

            except Exception as e:
                logger.error("Bedrijfspand fout %s/%s: %s", stad, obj_type, e)

    logger.info("Bedrijfspand: %d panden gevonden", len(results))
    return results
