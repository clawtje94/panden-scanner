"""
Kavels/bouwgrond scraper — Kavelonline.nl JSON API.
"""
import logging
import json
import re
import requests
from typing import List
from bs4 import BeautifulSoup

from models import Property

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "X-Requested-With": "XMLHttpRequest",
}

ZH_POSTCODES = range(2200, 3000)  # Zuid-Holland postcode range


def _is_zuid_holland(tekst: str) -> bool:
    """Check of een locatietekst in Zuid-Holland ligt."""
    t = tekst.lower()
    zh_steden = [
        "den haag", "'s-gravenhage", "rotterdam", "delft", "leiden",
        "zoetermeer", "schiedam", "rijswijk", "dordrecht", "gouda",
        "alphen", "westland", "vlaardingen", "maassluis", "capelle",
        "spijkenisse", "barendrecht", "ridderkerk", "pijnacker",
        "nootdorp", "voorburg", "leidschendam", "wassenaar",
        "katwijk", "noordwijk", "oegstgeest", "voorschoten",
        "papendrecht", "sliedrecht", "zwijndrecht",
    ]
    if any(s in t for s in zh_steden):
        return True
    # Check postcode range
    pc_match = re.search(r'(\d{4})', tekst)
    if pc_match:
        pc = int(pc_match.group(1))
        return pc in ZH_POSTCODES
    return False


def scrape_kavels(max_pages: int = 10) -> List[Property]:
    """Scrape Kavelonline.nl voor bouwkavels in Zuid-Holland."""
    results = []

    for offset in range(0, max_pages * 20, 20):
        try:
            r = requests.get(
                "https://kavelonline.nl/pages/load_more_kavels",
                params={"offset": offset},
                headers=HEADERS,
                timeout=15,
            )
            if r.status_code != 200:
                break

            data = r.json()
            html = data.get("html", "")
            if not html or html.strip() == "":
                break

            soup = BeautifulSoup(html, "lxml")
            cards = soup.select("div.niew-itm")
            if not cards:
                break

            for card in cards:
                try:
                    a = card.select_one("a")
                    if not a:
                        continue
                    url = a.get("href", "")

                    title_el = card.select_one("strong")
                    title = title_el.get_text(strip=True) if title_el else ""

                    loc_el = card.select_one("p.loc")
                    loc = loc_el.get_text(strip=True) if loc_el else ""

                    # Filter Zuid-Holland
                    if not _is_zuid_holland(f"{title} {loc}"):
                        continue

                    # Oppervlakte
                    opp = 0
                    opp_els = card.select("p.opp span")
                    for opp_el in opp_els:
                        txt = opp_el.get_text(strip=True)
                        m = re.search(r'(\d+)', txt.replace(".", ""))
                        if m and "m2" in txt.lower() or "m²" in txt.lower():
                            opp = int(m.group(1))
                            break

                    # Prijs
                    prijs = 0
                    for p_el in card.select("p.opp span, p span"):
                        txt = p_el.get_text(strip=True)
                        if "€" in txt or "EUR" in txt.upper():
                            prijs_clean = re.sub(r'[^\d]', '', txt.split("K.K")[0].split("k.k")[0])
                            if prijs_clean:
                                prijs = int(prijs_clean)
                                break

                    # Foto
                    img = card.select_one("img")
                    foto = img.get("src", "") if img else ""

                    # Stad uit locatie
                    stad = ""
                    loc_parts = loc.split(",")
                    if len(loc_parts) > 1:
                        stad = loc_parts[-1].strip()
                    elif loc:
                        stad = loc.split()[-1] if loc.split() else ""

                    prop = Property(
                        source="kavel_kavelonline",
                        url=url,
                        adres=title or loc,
                        stad=stad,
                        prijs=prijs,
                        opp_m2=opp,
                        prijs_per_m2=round(prijs / opp) if prijs and opp > 0 else 0,
                        type_woning="bouwkavel",
                        foto_url=foto,
                    )
                    prop.calc = {"is_kavel": True}
                    results.append(prop)

                except Exception as e:
                    logger.debug("Kavelonline parse fout: %s", e)

        except Exception as e:
            logger.error("Kavelonline fout offset %d: %s", offset, e)
            break

    logger.info("Kavelonline: %d kavels in Zuid-Holland", len(results))
    return results
