"""
Referentieprijzen ophalen — zoekt in DEZELFDE WIJK (postcode) naar
vergelijkbare panden voor een realistische verkoopprijs na renovatie.

Zoekt op:
1. Postcode (4 cijfers) = zelfde wijk
2. Zelfde type (appartement vs huis)
3. Vergelijkbaar oppervlak (+/- 30%)
4. Neemt de bovenste helft qua prijs/m² (= gerenoveerde panden)
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
    t = type_woning.lower() if type_woning else ""
    if any(kw in t for kw in ["appartement", "apartment", "flat", "portiek", "bovenwoning",
                                "benedenwoning", "maisonnette", "penthouse", "etage"]):
        return "apartment"
    if any(kw in t for kw in ["huis", "house", "woonhuis", "tussenwoning", "hoekwoning",
                                "twee-onder-een-kap", "vrijstaand", "geschakeld",
                                "herenhuis", "villa", "bungalow", "eengezins"]):
        return "house"
    if opp_m2 < 120:
        return "apartment"
    return "house"


def zoek_vergelijkbare(
    stad: str,
    opp_m2: int,
    strategie: str = "fix_flip",
    type_woning: str = "",
    postcode: str = "",
) -> Tuple[float, List[dict]]:
    """
    Zoek vergelijkbare panden in DEZELFDE WIJK voor realistische verkoopprijs.

    Zoekstrategie:
    1. Eerst op postcode (4 cijfers) = zelfde wijk
    2. Fallback op stad als postcode geen resultaten geeft
    3. Alleen zelfde type (app vs app, huis vs huis)
    4. Neemt bovenste helft qua prijs/m² als referentie

    Returns:
        (gemiddelde_prijs_per_m2, [referentie panden met details])
    """
    funda_type = _bepaal_funda_type(type_woning, opp_m2)
    pc4 = postcode[:4].strip() if postcode else ""
    cache_key = f"{pc4 or stad}_{opp_m2}_{funda_type}"
    if cache_key in _cache:
        return _cache[cache_key]

    f = _get_funda()
    min_opp = max(30, int(opp_m2 * 0.7))
    max_opp = int(opp_m2 * 1.3)
    type_label = "appartementen" if funda_type == "apartment" else "huizen"

    referenties = []

    # Stap 1: Zoek op postcode (= zelfde wijk)
    zoek_locaties = []
    if pc4:
        zoek_locaties.append(("postcode " + pc4, pc4))
    stad_clean = stad.lower().replace(" ", "-")
    if stad_clean:
        zoek_locaties.append(("stad " + stad, stad_clean))

    for label_loc, locatie in zoek_locaties:
        if referenties:
            break  # al gevonden via postcode
        try:
            results = f.search_listing(
                location=locatie,
                offering_type='buy',
                price_min=150_000,
                price_max=900_000,
                area_min=min_opp,
                area_max=max_opp,
                object_type=[funda_type],
                sort='newest',
                page=0,
            )
            if not results:
                continue

            time.sleep(0.3)

            for listing in results:
                d = listing.data if hasattr(listing, 'data') else listing
                prijs = d.get("price", 0) or 0
                opp = d.get("living_area", 0) or 0
                if prijs <= 0 or opp <= 0:
                    continue

                pm2 = round(prijs / opp)
                e_label = d.get("energy_label", "") or "?"
                titel = d.get("title", "") or ""
                wijk = d.get("neighbourhood", "") or ""
                obj_type = d.get("object_type", "") or ""
                detail_url = d.get("detail_url", "")
                url = "https://www.funda.nl" + detail_url if detail_url and not detail_url.startswith("http") else detail_url

                referenties.append({
                    "adres": titel,
                    "prijs": prijs,
                    "opp_m2": opp,
                    "prijs_per_m2": pm2,
                    "energie_label": e_label,
                    "type": obj_type,
                    "wijk": wijk,
                    "url": url,
                })

            if referenties:
                logger.info(
                    "Referentie %s (%s, %d-%dm²): %d panden gevonden",
                    label_loc, type_label, min_opp, max_opp, len(referenties),
                )

        except Exception as e:
            logger.debug("Referentie zoeken mislukt voor %s: %s", label_loc, e)

    if not referenties:
        logger.info("Referentie: geen vergelijkbare %s gevonden voor %s", type_label, pc4 or stad)
        _cache[cache_key] = (0.0, [])
        return (0.0, [])

    # Sorteer op prijs/m² en neem bovenste helft (= beter onderhouden panden)
    referenties.sort(key=lambda x: x["prijs_per_m2"], reverse=True)
    top_helft = referenties[:max(3, len(referenties) // 2)]

    gem_pm2 = sum(r["prijs_per_m2"] for r in top_helft) / len(top_helft)

    # Top 5 als voorbeelden (met wijk erbij)
    top5 = top_helft[:5]

    logger.info(
        "Referentie %s (%s): gem %d/m2 (range %d-%d) op basis van %d panden",
        pc4 or stad, type_label, gem_pm2,
        min(r["prijs_per_m2"] for r in top_helft),
        max(r["prijs_per_m2"] for r in top_helft),
        len(top_helft),
    )

    result = (round(gem_pm2), top5)
    _cache[cache_key] = result
    return result
