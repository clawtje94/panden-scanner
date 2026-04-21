"""
Dynamische looptijd berekening per project.

Looptijd = vergunning + verbouw + verkooptijd

Afhankelijk van:
- Type renovatie (cosmetisch/medium/zwaar/casco)
- Stad (gemeente vergunningtraject)
- Oppervlak
"""
import logging

logger = logging.getLogger(__name__)

# Gemiddeld vergunningtraject per gemeente (maanden)
VERGUNNING_MAANDEN = {
    "den haag": 3,
    "rotterdam": 3.5,
    "delft": 2.5,
    "leiden": 3,
    "zoetermeer": 2,
    "schiedam": 2,
    "rijswijk": 2,
    "dordrecht": 2.5,
}

# Gemiddelde verkooptijd (maanden) — bron: NVM Q1 2026
VERKOOPTIJD_MAANDEN = 2  # ~60 dagen gemiddeld


def bereken_looptijd(
    renovatie_per_m2: int,
    opp_m2: int,
    stad: str = "",
    type_woning: str = "",
    is_opknapper: bool = False,
    avg_days_online_wijk: float = None,
) -> dict:
    """
    Bereken realistische projectlooptijd in maanden.

    Returns:
        {
            'totaal_maanden': int,
            'vergunning_maanden': float,
            'verbouw_maanden': float,
            'verkoop_maanden': float,
            'type': str,  # cosmetisch/medium/zwaar/casco
        }
    """
    # Bepaal renovatie-type op basis van kosten/m2
    if renovatie_per_m2 >= 1400:
        reno_type = "casco"
        verbouw_base = 10  # 10-14 maanden
        verbouw_factor = 0.02  # extra per m2 boven 80
    elif renovatie_per_m2 >= 900:
        reno_type = "zwaar"
        verbouw_base = 6
        verbouw_factor = 0.015
    elif renovatie_per_m2 >= 600:
        reno_type = "medium"
        verbouw_base = 4
        verbouw_factor = 0.01
    else:
        reno_type = "cosmetisch"
        verbouw_base = 2
        verbouw_factor = 0.005

    # Verbouwtijd schalen met oppervlak
    extra_m2 = max(0, opp_m2 - 80) * verbouw_factor
    verbouw_mnd = round(verbouw_base + extra_m2, 1)

    # Vergunning (bij cosmetisch vaak niet nodig)
    stad_clean = stad.lower().replace("'s-gravenhage", "den haag").strip()
    if reno_type == "cosmetisch":
        vergunning_mnd = 0  # geen vergunning nodig
    elif reno_type == "medium":
        vergunning_mnd = 1  # vaak omgevingsvergunning light
    else:
        vergunning_mnd = VERGUNNING_MAANDEN.get(stad_clean, 3)

    # Verkooptijd — gebruik echte wijk-data als beschikbaar
    # avg_days_online_wijk komt uit referentie-engine (gemiddelde dagen dat
    # vergelijkbare panden op Funda staan in deze wijk). Zelfs na listing
    # duurt verkoop + transactie nog ~6 weken.
    if avg_days_online_wijk and avg_days_online_wijk > 0:
        verkoop_mnd = round(avg_days_online_wijk / 30 + 1.5, 1)
        verkoop_mnd = max(1.5, min(verkoop_mnd, 12))  # clamp 1.5-12 mnd
        verkoop_bron = f"wijk-data ({int(avg_days_online_wijk)}d online)"
    else:
        verkoop_mnd = VERKOOPTIJD_MAANDEN
        verkoop_bron = "landelijk gemiddelde"

    totaal = round(vergunning_mnd + verbouw_mnd + verkoop_mnd)

    logger.info(
        "Looptijd %s %dm2 %s: %d mnd (verg %s + bouw %s + verkoop %s)",
        reno_type, opp_m2, stad, totaal, vergunning_mnd, verbouw_mnd, verkoop_mnd,
    )

    return {
        "totaal_maanden": totaal,
        "vergunning_maanden": vergunning_mnd,
        "verbouw_maanden": verbouw_mnd,
        "verkoop_maanden": verkoop_mnd,
        "verkoop_bron": verkoop_bron,
        "type": reno_type,
    }
