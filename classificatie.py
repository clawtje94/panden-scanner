"""
Centrale pand-classificatie.

Beslist voor elk pand één keer: is dit een woon-pand, een transformatie-kandidaat,
verhuurd (= geen ontwikkeling), of moet het sowieso uit de pipeline (hallen,
kavels, boten, garageboxen)?

Deze module is de waakhond voor data-kwaliteit. Een developer moet 50 goede
leads per week beoordelen, niet 500 ruwe — dus bij twijfel eerder skippen dan
doorlaten.

Categorieën (veld `category`):
  - "wonen"          : reguliere woning, in fix&flip/splits pipeline
  - "transformatie"  : kantoor/winkel/horeca met realistisch woonpotentieel
  - "verhuurd_wonen" : woning, maar verhuurd (= belegging, géén ontwikkeling)
  - "skip"           : hal/loods/garagebox/boot/kavel/grond etc
"""
from __future__ import annotations

import re
from typing import Optional

# ── Whitelist woon-types ─────────────────────────────────────────────────────
# Herkend in Funda object_type, Pararius titels, makelaar type-velden,
# veiling-woningtype, beleggingspanden type. Altijd lowercase matchen.
WOON_TYPES = {
    # Funda / makelaars
    "apartment", "house", "residential",
    # Nederlands
    "woning", "appartement", "appartementen",
    "eengezinswoning", "tussenwoning", "hoekwoning", "herenhuis",
    "2-onder-1-kap", "twee onder een kap", "twee-onder-een-kap", "vrijstaand",
    "vrijstaande woning", "villa", "bungalow",
    "portiekwoning", "portiekflat", "galerijwoning", "galerijflat", "flat",
    "bovenwoning", "benedenwoning", "maisonnette", "split-level", "split level",
    "dubbel bovenhuis", "stadswoning", "drive-in woning", "woonboerderij",
    "woonhuis", "penthouse", "studio", "bel-etage", "souterrain",
    "woning / appartement", "appartement (veiling)", "woonhuis (veiling)",
    "portiekwoning (veiling)", "tussenwoning (veiling)", "hoekwoning (veiling)",
    "galerijwoning (veiling)", "bovenwoning (veiling)", "benedenwoning (veiling)",
    "vrijstaand (veiling)", "herenhuis (veiling)", "2-onder-1-kap (veiling)",
    "maisonnette (veiling)",
}

# ── Commercieel met realistisch woonpotentieel (transformatie) ───────────────
TRANSFORMATIE_TYPES = {
    "kantoor", "kantoorpand", "kantoorruimte", "kantoor (veiling)",
    "kantoorpand (veiling)",
    "winkel", "winkelpand", "winkelruimte", "winkel (veiling)",
    "winkel / woonhuis", "winkel met bovenwoning",
    "winkel met bovenwoning (executieveiling)", "winkel met bovenwoning (veiling)",
    "horeca", "horecapand", "horeca (veiling)",
    "praktijkruimte", "dienstverlening", "maatschappelijk",
    "gemengd", "gemengde bestemming",
}

# ── Hard skip — nooit in woning-pipeline ─────────────────────────────────────
SKIP_TYPES = {
    "bedrijfspand", "bedrijfsruimte", "bedrijfshal", "hal", "loods",
    "industrieel", "industriepand", "industrie",
    "bedrijfspand (veiling)", "bedrijfspand / woonhuis (veiling)",
    "productiehal", "werkplaats", "opslag", "opslagruimte",
    "garage", "garagebox", "parkeerplaats", "garage (veiling)",
    "motorschip", "motorschip (veiling)", "woonboot", "woonschip", "boot",
    "grond", "kavel", "bouwkavel", "grond / kavel (veiling)", "bouwgrond",
    "agrarisch", "tuin", "weiland", "recreatie", "recreatiewoning",
    "stacaravan", "chalet", "caravan", "camping",
    "beleggingsobject",               # typisch verhuurd commercieel/mixed
    "beleggingsobject (veiling)",
    "beleggingsobject (executieveiling)",
    "beleggingsobject (beslagveiling)",
    "beleggingsobject (beslaglegging)",
    "combinatieveiling",              # meerdere objecten in één lot
    "bijzonder object", "bijzonder object (veiling)",
}

