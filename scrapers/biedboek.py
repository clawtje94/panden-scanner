"""
Biedboek.nl scraper — veilingen en biedingen op vastgoed.
Gebruikt de public JSON API (geen HTML scraping nodig).

Interessante deals zonder standaard berekening — hier geldt biedprijs,
niet vraagprijs, dus marges zijn anders.
"""
import logging
import requests
from typing import List
from datetime import datetime

from models import Property

logger = logging.getLogger(__name__)

BASE = "https://www.biedboek.nl"
API = f"{BASE}/api/real-estate/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
}

# Provincie enum uit de JS bundle
ZUID_HOLLAND = 12

# Type enum
TYPE_GEBOUW = 1        # kantoren, winkels, commercieel
TYPE_PERCEEL = 2       # grond, kavels
TYPE_RESIDENTIAL = 3   # meestal Caribisch, zelden ZH

# Status enum: alleen actieve biedingen
STATUS_KOOP = 100
STATUS_HUUR = 200
STATUS_VEILING = 1900


def scrape_biedboek() -> List[Property]:
    """Haal ALLE actieve Zuid-Holland biedboek objecten op."""
    results: List[Property] = []

    try:
        logger.info("Biedboek: API call naar %s", API)
        r = requests.get(API, headers=HEADERS, timeout=60)
        if r.status_code != 200:
            logger.error("Biedboek HTTP %d", r.status_code)
            return results

        records = r.json()
        logger.info("Biedboek: %d records totaal", len(records))

        for x in records:
            try:
                # Filter: Zuid-Holland, niet gearchiveerd
                if ZUID_HOLLAND not in (x.get("provinces") or []):
                    continue
                if x.get("isArchived"):
                    continue

                # Alleen types die relevant zijn
                typ = x.get("realEstateType")
                if typ not in (TYPE_GEBOUW, TYPE_PERCEEL, TYPE_RESIDENTIAL):
                    continue

                # Basis info
                t = x.get("translation") or {}
                bd = x.get("biddingData") or {}

                adres = t.get("address", "") or x.get("title", "")
                stad = t.get("city") or x.get("city", "")
                postcode = t.get("postalCode", "") or ""
                short_id = x.get("shortId", "")

                # Provincie 12 = Zuid-Holland, geen extra stad-filter nodig
                # (die is al gedaan via provincies filter hierboven)

                # Prijs: askingPrice of price of appraisedMarketValue
                prijs = x.get("askingPrice") or x.get("price") or x.get("appraisedMarketValue") or 0
                if not prijs or prijs < 10_000:
                    continue

                # Oppervlak
                opp = x.get("surface") or 0

                # Commercieel?
                is_comm = typ in (TYPE_GEBOUW, TYPE_PERCEEL)

                # Type beschrijving
                type_map = {
                    TYPE_GEBOUW: "bedrijfspand",
                    TYPE_PERCEEL: "perceel",
                    TYPE_RESIDENTIAL: "woning",
                }
                type_w = type_map.get(typ, "onbekend")

                # URL
                url = f"{BASE}/{short_id}"

                # Deadline (belangrijk voor veilingen)
                eind = bd.get("endDate", "")
                if eind:
                    try:
                        eind_dt = datetime.fromisoformat(eind.replace("Z", "+00:00"))
                        deadline_days = (eind_dt.date() - datetime.now().date()).days
                        if deadline_days < 0:
                            continue  # veiling is al voorbij
                    except:
                        pass

                bouwjaar = x.get("yearConstructed", 0) or 0

                prop = Property(
                    source="biedboek",
                    url=url,
                    adres=adres,
                    stad=stad or "Zuid-Holland",
                    postcode=postcode,
                    prijs=int(prijs),
                    opp_m2=int(opp) if opp else 0,
                    prijs_per_m2=round(prijs / opp, 0) if opp and opp > 0 else 0,
                    type_woning=type_w,
                    bouwjaar=int(bouwjaar) if bouwjaar else 0,
                    is_commercieel=is_comm,
                )
                results.append(prop)

            except Exception as e:
                logger.debug("Biedboek parse fout: %s", e)

    except Exception as e:
        logger.error("Biedboek fout: %s", e)

    logger.info("Biedboek: %d panden in Zuid-Holland", len(results))
    return results
