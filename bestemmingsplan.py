"""
Bestemmingsplan module — Panden Scanner.

Checkt voor een adres:
1. Huidige bestemming (Wonen, Gemengd, Bedrijf, Kantoor)
2. Splitsingbeleid per gemeente
3. Opbouw mogelijkheden (bouwhoogte)

Gebruikt PDOK Locatieserver (gratis, geen API key) voor geocoding.
Ruimtelijke Plannen API v4 staat klaar maar vereist API key.
Zonder key: heuristieken op basis van postcode + gemeente data.
"""

import logging
import re
from typing import Optional

import requests

from wijkdata import check_den_haag_splits, check_rotterdam_splits

logger = logging.getLogger(__name__)

# ── PDOK Locatieserver ───────────────────────────────────────────────────────
PDOK_URL = "https://api.pdok.nl/bzk/locatieserver/search/v3_1/free"

# ── Ruimtelijke Plannen API v4 (vereist API key) ────────────────────────────
RP_API_URL = (
    "https://ruimte.omgevingswet.overheid.nl/"
    "ruimtelijke-plannen/api/opvragen/v4/plannen/_zoek"
)


# ── Gemeente splitsingbeleid ─────────────────────────────────────────────────
# Bron: gemeentelijke huisvestingsverordeningen / beleidsregels
SPLITSINGBELEID = {
    "den haag": {
        "min_opp_m2": 70,        # 2x35 als absolute ondergrens
        "max_units": None,
        "min_per_unit_m2": 35,   # per 1-4-2026 (was 24)
        "vergunning": "splitsingsvergunning",
        "bijzonderheden": (
            "Per 1-4-2026: splitsen alleen in wijken met Leefbaarometer-score "
            ">= goed (7+) EN parkeerdruk < 90%. Min 35 m² GBO per nieuwe unit. "
            "Geluidsisolatie-eisen (Bouwbesluit). Bibob-check mogelijk."
        ),
    },
    "rotterdam": {
        "min_opp_m2": 100,       # 2x50 als ondergrens, hoger in NPRZ
        "max_units": 3,
        "min_per_unit_m2": 50,   # Verordening samenstelling Woningvoorraad 2025
        "vergunning": "woningvormingsvergunning",
        "bijzonderheden": (
            "Per 1-7-2025: standaard 50 m² per unit. In NPRZ-kerngebieden "
            "(delen Feijenoord 3071-3075 en Charlois 3081-3083) geldt 85 m². "
            "Woningvormings- + splitsingsvergunning vereist (ca. EUR 1.350)."
        ),
    },
    "delft": {
        "min_opp_m2": 120,
        "max_units": 2,
        "min_per_unit_m2": 40,
        "vergunning": "omgevingsvergunning",
        "bijzonderheden": (
            "Splitsen beperkt in de binnenstad (beschermd stadsgezicht). "
            "Min 120m2 totaal, max 2 units. Omgevingsvergunning vereist. "
            "Extra streng in de historische kern."
        ),
    },
    "leiden": {
        "min_opp_m2": 100,
        "max_units": 2,
        "min_per_unit_m2": 30,
        "vergunning": "omzettingsvergunning",
        "bijzonderheden": (
            "Omzettingsvergunning vereist (Huisvestingsverordening). "
            "Strenge eisen in Binnenstad-Noord en Zuid. "
            "Geluidsisolatie conform Bouwbesluit vereist."
        ),
    },
    "zoetermeer": {
        "min_opp_m2": 100,
        "max_units": 2,
        "min_per_unit_m2": 28,
        "vergunning": "splitsingsvergunning",
        "bijzonderheden": (
            "Splitsingsvergunning vereist. Relatief soepel beleid. "
            "Min 100m2 totaal. Parkeereis per extra unit."
        ),
    },
    "schiedam": {
        "min_opp_m2": 90,
        "max_units": 2,
        "min_per_unit_m2": 28,
        "vergunning": "splitsingsvergunning",
        "bijzonderheden": (
            "Splitsingsvergunning vereist. Min 90m2 totaal. "
            "In beschermd stadsgezicht extra voorwaarden."
        ),
    },
    "rijswijk": {
        "min_opp_m2": 100,
        "max_units": 2,
        "min_per_unit_m2": 28,
        "vergunning": "splitsingsvergunning",
        "bijzonderheden": (
            "Splitsingsvergunning vereist. Min 100m2 totaal. "
            "Geen specifieke wijkbeperkingen bekend."
        ),
    },
    "dordrecht": {
        "min_opp_m2": 100,
        "max_units": 3,
        "min_per_unit_m2": 24,
        "vergunning": "splitsingsvergunning",
        "bijzonderheden": (
            "Splitsingsvergunning vereist. Min 100m2 totaal, max 3 units. "
            "In eiland van Dordrecht: beschermd stadsgezicht."
        ),
    },
    "westland": {
        "min_opp_m2": 120,
        "max_units": 2,
        "min_per_unit_m2": 30,
        "vergunning": "splitsingsvergunning",
        "bijzonderheden": (
            "Splitsingsvergunning vereist. Woningsplitsing beperkt mogelijk "
            "in woonkernen. Glastuinbouwgebied is uitgesloten."
        ),
    },
    "pijnacker-nootdorp": {
        "min_opp_m2": 100,
        "max_units": 2,
        "min_per_unit_m2": 28,
        "vergunning": "splitsingsvergunning",
        "bijzonderheden": (
            "Splitsingsvergunning vereist. Relatief soepel beleid. "
            "Min 100m2 totaal."
        ),
    },
}

