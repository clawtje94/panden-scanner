"""
Wijkdata voor splitsings-eligibility checks.

Den Haag (per 1-4-2026):
  - Splitsen alleen toegestaan in wijken met Leefbaarometer-score >= "goed" (7+)
    op basis van 2-jaars gemiddelde.
  - Parkeerdruk in de wijk moet < 90% zijn.
  - Min 35 m² GBO per nieuwe unit.
  Bron: Huisvestingsverordening Den Haag + Leefbaarometer 2024.

Rotterdam (per 1-7-2025, Verordening samenstelling Woningvoorraad 2025):
  - Standaard min 50 m² per unit.
  - In NPRZ-kerngebieden (delen van Feijenoord en Charlois) geldt 85 m².

Fallback-lookup op basis van PC4 (vier cijfers van de postcode). Wijkgrenzen
lopen niet 1-op-1 met PC4 dus dit is een benadering; bij twijfel altijd de
actuele gemeentelijke check doen.
"""
from __future__ import annotations

import re

_PC4_RE = re.compile(r"([1-9]\d{3})")


# ── Den Haag: PC4 → Leefbaarometer 2024 score ────────────────────────────────
# Score 7 = goed, 8 = zeer goed, 9 = uitstekend. Alleen 7+ telt voor splitsen.
DH_LEEFBAAROMETER = {
    # uitstekend (9)
    2582: 9, 2585: 9, 2586: 9, 2596: 9, 2597: 9,
    2517: 9, 2518: 9, 2594: 9, 2496: 9,
    2563: 9, 2564: 9, 2565: 9, 2566: 9,
    # zeer goed (8)
    2511: 8, 2512: 8, 2513: 8, 2516: 6,  # Binckhorst iets lager
    2562: 8, 2583: 9, 2584: 9,
    2593: 8, 2595: 8,
    2553: 8, 2554: 8,
    # goed (7)
    2491: 7, 2492: 7, 2493: 7, 2495: 7, 2497: 7,
    2548: 7, 2552: 7, 2555: 7,
    # onder de drempel (< 7) — expliciet zodat we onderscheid maken met onbekend
    2514: 6, 2515: 6,                      # Stationsbuurt
    2521: 4, 2522: 4, 2524: 4,             # Laakkwartier / Spoorwijk
    2525: 4, 2526: 4, 2527: 4,             # Schildersbuurt
    2531: 4, 2532: 4, 2533: 5,             # Moerwijk / Zuiderpark
    2543: 4, 2544: 4, 2545: 6,             # Morgenstond / Bouwlust / Leyenburg
    2551: 6,                                # Loosduinen
    2572: 4,                                # Transvaal
    2573: 4, 2574: 4,                       # Rustenburg / Oostbroek
    2592: 6, 2598: 6,                       # Mariahoeve / Marlot
}

# Den Haag PC4s met structureel hoge parkeerdruk (>= 90%). Uit parkeerbeleid
# 2021-2030 + Den Haag in Cijfers. Geen harde APIdata hier, dit is een
# handmatige fallback; bij voorkeur aanvullen met live cijfers als we die
# kunnen ophalen.
DH_PARKEERDRUK_HOOG = {
    2511, 2512, 2513, 2514, 2515, 2517, 2518,       # Centrum + Willemspark/Zeeheldenkw.
    2582, 2583, 2584, 2585, 2586,                   # Scheveningen + Statenkwartier/Archipel
    2593,                                            # Bezuidenhout-West
    2562, 2563,                                      # Regentesse/Valkenbos
}


# ── Rotterdam: NPRZ-kerngebieden met 85 m² minimum ───────────────────────────
RDAM_NPRZ_85M2 = {
    3071, 3072, 3073, 3074, 3075,     # Feijenoord (Afrikaanderwijk, Bloemhof, Hillesluis, Vreewijk-deel)
    3081, 3082, 3083,                 # Charlois (Tarwewijk, Oud-Charlois, Carnisse)
}


