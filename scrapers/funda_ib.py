"""
Funda In Business scraper — commercieel vastgoed via pyfunda mobile API.
Zoekt kantoren, winkels en bedrijfsruimtes voor transformatie.
"""
import logging
import re
from typing import List
from datetime import date

from funda import Funda
from models import Property
from config import STEDEN_FUNDA, TRANSFORMATIE

logger = logging.getLogger(__name__)

FUNDA_BASE = "https://www.funda.nl"


def _listing_to_property(listing: dict, stad: str) -> Property:
    """Converteer een pyfunda listing naar Property."""
    prijs = listing.get("price") or listing.get("asking_price") or 0
    if isinstance(prijs, str):
        prijs_clean = re.sub(r'[^\d]', '', prijs)
        prijs = int(prijs_clean) if prijs_clean else 0

    opp = listing.get("living_area") or listing.get("area") or listing.get("floor_area") or 0
    if isinstance(opp, str):
        opp_match = re.search(r'(\d+)', str(opp))
        opp = int(opp_match.group(1)) if opp_match else 0

    adres = listing.get("address") or listing.get("title") or ""
    url = listing.get("url") or ""
    type_w = listing.get("property_type") or listing.get("object_type") or ""

    return Property(
        source="funda_ib",
        url=url,
        adres=adres,
        stad=stad.replace("-", " ").title(),
        prijs=int(prijs),
        opp_m2=int(opp),
        prijs_per_m2=round(prijs / opp, 0) if opp > 0 else 0,
        type_woning=str(type_w),
        is_commercieel=True,
        datum_online=date.today(),
    )


def scrape_funda_ib(max_pages: int = 2) -> List[Property]:
    """Scrape Funda zakelijk via mobile API voor transformatie kansen."""
    results: List[Property] = []
    max_prijs = TRANSFORMATIE["max_aankoopprijs"]
    min_m2 = TRANSFORMATIE["min_opp_m2"]

    f = Funda()

    for stad in STEDEN_FUNDA[:6]:
        for page_num in range(max_pages):
            try:
                logger.info("Funda IB API: zoeken in %s pagina %d", stad, page_num + 1)

                # Probeer zakelijk zoeken
                listings = f.search_listing(
                    location=stad,
                    offering_type='buy',
                    price_max=max_prijs,
                    area_min=min_m2,
                    object_type=['office', 'retail', 'industrial'],
                    sort='newest',
                    page=page_num,
                )

                if not listings:
                    break

                items = listings if isinstance(listings, list) else listings.get("objects", listings.get("results", []))
                if not items:
                    break

                for listing in items:
                    try:
                        if isinstance(listing, dict):
                            ld = listing
                        else:
                            ld = listing.__dict__ if hasattr(listing, '__dict__') else {}

                        prop = _listing_to_property(ld, stad)

                        # Filter: alleen koopprijzen, niet te duur
                        if prop.prijs < 25_000:
                            continue
                        if prop.prijs > max_prijs:
                            continue
                        if prop.opp_m2 < min_m2:
                            continue
                        if prop.opp_m2 > 0 and (prop.prijs / prop.opp_m2) > TRANSFORMATIE["max_prijs_per_m2"]:
                            continue

                        results.append(prop)
                    except Exception as e:
                        logger.debug("FiB listing parse fout: %s", e)

            except Exception as e:
                logger.error("Funda IB API fout %s: %s", stad, e)
                break

    logger.info("FiB: %d panden gevonden", len(results))
    return results