# ── Opbouw beleid per gemeente ───────────────────────────────────────────────
# Typische max bouwhoogtes per woningtype (in meters)
OPBOUWBELEID = {
    "den haag": {
        "tussenwoning": {"max_hoogte_m": 10.0, "max_verdiepingen": 3, "dakopbouw_toegestaan": True},
        "hoekwoning": {"max_hoogte_m": 10.0, "max_verdiepingen": 3, "dakopbouw_toegestaan": True},
        "twee_onder_een_kap": {"max_hoogte_m": 10.0, "max_verdiepingen": 3, "dakopbouw_toegestaan": True},
        "vrijstaand": {"max_hoogte_m": 11.0, "max_verdiepingen": 3, "dakopbouw_toegestaan": True},
        "appartement": {"max_hoogte_m": None, "max_verdiepingen": None, "dakopbouw_toegestaan": False},
        "bijzonderheden": (
            "Dakopbouw vergunningvrij mits <= 4m diep aan achterkant, "
            "kruimelregeling mogelijk. In beschermde stadsgezichten (Statenkwartier, "
            "Archipelbuurt, Zeeheldenkwartier) extra welstandseisen."
        ),
    },
    "rotterdam": {
        "tussenwoning": {"max_hoogte_m": 10.0, "max_verdiepingen": 3, "dakopbouw_toegestaan": True},
        "hoekwoning": {"max_hoogte_m": 10.0, "max_verdiepingen": 3, "dakopbouw_toegestaan": True},
        "twee_onder_een_kap": {"max_hoogte_m": 10.0, "max_verdiepingen": 3, "dakopbouw_toegestaan": True},
        "vrijstaand": {"max_hoogte_m": 12.0, "max_verdiepingen": 3, "dakopbouw_toegestaan": True},
        "appartement": {"max_hoogte_m": None, "max_verdiepingen": None, "dakopbouw_toegestaan": False},
        "bijzonderheden": (
            "Rotterdam is relatief soepel met opbouwen. "
            "Dakopbouw vergunningvrij onder voorwaarden. "
            "Welstandsnota Rotterdam: gebiedsafhankelijk."
        ),
    },
    "delft": {
        "tussenwoning": {"max_hoogte_m": 9.0, "max_verdiepingen": 2, "dakopbouw_toegestaan": True},
        "hoekwoning": {"max_hoogte_m": 9.0, "max_verdiepingen": 2, "dakopbouw_toegestaan": True},
        "twee_onder_een_kap": {"max_hoogte_m": 9.0, "max_verdiepingen": 2, "dakopbouw_toegestaan": True},
        "vrijstaand": {"max_hoogte_m": 10.0, "max_verdiepingen": 3, "dakopbouw_toegestaan": True},
        "appartement": {"max_hoogte_m": None, "max_verdiepingen": None, "dakopbouw_toegestaan": False},
        "bijzonderheden": (
            "Binnenstad Delft is beschermd stadsgezicht — opbouw zeer beperkt. "
            "Buiten binnenstad: vergunningvrij dakopbouw onder voorwaarden. "
            "Welstandscommissie adviseert streng in historische kern."
        ),
    },
    "leiden": {
        "tussenwoning": {"max_hoogte_m": 9.0, "max_verdiepingen": 2, "dakopbouw_toegestaan": True},
        "hoekwoning": {"max_hoogte_m": 9.0, "max_verdiepingen": 2, "dakopbouw_toegestaan": True},
        "twee_onder_een_kap": {"max_hoogte_m": 9.0, "max_verdiepingen": 2, "dakopbouw_toegestaan": True},
        "vrijstaand": {"max_hoogte_m": 10.0, "max_verdiepingen": 3, "dakopbouw_toegestaan": True},
        "appartement": {"max_hoogte_m": None, "max_verdiepingen": None, "dakopbouw_toegestaan": False},
        "bijzonderheden": (
            "Beschermd stadsgezicht in Leiden binnenstad — opbouw beperkt. "
            "Buiten de singels: soepeler. Welstandsnota Leiden is leidend."
        ),
    },
}

