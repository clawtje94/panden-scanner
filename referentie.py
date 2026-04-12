"""
Referentieprijzen ophalen — zoekt GELIJKWAARDIGE panden in dezelfde stad
op Funda om een realistische verkoopprijs na renovatie te bepalen.

Vergelijkt alleen:
- Zelfde type (appartement vs appartement, huis vs huis)
- Vergelijkbaar oppervlak (+/- 30%)
- Zelfde stad
- Hogere prijsklasse (= al gerenoveerd/goed onderhouden)
"""
import logging
import time
from typing import List, Tuple
from funda import Funda

logger = logging.getLogger(__name__)

_cache: dict = {}
_funda: Funda = None


def _get_funda() -> Funda:
    global _funda
    if _funda is None:
        _funda = Funda()
    return _funda


def _bepaal_funda_type(type_woning: str, opp_m2: int) -> str:
    """Vertaal type_woning naar Funda object_type filter."""
    t = type_woning.lower() if type_woning else ""

    # Appartementen
    if any(kw in t for kw in ["appartement", "apartment", "flat", "portiek", "bovenwoning",
                                "benedenwoning", "maisonnette", "penthouse", "etage"]):
        return "apartment"

    # Huizen
    if any(kw in t for kw in ["huis", "house", "woonhuis", "tussenwoning", "hoekwoning",
                                "twee-onder-een-kap", "vrijstaand", "geschakeld",
                                "herenhuis", "villa", "bungalow", "eengezins"]):
        return "house"

    # Onbekend type: schat op basis van oppervlak
    # < 120m² in Zuid-Holland is meestal appartement
    if opp_m2 < 120:
        return "apartment"
    return "house"


def zoek_vergelijkbare(
    stad: str,
    opp_m2: int,
    strategie: str = "fix_flip",
    type_woning: str = "",
) -> Tuple[float, List[dict]]:
    """
    Zoek vergelijkbare panden in dezelfde stad om de verkoopprijs/m² te bepalen.

    Vergelijkt ALLEEN gelijkwaardige panden:
    - Zelfde type (appartement ↔ appartement, huis ↔ huis)
    - Vergelijkbaar oppervlak
    - Hogere prijsklasse (= gerenoveerd/goed onderhouden)

    Returns:
        (gemiddelde_prijs_per_m2, [lijst van referentie panden])
    """
    funda_type = _bepaal_funda_type(type_woning, opp_m2)
    cache_key = f"{stad}_{opp_m2}_{funda_type}"
    if cache_key in _cache:
        return _cache[cache_key]

    f = _get_funda()

    # Zoek range: +/- 30% van het oppervlak
    min_opp = max(30, int(opp_m2 * 0.7))
    max_opp = int(opp_m2 * 1.3)

    stad_clean = stad.lower().replace(" ", "-")
    type_label = "appartementen" if funda_type == "apartment" else "huizen"

    referenties = []

    try:
        results = f.search_listing(
            location=stad_clean,
            offering_type='buy',
            price_min=200_000,
            price_max=900_000,
            area_min=min_opp,
            area_max=max_opp,
            object_type=[funda_type],
            sort='newest',
            page=0,
        )

        if not results:
            logger.info("Referentie: geen vergelijkbare %s gevonden in %s", type_label, stad)
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
            obj_type = d.get("object_type", "") or ""
            url = d.get("detail_url", "")
            if url and not url.startswith("http"):
                url = "https://www.funda.nl" + url

            referenties.append({
                "adres": titel,
                "prijs": prijs,
                "opp_m2": opp,
                "prijs_per_m2": pm2,
                "energie_label": label,
                "type": obj_type,
                "url": url,
            })

        if not referenties:
            _cache[cache_key] = (0.0, [])
            return (0.0, [])

        # Neem bovenste helft qua prijs/m² (= de beter onderhouden panden)
        referenties.sort(key=lambda x: x["prijs_per_m2"], reverse=True)
        top_helft = referenties[:max(3, len(referenties) // 2)]

        gem_pm2 = sum(r["prijs_per_m2"] for r in top_helft) / len(top_helft)

        # Top 3 als voorbeelden
        top3 = top_helft[:3]

        logger.info(
            "Referentie %s (%s, %d-%dm²): gem %d/m2 op basis van %d panden",
            stad, type_label, min_opp, max_opp, gem_pm2, len(top_helft),
        )

        result = (round(gem_pm2), top3)
        _cache[cache_key] = result
        return result

    except Exception as e:
        logger.warning("Referentie zoeken mislukt voor %s: %s", stad, e)
        _cache[cache_key] = (0.0, [])
        return (0.0, [])
