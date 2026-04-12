"""
Funda.nl scraper — via pyfunda (mobile app API, geen CAPTCHA).
Zoekt naar woningen voor fix & flip en splitsing.
"""
import logging
import time
from typing import List
from datetime import date

from funda import Funda
from models import Property
from config import STEDEN_FUNDA, FIX_FLIP, SPLITSING

logger = logging.getLogger(__name__)

FUNDA_BASE = "https://www.funda.nl"


def _listing_to_property(listing, stad: str) -> Property:
    """Converteer een pyfunda Listing object naar een Property."""
    # pyfunda retourneert Listing objects met een .data dict
    d = listing.data if hasattr(listing, 'data') else listing

    prijs = d.get("price", 0) or 0
    opp = d.get("living_area", 0) or 0
    adres = d.get("title", "") or f"{d.get('street_name', '')} {d.get('house_number', '')}".strip()
    city = d.get("city", stad.replace("-", " ").title())
    postcode = d.get("postcode", "") or ""
    # URL: detail_url van search API + wordt later overschreven
    # door correcte URL uit detail API (in _check_funda_api)
    detail_url = d.get("detail_url", "")
    global_id = d.get("global_id", "")
    if detail_url:
        url = FUNDA_BASE + detail_url if not detail_url.startswith("http") else detail_url
    elif global_id:
        url = f"{FUNDA_BASE}/detail/{global_id}/"
    else:
        url = ""

    energie = d.get("energy_label", "") or ""
    bouwjaar = d.get("construction_year", 0) or 0
    kamers = d.get("rooms", 0) or 0
    slaapkamers = d.get("bedrooms", 0) or 0
    type_w = d.get("object_type", "") or ""

    # Alleen koop (check price_condition)
    price_cond = d.get("price_condition", "")
    if price_cond and "huur" in str(price_cond).lower():
        return None

    return Property(
        source="funda",
        url=url,
        adres=adres,
        stad=city,
        postcode=str(postcode),
        prijs=int(prijs),
        opp_m2=int(opp),
        prijs_per_m2=round(prijs / opp, 0) if opp > 0 else 0,
        type_woning=str(type_w),
        bouwjaar=int(bouwjaar) if bouwjaar else 0,
        energie_label=str(energie),
        kamers=int(kamers or slaapkamers) if (kamers or slaapkamers) else 0,
        datum_online=date.today(),
    )


def scrape_funda(max_pages: int = 5) -> List[Property]:
    """Scrape Funda via mobile API voor fix & flip en splitsing kansen."""
    results: List[Property] = []
    max_prijs = max(FIX_FLIP["max_aankoopprijs"], SPLITSING["max_aankoopprijs"])
    min_m2 = min(FIX_FLIP["min_opp_m2"], SPLITSING["min_opp_m2"])

    f = Funda()

    for stad in STEDEN_FUNDA:
        for page_num in range(max_pages):
            try:
                logger.info("Funda API: %s pagina %d", stad, page_num + 1)
                listings = f.search_listing(
                    location=stad,
                    offering_type='buy',
                    price_max=max_prijs,
                    area_min=min_m2,
                    sort='newest',
                    page=page_num,
                )

                if not listings:
                    logger.info("Funda API: geen resultaten meer voor %s", stad)
                    break

                for listing in listings:
                    try:
                        prop = _listing_to_property(listing, stad)
                        if prop and prop.prijs >= 25_000 and prop.opp_m2 > 0:
                            results.append(prop)
                    except Exception as e:
                        logger.debug("Funda listing parse fout: %s", e)

                # Kleine pauze om rate limiting te voorkomen
                time.sleep(0.3)

            except RuntimeError as e:
                if "403" in str(e):
                    logger.warning("Funda API rate limit voor %s — even wachten", stad)
                    time.sleep(5)
                    break
                logger.error("Funda API fout %s: %s", stad, e)
                break
            except Exception as e:
                logger.error("Funda API fout %s: %s", stad, e)
                break

    logger.info("Funda: %d panden gevonden", len(results))
    return results
