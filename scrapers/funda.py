"""
Funda.nl scraper — via pyfunda (mobile app API, geen CAPTCHA).
Zoekt naar woningen voor fix & flip en splitsing.
"""
import logging
from typing import List
from datetime import date

from funda import Funda
from models import Property
from config import STEDEN_FUNDA, FIX_FLIP, SPLITSING

logger = logging.getLogger(__name__)

FUNDA_BASE = "https://www.funda.nl"

# Mapping van config steden naar funda location format
STAD_MAPPING = {
    "den-haag": "den-haag",
    "rotterdam": "rotterdam",
    "delft": "delft",
    "leiden": "leiden",
    "zoetermeer": "zoetermeer",
    "schiedam": "schiedam",
    "rijswijk": "rijswijk",
    "dordrecht": "dordrecht",
    "westland": "westland",
    "pijnacker-nootdorp": "pijnacker-nootdorp",
}


def _listing_to_property(listing: dict, stad: str) -> Property:
    """Converteer een pyfunda listing dict naar een Property."""
    prijs = listing.get("price") or listing.get("asking_price") or 0
    if isinstance(prijs, str):
        import re
        prijs_clean = re.sub(r'[^\d]', '', prijs)
        prijs = int(prijs_clean) if prijs_clean else 0

    opp = listing.get("living_area") or listing.get("area") or 0
    if isinstance(opp, str):
        import re
        opp_match = re.search(r'(\d+)', opp)
        opp = int(opp_match.group(1)) if opp_match else 0

    adres = listing.get("address") or listing.get("title") or ""
    url = listing.get("url") or ""
    if not url and listing.get("id"):
        url = f"{FUNDA_BASE}/detail/koop/{stad}/{listing['id']}/"

    postcode = listing.get("postal_code") or listing.get("zip_code") or ""
    energie = listing.get("energy_label") or ""
    bouwjaar = listing.get("construction_year") or listing.get("year_built") or 0
    kamers = listing.get("rooms") or listing.get("number_of_rooms") or 0
    type_w = listing.get("property_type") or listing.get("object_type") or ""

    if isinstance(bouwjaar, str):
        import re
        bj_match = re.search(r'(\d{4})', str(bouwjaar))
        bouwjaar = int(bj_match.group(1)) if bj_match else 0
    if isinstance(kamers, str):
        import re
        k_match = re.search(r'(\d+)', str(kamers))
        kamers = int(k_match.group(1)) if k_match else 0

    return Property(
        source="funda",
        url=url,
        adres=adres,
        stad=stad.replace("-", " ").title(),
        postcode=str(postcode),
        prijs=int(prijs),
        opp_m2=int(opp),
        prijs_per_m2=round(prijs / opp, 0) if opp > 0 else 0,
        type_woning=str(type_w),
        bouwjaar=int(bouwjaar) if bouwjaar else 0,
        energie_label=str(energie),
        kamers=int(kamers) if kamers else 0,
        datum_online=date.today(),
    )


def scrape_funda(max_pages: int = 3) -> List[Property]:
    """Scrape Funda via mobile API voor fix & flip en splitsing kansen."""
    results: List[Property] = []
    max_prijs = max(FIX_FLIP["max_aankoopprijs"], SPLITSING["max_aankoopprijs"])
    min_m2 = min(FIX_FLIP["min_opp_m2"], SPLITSING["min_opp_m2"])

    f = Funda()

    for stad in STEDEN_FUNDA:
        location = STAD_MAPPING.get(stad, stad)
        for page_num in range(max_pages):
            try:
                logger.info("Funda API: zoeken in %s pagina %d", stad, page_num + 1)
                listings = f.search_listing(
                    location=location,
                    offering_type='buy',
                    price_max=max_prijs,
                    area_min=min_m2,
                    sort='newest',
                    page=page_num,
                )

                if not listings:
                    logger.info("Funda API: geen resultaten meer voor %s", stad)
                    break

                # listings kan een list of dict zijn
                if isinstance(listings, dict):
                    items = listings.get("objects", listings.get("results", []))
                elif isinstance(listings, list):
                    items = listings
                else:
                    logger.warning("Funda API: onverwacht type %s", type(listings))
                    break

                if not items:
                    break

                for listing in items:
                    try:
                        if isinstance(listing, dict):
                            prop = _listing_to_property(listing, stad)
                        else:
                            # Als het een object is met attributen
                            listing_dict = listing.__dict__ if hasattr(listing, '__dict__') else {}
                            prop = _listing_to_property(listing_dict, stad)

                        if prop.prijs >= 25_000 and prop.opp_m2 > 0:
                            results.append(prop)
                    except Exception as e:
                        logger.debug("Funda listing parse fout: %s", e)

            except Exception as e:
                logger.error("Funda API fout %s pagina %d: %s", stad, page_num + 1, e)
                break  # stop met deze stad bij API fouten

    logger.info("Funda: %d panden gevonden", len(results))
    return results