# ── Tekst-keywords die duiden op VERHUURD pand ───────────────────────────────
# Als match → category wordt "verhuurd_wonen" (niet ontwikkeling)
VERHUURD_KEYWORDS = (
    "verhuurde staat", "in verhuurde staat", "verhuurd", "verhuurde",
    "zittende huurder", "met huurder", "met huurders",
    "beleggingsobject", "belegd", "belegging",
    "huurovereenkomst lopend", "lopend huurcontract",
    "huurbeding is niet ingeroepen",           # veiling-term: huurder blijft
    "huurbeding_is_niet_ingeroepen",
    "tenant in place", "rented",
)

# Keywords voor al bewoond maar niet verhuurd (eigen gebruiker) — geen risico
BEWOOND_KEYWORDS = (
    "bewoond", "in bewoonde staat", "eigen gebruik",
    "gebruikt door eigenaar", "owner-occupied",
)

# Veiling gebruikssituatie-codes van vastgoedveiling.nl
VEILING_VERHUURD_SITUATIES = {
    "verhuurd",
    "huurbeding_is_niet_ingeroepen",
    "huurbeding_niet_ingeroepen",
    "huurovereenkomst_aanwezig",
}


# ── Hulpfuncties ─────────────────────────────────────────────────────────────
def _norm(s: str) -> str:
    return (s or "").strip().lower()


def _bevat_keyword(tekst: str, keywords) -> bool:
    t = _norm(tekst)
    return any(kw in t for kw in keywords)


def type_in_set(type_woning: str, typeset: set) -> bool:
    """Match type_woning (case-insensitive) tegen een set.
    Doet óók een 'contains' match: als type_woning 'Bedrijfspand (veiling)' is
    en de set bevat 'bedrijfspand' dan is dat ook een hit."""
    t = _norm(type_woning)
    if not t:
        return False
    if t in typeset:
        return True
    for kw in typeset:
        if kw in t:
            return True
    return False