# ── Postcode → bestemming heuristiek ─────────────────────────────────────────
# Eerste 2 cijfers postcode → regio, derde + vierde → wijk-indicatie
# Dit is een grove benadering; echte data komt uit Ruimtelijke Plannen API

# Postcodes met veel bedrijvigheid / kantoren (bekende bedrijventerreinen)
BEDRIJF_POSTCODES = {
    # Den Haag
    "2491", "2492", "2493", "2497",  # Ypenburg bedrijven, Binckhorst
    "2516", "2517",  # Beatrixkwartier kantoren
    # Rotterdam
    "3011", "3012", "3013",  # Centrum (gemengd)
    "3089", "3068",  # Haven/Europoort
    # Delft
    "2628", "2629",  # TU Delft campus / technopolis
    # Leiden
    "2316", "2317",  # Bio Science Park
}

GEMENGD_POSTCODES = {
    # Den Haag centrum
    "2511", "2512", "2513", "2514", "2515",
    # Rotterdam centrum
    "3011", "3012", "3013", "3014", "3015",
    # Delft centrum
    "2611", "2612", "2613",
    # Leiden centrum
    "2311", "2312", "2313", "2314", "2315",
}

KANTOOR_POSTCODES = {
    "2516", "2517",  # Den Haag Beatrixkwartier
    "3062", "3063",  # Rotterdam Brainpark
    "2132", "2133",  # Hoofddorp Beukenhorst
}


def _normaliseer_stad(stad: str) -> str:
    """Normaliseer stadsnaam voor lookups."""
    stad = stad.lower().strip()
    # Verwijder 'gemeente' prefix
    stad = re.sub(r"^gemeente\s+", "", stad)
    # Veelvoorkomende variaties
    aliassen = {
        "den haag": "den haag",
        "'s-gravenhage": "den haag",
        "s-gravenhage": "den haag",
        "the hague": "den haag",
        "gemeente pijnacker-nootdorp": "pijnacker-nootdorp",
        "gemeente westland": "westland",
    }
    return aliassen.get(stad, stad)


