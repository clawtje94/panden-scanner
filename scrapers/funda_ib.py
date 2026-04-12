"""
Funda In Business scraper — commercieel vastgoed via pyfunda mobile API.
Zoekt kantoren, winkels en bedrijfsruimtes voor transformatie.
"""
import logging
import time
from typing import List
from datetime import date

from funda import Funda
from models import Property
from config import STEDEN_FUNDA, TRANSFORMATIE

logger = logging.getLogger(__name__)

FUNDA_BASE = "https://www.funda.nl"


def _listing_to_property(listing, stad: str) -> Property:
    """Converteer een pyfunda Listing object naar Property."""
    d = listing.data if hasattr(listing, 'data') else listing

    prijs = d.get("price", 0) or 0
    opp = d.get("living_area", 0) or d.get("plot_area", 0) or 0
    adres = d.get("title", "") or ""
    city = d.get("city", stad.replace("-", " ").title())
    url = d.get("detail_url", "")
    if url and not url.startswith("http"):
        url = FUNDA_BASE + url
    type_w = d.get("object_type", "") or ""

    # Check of het koop is
    price_cond = d.get("price_condition", "")
    if price_cond and "huur" in str(price_cond).lower():
        return None

    return Property(
        source="funda_ib",
        url=url,
        adres=adres,
        stad=city,
        prijs=int(prijs),
        opp_m2=int(opp),
        prijs_per_m2=round(prijs / opp, 0) if opp > 0 else 0,
        type_woning=str(type_w),
        is_commercieel=True,
        datum_online=date.today(),
    )


def scrape_funda_ib(max_pages: int = 3) -> List[Property]:
    """Scrape Funda zakelijk via mobile API voor transformatie kansen."""
    results: List[Property] = []
    max_prijs = TRANSFORMATIE["max_aankoopprijs"]
    min_m2 = TRANSFORMATIE["min_opp_m2"]

    f = Funda()

    for stad in STEDEN_FUNDA[:6]:
        for page_num in range(max_pages):
            try:
                logger.info("Funda IB API: %s pagina %d", stad, page_num + 1)
                listings = f.search_listing(
                    location=stad,
                    offering_type='buy',
                    price_max=max_prijs,
                    area_min=min_m2,
                    sort='newest',
                    page=page_num,
                )

                if not listings:
                    break

                for listing in listings:
                    try:
                        d = listing.data if hasattr(listing, 'data') else listing
                        obj_type = str(d.get("object_type", "")).lower()

                        # Alleen commercieel vastgoed
                        if obj_type not in ("office", "retail", "industrial",
                                            "kantoor", "winkel", "bedrijfsruimte"):
                            continue

                        prop = _listing_to_property(listing, stad)
                        if not prop or prop.prijs < 25_000:
                            continue
                        if prop.prijs > max_prijs:
                            continue
                        if prop.opp_m2 < min_m2:
                            continue

                        results.append(prop)
                    except Exception as e:
                        logger.debug("FiB listing parse fout: %s", e)

                time.sleep(0.3)

            except RuntimeError as e:
                if "403" in str(e):
                    logger.warning("FiB rate limit voor %s — skip", stad)
                    time.sleep(5)
                    break
                logger.error("FiB fout %s: %s", stad, e)
                break
            except Exception as e:
                logger.error("FiB fout %s: %s", stad, e)
                break

    logger.info("FiB: %d panden gevonden", len(results))
    return results