# ── Hoofd-classificatie ──────────────────────────────────────────────────────
def classificeer(
    type_woning: str,
    adres: str = "",
    extra_tekst: str = "",
    gebruikssituatie: str = "",
    is_commercieel_hint: Optional[bool] = None,
) -> dict:
    """Beslis de category van een pand.

    Args:
        type_woning: type-string zoals Funda/makelaar die teruggeeft
        adres: volledig adres (soms staat 'Winkel met bovenwoning' in adres)
        extra_tekst: vrije-tekst velden (beschrijving, titel) voor keyword-scan
        gebruikssituatie: veiling-specifiek (verhuurd, eigen_gebruik, etc)
        is_commercieel_hint: wat de scraper zelf dacht (niet bindend)

    Returns:
        dict met keys: category, subtype, is_verhuurd, redenen, risk_flags
    """
    type_n = _norm(type_woning)
    combined = f"{type_woning} {adres} {extra_tekst}".lower()
    gs_n = _norm(gebruikssituatie)

    redenen = []
    risk_flags = []

    # ── Stap 1: harde skip voor niet-woon-categorieën ──
    if type_in_set(type_woning, SKIP_TYPES):
        redenen.append(f"type '{type_woning}' staat op skip-lijst")
        return {
            "category": "skip",
            "subtype": type_woning,
            "is_verhuurd": False,
            "redenen": redenen,
            "risk_flags": [],
        }

    # "Beleggingsobject" zonder specifieke typering = vrijwel altijd verhuurd;
    # expliciet skippen (staat al in SKIP_TYPES, hier als backup via adres).
    if "beleggingsobject" in combined and "woning" not in combined and "appartement" not in combined:
        redenen.append("beleggingsobject zonder woning-kenmerk")
        return {
            "category": "skip",
            "subtype": type_woning or "beleggingsobject",
            "is_verhuurd": True,
            "redenen": redenen,
            "risk_flags": ["verhuurd"],
        }

    # ── Stap 2: verhuurd-detectie ──
    is_verhuurd = False
    if gs_n in VEILING_VERHUURD_SITUATIES:
        is_verhuurd = True
        redenen.append(f"veiling gebruikssituatie: {gs_n}")
    if _bevat_keyword(combined, VERHUURD_KEYWORDS):
        is_verhuurd = True
        redenen.append("verhuurd-keyword in type/adres/beschrijving")

    if is_verhuurd:
        risk_flags.append("verhuurd")

    # ── Stap 3: transformatie-kandidaat (commercieel met woonpotentieel) ──
    if type_in_set(type_woning, TRANSFORMATIE_TYPES) or (
        is_commercieel_hint and any(kw in combined for kw in (
            "kantoor", "winkel", "horeca", "praktijk"
        ))
    ):
        cat = "verhuurd_wonen" if is_verhuurd else "transformatie"
        return {
            "category": cat,
            "subtype": type_woning,
            "is_verhuurd": is_verhuurd,
            "redenen": redenen + ["commercieel type met woon-transformatiepotentieel"],
            "risk_flags": risk_flags + ["commercieel → woonbestemming check vereist"],
        }

    # ── Stap 4: wonen ──
    if type_in_set(type_woning, WOON_TYPES) or (not type_n and is_commercieel_hint is False):
        return {
            "category": "verhuurd_wonen" if is_verhuurd else "wonen",
            "subtype": type_woning or "wonen",
            "is_verhuurd": is_verhuurd,
            "redenen": redenen,
            "risk_flags": risk_flags,
        }

    # ── Stap 5: onbekend → defensief skippen ──
    # Bij een lege of onbekende type-string kunnen we beter uitsluiten dan
    # vervuilen. Een ontwikkelaar wil geen noise.
    if not type_n:
        # is_commercieel hint kan soms leiden zijn — zo niet: skip
        if is_commercieel_hint is False:
            return {
                "category": "verhuurd_wonen" if is_verhuurd else "wonen",
                "subtype": "wonen (aangenomen)",
                "is_verhuurd": is_verhuurd,
                "redenen": redenen + ["type leeg, fallback wonen op scraper-hint"],
                "risk_flags": risk_flags,
            }
        redenen.append("type leeg en geen woon-hint — defensief skip")
        return {
            "category": "skip",
            "subtype": "",
            "is_verhuurd": is_verhuurd,
            "redenen": redenen,
            "risk_flags": risk_flags,
        }

    # Onbekend type (niet woon, niet transformatie, niet skip) → skip
    redenen.append(f"onbekend type '{type_woning}' — niet op whitelist")
    return {
        "category": "skip",
        "subtype": type_woning,
        "is_verhuurd": is_verhuurd,
        "redenen": redenen,
        "risk_flags": risk_flags,
    }


def classificeer_property(prop) -> dict:
    """Helper: classificeer aan de hand van een Property-object.
    Haalt beschrijvings- en gebruikssituatie-velden uit prop.calc als die er zijn."""
    calc = getattr(prop, "calc", {}) or {}
    extra = " ".join(str(x) for x in [
        calc.get("beschrijving_parsed", ""),
        calc.get("type_verkoop", ""),
        calc.get("status_veiling", ""),
    ])
    gs = calc.get("gebruikssituatie", "")
    return classificeer(
        type_woning=prop.type_woning or "",
        adres=prop.adres or "",
        extra_tekst=extra,
        gebruikssituatie=gs,
        is_commercieel_hint=getattr(prop, "is_commercieel", None),
    )
