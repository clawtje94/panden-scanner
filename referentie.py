"""
Referentieprijzen ophalen — zoekt vergelijkbare panden in dezelfde stad
op Funda om een realistische verkoopprijs na renovatie te bepalen.
"""
import logging
import time
from typing import List, Tuple
from funda import Funda

logger = logging.getLogger(__name__)

# Cache om niet steeds dezelfde stad opnieuw op te zoeken
_cache: dict = {}
_funda: Funda = None


def _get_funda() -> Funda:
    global _funda
    if _funda is None:
        _funda = Funda()
    return _funda


def zoek_vergelijkbare(
    stad: str,
    opp_m2: int,
    strategie: str = "fix_flip",
) -> Tuple[float, List[dict]]:
    """
    Zoek vergelijkbare panden in dezelfde stad om de verkoopprijs/m² te bepalen.

    Zoekt naar panden die AL gerenoveerd/goed zijn (hoger geprijsd, goed label)
    als referentie voor wat je pand waard is NA renovatie.

    Returns:
        (gemiddelde_prijs_per_m2, [lijst van referentie panden])
    """
    cache_key = f"{stad}_{opp_m2}_{strategie}"
    if cache_key in _cache:
        return _cache[cache_key]

    f = _get_funda()

    # Zoek range: +/- 30% van het oppervlak, hogere prijsklasse
    min_opp = max(30, int(opp_m2 * 0.7))
    max_opp = int(opp_m2 * 1.3)

    # Stad mapping (funda format)
    stad_clean = stad.lower().replace(" ", "-")

    referenties = []

    try:
        # Zoek panden in hogere prijsklasse (= gerenoveerd/goed)
        results = f.search_listing(
            location=stad_clean,
            offering_type='buy',
            price_min=200_000,
            price_max=800_000,
            area_min=min_opp,
            area_max=max_opp,
            sort='newest',
            page=0,
        )

        if not results:
            logger.info("Referentie: geen vergelijkbare gevonden in %s", stad)
            _cache[cache_key] = (0.0, [])
            return (0.0, [])

        time.sleep(0.3)

        for listing in results:
            d = listing.data if hasattr(listing, 'data') else listing
            prijs = d.get("price", 0) or 0
            opp = d.get("living_area", 0) or 0
            if prijs <= 0 or opp <= 0:
                continue

            pm2 = round(prijs / opp)
            label = d.get("energy_label", "") or "?"
            titel = d.get("title", "") or ""
            url = d.get("detail_url", "")
            if url and not url.startswith("http"):
                url = "https://www.funda.nl" + url

            referenties.append({
                "adres": titel,
                "prijs": prijs,
                "opp_m2": opp,
                "prijs_per_m2": pm2,
                "energie_label": label,
                "url": url,
            })

        if not referenties:
            _cache[cache_key] = (0.0, [])
            return (0.0, [])

        # Filter: neem alleen de bovenste helft qua prijs/m² (= de gerenoveerde)
        referenties.sort(key=lambda x: x["prijs_per_m2"], reverse=True)
        top_helft = referenties[:max(3, len(referenties) // 2)]

        gem_pm2 = sum(r["prijs_per_m2"] for r in top_helft) / len(top_helft)

        # Neem top 3 als voorbeelden voor in het bericht
        top3 = top_helft[:3]

        logger.info(
            "Referentie %s: gem %d/m2 op basis van %d panden (top %d)",
            stad, gem_pm2, len(referenties), len(top_helft),
        )

        result = (round(gem_pm2), top3)
        _cache[cache_key] = result
        return result

    except Exception as e:
        logger.warning("Referentie zoeken mislukt voor %s: %s", stad, e)
        _cache[cache_key] = (0.0, [])
        return (0.0, [])