def _pc4(postcode: str) -> int | None:
    if not postcode:
        return None
    m = _PC4_RE.search(postcode.upper().replace(" ", ""))
    return int(m.group(1)) if m else None


def leefbaarometer_score(postcode: str) -> int | None:
    """Retourneer Leefbaarometer-score (1-9) voor een Den Haag postcode, of None
    als niet bekend. Alleen Den Haag is hier gevuld."""
    pc4 = _pc4(postcode)
    return DH_LEEFBAAROMETER.get(pc4) if pc4 else None


def parkeerdruk_hoog_dh(postcode: str) -> bool:
    """True als PC4 structureel hoge parkeerdruk (>= 90%) heeft — Den Haag."""
    pc4 = _pc4(postcode)
    return pc4 in DH_PARKEERDRUK_HOOG if pc4 else False


def rotterdam_nprz_85m2(postcode: str) -> bool:
    """True als PC4 in NPRZ-kerngebied valt (Rotterdam 85 m² regime)."""
    pc4 = _pc4(postcode)
    return pc4 in RDAM_NPRZ_85M2 if pc4 else False


def check_den_haag_splits(postcode: str, opp_m2: float, aantal_units: int = 2,
                           min_per_unit_m2: int = 35) -> dict:
    """Evalueer nieuwe Den Haag splitseisen (per 1-4-2026).

    Retourneert dict: {mag, redenen, wijkscore, parkeerdruk_hoog, opp_per_unit}.
    `mag` is True als alle harde eisen zijn gehaald; None als wijk onbekend is
    (bv onbekende postcode) zodat we niet ten onrechte doorlaten of blokkeren.
    """
    score = leefbaarometer_score(postcode)
    parkeer_hoog = parkeerdruk_hoog_dh(postcode)
    opp_per_unit = opp_m2 / aantal_units if aantal_units > 0 else 0

    redenen = []
    if score is None:
        redenen.append("wijk leefbaarometer score onbekend")
    elif score < 7:
        redenen.append(
            f"wijk leefbaarometer score {score} (< 7 = niet splitsbaar)"
        )
    if parkeer_hoog:
        redenen.append("parkeerdruk >= 90% in deze wijk (fallback-data)")
    if opp_per_unit < min_per_unit_m2:
        redenen.append(
            f"GBO per unit {opp_per_unit:.0f} m² < vereist {min_per_unit_m2} m²"
        )

    if score is None:
        mag = None
    else:
        mag = len(redenen) == 0 or redenen == ["parkeerdruk >= 90% in deze wijk (fallback-data)"]
        # Parkeerdruk-fallback als waarschuwing zonder hard nee (data is indicatief)
        if parkeer_hoog and score >= 7 and opp_per_unit >= min_per_unit_m2:
            mag = True  # maar met waarschuwing in redenen

    return {
        "mag": mag,
        "wijkscore": score,
        "parkeerdruk_hoog": parkeer_hoog,
        "opp_per_unit": round(opp_per_unit, 1),
        "redenen": redenen,
        "regime": "den_haag_2026",
    }


def check_rotterdam_splits(postcode: str, opp_m2: float, aantal_units: int = 2) -> dict:
    """Evalueer Rotterdam splitseisen (Verordening 2025).

    Standaard min 50 m² per unit; 85 m² in NPRZ-kerngebied.
    """
    is_nprz = rotterdam_nprz_85m2(postcode)
    min_per_unit = 85 if is_nprz else 50
    opp_per_unit = opp_m2 / aantal_units if aantal_units > 0 else 0

    redenen = []
    if opp_per_unit < min_per_unit:
        redenen.append(
            f"GBO per unit {opp_per_unit:.0f} m² < vereist {min_per_unit} m² "
            f"({'NPRZ-kerngebied' if is_nprz else 'standaard regime'})"
        )

    return {
        "mag": len(redenen) == 0,
        "min_per_unit_m2": min_per_unit,
        "is_nprz": is_nprz,
        "opp_per_unit": round(opp_per_unit, 1),
        "redenen": redenen,
        "regime": "rotterdam_2025",
    }
