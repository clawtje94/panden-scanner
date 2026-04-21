"""
Beleggingspanden.nl scraper — server-rendered Blazor site.
Scrapet Zuid-Holland listings met: adres, prijs, huursom, factor, BAR, oppervlakte.

URL: https://www.beleggingspanden.nl/nl/aanbod/provincie/Zuid-Holland
Tech: Blazor Server (HTML bevat alle listing data, geen JS rendering nodig).
"""
import logging
import re
import requests
from typing import List
from datetime import date
from bs4 import BeautifulSoup

from models import Property

logger = logging.getLogger(__name__)

BASE = "https://www.beleggingspanden.nl"
URL = f"{BASE}/nl/aanbod/provincie/Zuid-Holland"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "nl-NL,nl;q=0.9",
}

# CSS selectors (Blazor component met b- attributes)
# Elke listing: <div id="<numeric>" class="building__row">
# Bevat:
#   - <a href="/nl/aanbod/..."> met stad + straat
#   - Prijs in <p> met &#x20AC; prefix
#   - .building__row_otherinfo spans: Huursom, Vloeroppervlakte, Factor, BAR
#   - Status indicator: .building__commercial-status + "Te koop"/"Verkocht"


def _parse_euro(text: str) -> int:
    """Parse '€ 237.500' of '&#x20AC; 237.500' naar int."""
    cleaned = re.sub(r"[^\d]", "", text)
    return int(cleaned) if cleaned else 0


def _parse_float(text: str) -> float:
    """Parse '23,6' of '4.2%' naar float."""
    cleaned = text.replace("%", "").replace(",", ".").strip()
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def scrape_beleggingspanden() -> List[Property]:
    """Scrape alle Zuid-Holland beleggingspanden."""
    results: List[Property] = []

    try:
        logger.info("Beleggingspanden.nl: fetching %s", URL)
        r = requests.get(URL, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            logger.error("Beleggingspanden.nl HTTP %d", r.status_code)
            return results

        soup = BeautifulSoup(r.text, "html.parser")

        # Elke listing is een div.building__row met numeriek id
        rows = soup.select("div.building__row")
        logger.info("Beleggingspanden.nl: %d rows gevonden", len(rows))

        for row in rows:
            try:
                listing_id = row.get("id", "")

                # Status check — skip verkochte objecten
                status_el = row.select_one(".building__commercial-status")
                status_text_el = row.select_one(
                    "span.text-primary-s.fw-bold"
                )
                status = status_text_el.get_text(strip=True) if status_text_el else ""
                if "verkocht" in status.lower() or "optie" in status.lower():
                    continue

                # Adres: er zijn 2 links met /nl/aanbod/ — de eerste is de
                # afbeelding, de tweede (in .building__row_content) bevat de tekst.
                links = row.select("a[href*='/nl/aanbod/']")
                if not links:
                    continue

                # Gebruik de link met een <p> child (tekst-link)
                link = None
                for lnk in links:
                    if lnk.select_one("p"):
                        link = lnk
                        break
                if not link:
                    link = links[-1]  # fallback: laatste link

                href = link.get("href", "")
                url = BASE + href if href.startswith("/") else href

                # Stad en straat uit de link
                stad_el = link.select_one("p.fw-bold")
                if stad_el:
                    # Structuur: "Den Haag, <span>Thorbeckelaan 731</span>"
                    straat_el = stad_el.select_one("span")
                    straat = straat_el.get_text(strip=True) if straat_el else ""
                    full_text = stad_el.get_text(strip=True)
                    # Stad = alles voor de komma of alles minus straatnaam
                    stad = full_text.replace(straat, "").strip().rstrip(",").strip()
                    adres = f"{straat}, {stad}" if straat else stad
                else:
                    # Fallback: parse adres uit URL
                    adres = link.get_text(strip=True) or ""
                    stad = ""
                    m = re.match(r"/nl/aanbod/nederland-(.+)-\d+$", href)
                    if m:
                        parts = m.group(1).rsplit("-", 1)
                        stad = parts[0].replace("-", " ").title() if parts else ""

                # Prijs: <p> met € teken
                prijs = 0
                prijs_els = row.select("p.text-primary-blue.fw-bold")
                for pe in prijs_els:
                    txt = pe.get_text(strip=True)
                    if "\u20ac" in txt or "€" in txt or "20AC" in txt:
                        prijs = _parse_euro(txt)
                        break

                # Type woning
                type_el = row.select_one("p.mt-primary-4:not(.text-primary-blue)")
                type_woning = type_el.get_text(strip=True) if type_el else ""

                # Detail info: huursom, oppervlakte, factor, BAR
                huursom = 0
                opp = 0
                factor = 0.0
                bar = 0.0

                info_spans = row.select(
                    ".building__row_otherinfo span.text-primary-xs"
                )
                for span in info_spans:
                    txt = span.get_text(" ", strip=True)
                    if "Huursom" in txt:
                        huursom = _parse_euro(txt)
                    elif "Vloeroppervlakte" in txt or "Opp" in txt:
                        m = re.search(r"(\d+)", txt.replace(".", ""))
                        if m:
                            opp = int(m.group(1))
                    elif "Factor" in txt:
                        m = re.search(r"[\d,]+", txt.replace("Factor", ""))
                        if m:
                            factor = _parse_float(m.group())
                    elif "BAR" in txt:
                        m = re.search(r"[\d,]+%?", txt.replace("BAR", ""))
                        if m:
                            bar = _parse_float(m.group())

                if prijs <= 0:
                    continue

                # Makelaar logo/naam
                broker_img = row.select_one("img.building-row__broker-logo")
                makelaar = broker_img.get("title", "") if broker_img else ""

                # Foto
                foto_el = row.select_one(".building__row_image img")
                foto_url = ""
                if foto_el:
                    foto_url = foto_el.get("src", "") or foto_el.get("data-src", "")

                # Beleggingspanden zijn per definitie verhuurde objecten
                # (huursom + factor + BAR = verhuurd gegeven). Flag ze als
                # belegging, niet als ontwikkelkans. Scanner besluit of ze
                # alsnog een aparte "beleggingen"-lijst in gaan.
                is_verhuurd = huursom > 0 or "verhuurd" in type_woning.lower()

                prop = Property(
                    source="beleggingspanden",
                    url=url,
                    adres=adres,
                    stad=stad,
                    prijs=prijs,
                    opp_m2=opp,
                    prijs_per_m2=round(prijs / opp, 0) if opp > 0 else 0,
                    type_woning=type_woning,
                    is_commercieel="woning" not in type_woning.lower()
                    and "appartement" not in type_woning.lower(),
                    datum_online=date.today(),
                    foto_url=foto_url,
                    makelaar=makelaar,
                )

                # Bewaar extra beleggingsdata in calc dict
                prop.calc = {
                    "huursom_jaar": huursom,
                    "factor": factor,
                    "bar_pct": bar,
                    "makelaar": makelaar,
                    "listing_id": listing_id,
                    "is_belegging": True,
                    "is_verhuurd": is_verhuurd,
                }

                results.append(prop)

            except Exception as e:
                logger.debug("Beleggingspanden parse fout: %s", e)

    except Exception as e:
        logger.error("Beleggingspanden.nl fout: %s", e)

    logger.info("Beleggingspanden.nl: %d panden in Zuid-Holland", len(results))
    return results