def pdok_lookup(adres: str) -> Optional[dict]:
    """
    Zoek adres op via PDOK Locatieserver.
    Geen API key nodig.

    Returns dict met:
        - centroide_rd: "x y" (RD coordinaten)
        - woonplaatsnaam: str
        - gemeentenaam: str
        - postcode: str
        - straatnaam: str
        - huisnummer: str
        - centroide_ll: "lat lon" (WGS84)
    Of None bij geen resultaat.
    """
    try:
        resp = requests.get(
            PDOK_URL,
            params={"q": adres, "fq": "type:adres", "rows": 1},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        docs = data.get("response", {}).get("docs", [])
        if not docs:
            logger.warning("PDOK: geen resultaat voor '%s'", adres)
            return None

        doc = docs[0]
        return {
            "centroide_rd": doc.get("centroide_rd"),
            "centroide_ll": doc.get("centroide_ll"),
            "woonplaatsnaam": doc.get("woonplaatsnaam"),
            "gemeentenaam": doc.get("gemeentenaam"),
            "postcode": doc.get("postcode"),
            "straatnaam": doc.get("straatnaam"),
            "huisnummer": str(doc.get("huisnummer", "")),
            "weergavenaam": doc.get("weergavenaam"),
            "score": doc.get("score"),
        }
    except requests.RequestException as e:
        logger.error("PDOK lookup fout: %s", e)
        return None


def _parse_rd_coords(centroide_rd: str) -> Optional[tuple[float, float]]:
    """Parse 'POINT(x y)' string naar (x, y) tuple."""
    match = re.match(r"POINT\(([0-9.]+)\s+([0-9.]+)\)", centroide_rd or "")
    if match:
        return float(match.group(1)), float(match.group(2))
    return None


def _bestemming_via_postcode(postcode: str) -> dict:
    """
    Heuristiek: schat bestemming op basis van postcode.
    Grove benadering — echte data vereist Ruimtelijke Plannen API.
    """
    pc4 = postcode.replace(" ", "")[:4] if postcode else ""

    if pc4 in KANTOOR_POSTCODES:
        return {
            "bestemming": "Kantoor",
            "zekerheid": "laag",
            "toelichting": (
                f"Postcode {pc4} valt in een bekend kantoorgebied. "
                "Check het bestemmingsplan voor de exacte bestemming."
            ),
        }

    if pc4 in BEDRIJF_POSTCODES:
        return {
            "bestemming": "Bedrijf",
            "zekerheid": "laag",
            "toelichting": (
                f"Postcode {pc4} valt in een bekend bedrijventerrein/campusgebied. "
                "Kan ook Gemengd zijn. Check bestemmingsplan."
            ),
        }

    if pc4 in GEMENGD_POSTCODES:
        return {
            "bestemming": "Gemengd",
            "zekerheid": "laag",
            "toelichting": (
                f"Postcode {pc4} valt in een centrumgebied met gemengde bestemming. "
                "Wonen + commercieel waarschijnlijk. Check bestemmingsplan."
            ),
        }

    # Default: waarschijnlijk wonen
    return {
        "bestemming": "Wonen",
        "zekerheid": "laag",
        "toelichting": (
            f"Postcode {pc4} valt vermoedelijk in een woongebied. "
            "Dit is een schatting op basis van postcode. "
            "Check het bestemmingsplan via ruimtelijkeplannen.nl voor zekerheid."
        ),
    }


def check_bestemming(adres: str, stad: Optional[str] = None,
                     postcode: Optional[str] = None) -> dict:
    """
    Check de bestemming van een adres.

    Probeert eerst PDOK lookup. Valt terug op postcode-heuristiek.
    Wanneer Ruimtelijke Plannen API key beschikbaar is, wordt die
    gebruikt voor exacte bestemmingsplandata.

    Args:
        adres: Volledig adres (straat + huisnummer + stad)
        stad: Optioneel, overschrijft stad uit PDOK
        postcode: Optioneel, overschrijft postcode uit PDOK

    Returns:
        dict met:
            - bestemming: str (Wonen / Gemengd / Bedrijf / Kantoor)
            - zekerheid: str (hoog / laag)
            - toelichting: str
            - bron: str (pdok_heuristiek / ruimtelijke_plannen)
            - pdok_data: dict (ruwe PDOK data, indien beschikbaar)
            - gemeente: str
            - postcode: str
    """
    result = {
        "adres": adres,
        "bestemming": "Onbekend",
        "zekerheid": "geen",
        "toelichting": "",
        "bron": "geen",
        "pdok_data": None,
        "gemeente": stad or "",
        "postcode": postcode or "",
    }

    # Stap 1: PDOK lookup
    pdok = pdok_lookup(adres)
    if pdok:
        result["pdok_data"] = pdok
        result["gemeente"] = stad or pdok.get("gemeentenaam", "")
        result["postcode"] = postcode or pdok.get("postcode", "")

    pc = result["postcode"]
    gemeente = result["gemeente"]

    # Stap 2: Probeer Ruimtelijke Plannen API (wanneer key beschikbaar)
    # TODO: implementeer wanneer API key verkregen is
    # rd_coords = _parse_rd_coords(pdok.get("centroide_rd")) if pdok else None
    # if rd_coords and RP_API_KEY:
    #     rp_result = _check_ruimtelijke_plannen(rd_coords)
    #     if rp_result:
    #         return {**result, **rp_result, "bron": "ruimtelijke_plannen"}

    # Stap 3: Heuristiek op basis van postcode
    if pc:
        bestemming_data = _bestemming_via_postcode(pc)
        result.update(bestemming_data)
        result["bron"] = "pdok_heuristiek"

    logger.info(
        "Bestemming %s: %s (%s) — %s",
        adres, result["bestemming"], result["zekerheid"], result["bron"],
    )
    return result


def mag_splitsen(stad: str, opp_m2: float,
                 aantal_units: int = 2,
                 postcode: str = "") -> dict:
    """
    Check of splitsen is toegestaan op basis van gemeente-beleid.

    Voor Den Haag (per 1-4-2026) en Rotterdam (per 1-7-2025) worden wijk-
    specifieke regels toegepast op basis van postcode: Leefbaarometer-score,
    parkeerdruk (DH) en NPRZ-kerngebieden (RDAM).

    Args:
        stad: Gemeentenaam
        opp_m2: Totaal woonoppervlak in m2
        aantal_units: Gewenst aantal units na splitsing
        postcode: Postcode voor wijk-specifieke checks (DH/RDAM)
    """
    stad_norm = _normaliseer_stad(stad)
    beleid = SPLITSINGBELEID.get(stad_norm)

    # Wijk-specifieke check voor Den Haag / Rotterdam
    wijkcheck = None
    if stad_norm == "den haag" and postcode:
        wijkcheck = check_den_haag_splits(postcode, opp_m2, aantal_units, min_per_unit_m2=35)
    elif stad_norm == "rotterdam" and postcode:
        wijkcheck = check_rotterdam_splits(postcode, opp_m2, aantal_units)

    if not beleid:
        return {
            "mag_splitsen": None,  # onbekend
            "uitleg": (
                f"Geen splitsingbeleid bekend voor {stad}. "
                "Check de gemeentelijke huisvestingsverordening."
            ),
            "vergunning": "onbekend",
            "min_opp_m2": None,
            "max_units": None,
            "min_per_unit_m2": None,
            "opp_per_unit": opp_m2 / aantal_units if aantal_units > 0 else 0,
            "bijzonderheden": "",
        }

    opp_per_unit = opp_m2 / aantal_units if aantal_units > 0 else 0
    min_opp = beleid["min_opp_m2"]
    max_units = beleid["max_units"]
    min_per_unit = beleid["min_per_unit_m2"]

    redenen_nee = []

    if opp_m2 < min_opp:
        redenen_nee.append(
            f"Totaal oppervlak ({opp_m2:.0f}m2) is kleiner dan "
            f"minimaal vereist ({min_opp}m2)"
        )

    if max_units and aantal_units > max_units:
        redenen_nee.append(
            f"Aantal units ({aantal_units}) overschrijdt maximum ({max_units})"
        )

    if opp_per_unit < min_per_unit:
        redenen_nee.append(
            f"Oppervlak per unit ({opp_per_unit:.0f}m2) is kleiner dan "
            f"minimaal vereist per unit ({min_per_unit}m2)"
        )

    mag = len(redenen_nee) == 0

    if mag:
        uitleg = (
            f"Splitsen is waarschijnlijk toegestaan in {stad}. "
            f"Oppervlak ({opp_m2:.0f}m2) voldoet aan minimum ({min_opp}m2). "
            f"Per unit: {opp_per_unit:.0f}m2 (min: {min_per_unit}m2). "
            f"Vereist: {beleid['vergunning']}."
        )
    else:
        uitleg = (
            f"Splitsen is waarschijnlijk NIET toegestaan in {stad}. "
            + " ".join(redenen_nee) + ". "
            f"Vereist: {beleid['vergunning']}."
        )

    # Wijk-specifieke check heeft laatste woord voor DH/RDAM
    if wijkcheck is not None:
        if wijkcheck["mag"] is False:
            mag = False
            uitleg = (
                f"Splitsen NIET toegestaan in {stad} op dit adres. "
                + "; ".join(wijkcheck["redenen"])
            )
        elif wijkcheck["mag"] is True and mag:
            uitleg += " Wijk-check OK: " + (
                f"Leefbaarometer score {wijkcheck['wijkscore']}"
                if stad_norm == "den haag" and wijkcheck.get("wijkscore")
                else f"regime {wijkcheck.get('regime', '')}"
            )

    return {
        "mag_splitsen": mag,
        "uitleg": uitleg,
        "vergunning": beleid["vergunning"],
        "min_opp_m2": min_opp,
        "max_units": max_units,
        "min_per_unit_m2": min_per_unit,
        "opp_per_unit": round(opp_per_unit, 1),
        "bijzonderheden": beleid["bijzonderheden"],
        "wijkcheck": wijkcheck,
    }


def mag_opbouwen(stad: str, type_woning: str = "tussenwoning",
                 huidige_hoogte_m: Optional[float] = None) -> dict:
    """
    Check of opbouwen is toegestaan op basis van gemeente-beleid.

    Args:
        stad: Gemeentenaam
        type_woning: Type woning (tussenwoning, hoekwoning,
                     twee_onder_een_kap, vrijstaand, appartement)
        huidige_hoogte_m: Huidige bouwhoogte in meters (optioneel)

    Returns:
        dict met:
            - mag_opbouwen: bool | None
            - uitleg: str
            - max_hoogte_m: float | None
            - max_verdiepingen: int | None
            - dakopbouw_toegestaan: bool
            - ruimte_over_m: float | None (verschil huidige vs max)
            - bijzonderheden: str
    """
    stad_norm = _normaliseer_stad(stad)
    beleid = OPBOUWBELEID.get(stad_norm)

    if not beleid:
        return {
            "mag_opbouwen": None,
            "uitleg": (
                f"Geen opbouwbeleid bekend voor {stad}. "
                "Check het bestemmingsplan op ruimtelijkeplannen.nl."
            ),
            "max_hoogte_m": None,
            "max_verdiepingen": None,
            "dakopbouw_toegestaan": None,
            "ruimte_over_m": None,
            "bijzonderheden": "",
        }

    type_norm = type_woning.lower().strip().replace(" ", "_")
    woning_data = beleid.get(type_norm)

    if not woning_data:
        return {
            "mag_opbouwen": None,
            "uitleg": (
                f"Woningtype '{type_woning}' niet gevonden voor {stad}. "
                f"Bekende types: {', '.join(k for k in beleid if k != 'bijzonderheden')}."
            ),
            "max_hoogte_m": None,
            "max_verdiepingen": None,
            "dakopbouw_toegestaan": None,
            "ruimte_over_m": None,
            "bijzonderheden": beleid.get("bijzonderheden", ""),
        }

    max_hoogte = woning_data["max_hoogte_m"]
    max_verd = woning_data["max_verdiepingen"]
    dakopbouw = woning_data["dakopbouw_toegestaan"]

    ruimte_over = None
    if huidige_hoogte_m is not None and max_hoogte is not None:
        ruimte_over = round(max_hoogte - huidige_hoogte_m, 1)

    if max_hoogte is None:
        # Appartement — niet zelf opbouwen
        mag = False
        uitleg = (
            f"Opbouwen op een {type_woning} in {stad} is niet van toepassing. "
            "Bij appartementen is opbouwen afhankelijk van de VvE en het "
            "bestemmingsplan voor het hele gebouw."
        )
    elif huidige_hoogte_m is not None and ruimte_over is not None:
        if ruimte_over > 0.5:
            mag = True
            uitleg = (
                f"Opbouwen is waarschijnlijk mogelijk in {stad}. "
                f"Max bouwhoogte: {max_hoogte}m, huidige hoogte: {huidige_hoogte_m}m. "
                f"Ruimte over: {ruimte_over}m. "
                f"Dakopbouw: {'ja' if dakopbouw else 'nee'}."
            )
        else:
            mag = False
            uitleg = (
                f"Opbouwen is waarschijnlijk NIET mogelijk in {stad}. "
                f"Max bouwhoogte: {max_hoogte}m, huidige hoogte: {huidige_hoogte_m}m. "
                f"Onvoldoende ruimte over ({ruimte_over}m)."
            )
    else:
        mag = dakopbouw
        uitleg = (
            f"Opbouwen is {'waarschijnlijk mogelijk' if dakopbouw else 'beperkt'} "
            f"voor een {type_woning} in {stad}. "
            f"Max bouwhoogte: {max_hoogte}m, max {max_verd} verdiepingen. "
            f"Dakopbouw: {'ja' if dakopbouw else 'nee'}. "
            "Exacte hoogte onbekend — geef huidige_hoogte_m mee voor preciezere check."
        )

    return {
        "mag_opbouwen": mag,
        "uitleg": uitleg,
        "max_hoogte_m": max_hoogte,
        "max_verdiepingen": max_verd,
        "dakopbouw_toegestaan": dakopbouw,
        "ruimte_over_m": ruimte_over,
        "bijzonderheden": beleid.get("bijzonderheden", ""),
    }


def volledig_rapport(adres: str, opp_m2: float,
                     type_woning: str = "tussenwoning",
                     huidige_hoogte_m: Optional[float] = None,
                     aantal_units: int = 2) -> dict:
    """
    Genereer een volledig bestemmingsplan rapport voor een adres.

    Combineert check_bestemming, mag_splitsen en mag_opbouwen.

    Args:
        adres: Volledig adres
        opp_m2: Woonoppervlak in m2
        type_woning: Type woning
        huidige_hoogte_m: Huidige bouwhoogte (optioneel)
        aantal_units: Gewenst aantal units bij splitsing

    Returns:
        dict met bestemming, splitsing en opbouw informatie
    """
    bestemming = check_bestemming(adres)
    gemeente = bestemming.get("gemeente", "")

    splitsing = mag_splitsen(gemeente, opp_m2, aantal_units)
    opbouw = mag_opbouwen(gemeente, type_woning, huidige_hoogte_m)

    return {
        "adres": adres,
        "gemeente": gemeente,
        "postcode": bestemming.get("postcode", ""),
        "bestemming": bestemming,
        "splitsing": splitsing,
        "opbouw": opbouw,
        "disclaimer": (
            "Dit rapport is gebaseerd op heuristieken en gemeentelijk beleid. "
            "Voor juridische zekerheid: check het bestemmingsplan op "
            "ruimtelijkeplannen.nl en neem contact op met de gemeente."
        ),
    }


# ── CLI test ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json

    logging.basicConfig(level=logging.INFO)

    # Test: Den Haag adres
    print("=" * 70)
    print("TEST: Volledig rapport — Den Haag")
    print("=" * 70)
    rapport = volledig_rapport(
        adres="Laan van Meerdervoort 100, Den Haag",
        opp_m2=140,
        type_woning="tussenwoning",
        huidige_hoogte_m=7.5,
        aantal_units=2,
    )
    print(json.dumps(rapport, indent=2, ensure_ascii=False))

    print()
    print("=" * 70)
    print("TEST: Splitsen — Rotterdam 75m2")
    print("=" * 70)
    result = mag_splitsen("Rotterdam", 75, 2)
    print(json.dumps(result, indent=2, ensure_ascii=False))

    print()
    print("=" * 70)
    print("TEST: Opbouwen — Delft vrijstaand")
    print("=" * 70)
    result = mag_opbouwen("Delft", "vrijstaand", 6.0)
    print(json.dumps(result, indent=2, ensure_ascii=False))
