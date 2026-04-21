"""
Vastiva.nl scraper — beleggingspanden via server-rendered PHP.
Scrapet landelijk aanbod met focus op Zuid-Holland: adres, prijs, type, oppervlakte.

URL: https://www.vastiva.nl/beleggingspanden/koop/nederland/zuid-holland/
Tech: Custom PHP, server-rendered HTML. Listings in .property cards.
"""
import logging
import re
import requests
from typing import List
from datetime import date
from bs4 import BeautifulSoup

from models import Property

logger = logging.getLogger(__name__)

BASE = "https://www.vastiva.nl"

# Pagina's om te scrapen — Zuid-Holland specifiek + landelijk beleggingspanden
URLS = [
    f"{BASE}/beleggingspanden/koop/nederland/zuid-holland/",
    f"{BASE}/beleggingspanden/koop/nederland/",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "nl-NL,nl;q=0.9",
}

# Zuid-Holland steden voor filtering van landelijke resultaten
ZH_STEDEN = {
    "rotterdam", "den haag", "'s-gravenhage", "leiden", "delft",
    "dordrecht", "zoetermeer", "schiedam", "rijswijk", "gouda",
    "alphen aan den rijn", "vlaardingen", "leidschendam", "voorburg",
    "katwijk", "westland", "pijnacker", "nootdorp", "capelle aan den ijssel",
    "papendrecht", "sliedrecht", "zwijndrecht", "barendrecht",
    "spijkenisse", "hellevoetsluis", "brielle", "maassluis",
    "ridderkerk", "gorinchem", "nieuwkoop", "waddinxveen",
    "krimpen aan den ijssel", "hendrik-ido-ambacht", "oud-beijerland",
    "lisse", "voorschoten", "wassenaar", "oegstgeest",
}


def _parse_euro(text: str) -> int:
    """Parse '€ 788.000' of '&euro; 1.600.000' naar int."""
    cleaned = re.sub(r"[^\d]", "", text)
    return int(cleaned) if cleaned else 0


def _is_zh(stad: str, listing_url: str) -> bool:
    """Check of een listing in Zuid-Holland ligt (op basis van listing URL of stad)."""
    if "zuid-holland" in listing_url.lower():
        return True
    return stad.lower().strip() in ZH_STEDEN


def scrape_vastiva() -> List[Property]:
    """Scrape Vastiva beleggingspanden met focus op Zuid-Holland."""
    results: List[Property] = []
    seen_urls = set()

    for page_url in URLS:
        try:
            logger.info("Vastiva: fetching %s", page_url)
            r = requests.get(page_url, headers=HEADERS, timeout=30)
            if r.status_code != 200:
                logger.warning("Vastiva HTTP %d voor %s", r.status_code, page_url)
                continue

            soup = BeautifulSoup(r.text, "html.parser")

            # Elke listing: <a class="property"> met daarin property-info divs
            cards = soup.select("a.property")
            logger.info("Vastiva: %d cards op %s", len(cards), page_url)

            for card in cards:
                try:
                    href = card.get("href", "")
                    if not href or href in seen_urls:
                        continue

                    # Alleen beleggingspanden URLs
                    if "/beleggingspanden/" not in href:
                        continue

                    seen_urls.add(href)
                    url = BASE + href if href.startswith("/") else href

                    # Titel en stad
                    title_el = card.select_one(".property-title")
                    city_el = card.select_one(".property-city")
                    adres = title_el.get_text(strip=True) if title_el else ""
                    stad = city_el.get_text(strip=True) if city_el else ""

                    # Prijs uit .property-subinfo span.price
                    subinfo = card.find_next_sibling("div", class_="property-subinfo")
                    if not subinfo:
                        # Soms is subinfo een sibling van de parent
                        parent = card.parent
                        subinfo = parent.select_one(".property-subinfo") if parent else None

                    prijs = 0
                    type_woning = ""
                    opp = 0
                    bouwjaar = 0

                    if subinfo:
                        price_el = subinfo.select_one("span.price")
                        if price_el:
                            prijs = _parse_euro(price_el.get_text())

                        # Type en oppervlakte uit de subinfo flex divs
                        info_divs = subinfo.select(
                            ".d-flex div"
                        )
                        for div in info_divs:
                            txt = div.get_text(strip=True)
                            if not txt or txt == "|":
                                continue
                            # Eerste niet-lege div = type
                            if not type_woning and "m" not in txt and not txt.isdigit():
                                type_woning = txt
                            # m2 oppervlakte
                            m = re.search(r"(\d+)\s*m", txt)
                            if m:
                                opp = int(m.group(1))
                            # Bouwjaar (4-cijferig getal)
                            m = re.search(r"\b(1[89]\d{2}|20[0-2]\d)\b", txt)
                            if m:
                                bouwjaar = int(m.group(1))

                    if prijs <= 0:
                        continue

                    # Filter op Zuid-Holland (check listing URL, niet page URL)
                    if not _is_zh(stad, url):
                        continue

                    # Foto
                    img = card.select_one("img")
                    foto_url = ""
                    if img:
                        foto_url = img.get("data-src", "") or img.get("src", "")
                        if foto_url and not foto_url.startswith("http"):
                            foto_url = BASE + foto_url

                    prop = Property(
                        source="vastiva",
                        url=url,
                        adres=adres,
                        stad=stad,
                        prijs=prijs,
                        opp_m2=opp,
                        prijs_per_m2=round(prijs / opp, 0) if opp > 0 else 0,
                        type_woning=type_woning,
                        bouwjaar=bouwjaar,
                        is_commercieel="woning" not in type_woning.lower()
                        and "appartement" not in type_woning.lower(),
                        datum_online=date.today(),
                        foto_url=foto_url,
                    )
                    results.append(prop)

                except Exception as e:
                    logger.debug("Vastiva parse fout: %s", e)

        except Exception as e:
            logger.error("Vastiva fout voor %s: %s", page_url, e)

    logger.info("Vastiva: %d beleggingspanden in Zuid-Holland", len(results))
    return results
