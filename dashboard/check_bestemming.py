"""
check_bestemming.py — Bepaal de bestemming (Wonen/Gemengd/Bedrijf/Kantoor) voor een
Nederlands adres via de Ruimtelijke Plannen API v4 (Kadaster / Informatiehuis Ruimte).

Flow:
  1. PDOK Locatieserver free-text search   (geen API key)
      adres -> RD-coordinaten (EPSG:28992)
  2. RP API v4 POST /plannen/_zoek          (API key verplicht)
      RD-coordinaat -> vigerend bestemmingsplan (planId)
  3. RP API v4 POST /plannen/{planId}/bestemmingsvlakken/_zoek
      RD-coordinaat -> bestemmingsvlak met 'naam' / 'bestemmingshoofdgroep'

API key aanvragen (gratis):
  https://developer.omgevingswet.overheid.nl/formulieren/api-key-aanvragen-0/
  (naam / e-mail / organisatie / telefoonnummer + Fair Use Policy accepteren)

Rate limiting:
  Geen harde limiet gepubliceerd. Fair Use Policy geldt. In de praktijk:
  ~ max een paar requests per seconde; voor een daily scraper ruim voldoende.
  Key komt via e-mail na goedkeuring (meestal 1-3 werkdagen).
"""

from __future__ import annotations

import os
import re
import time
from typing import Optional

import requests

RP_BASE = "https://ruimte.omgevingswet.overheid.nl/ruimtelijke-plannen/api/opvragen/v4"
PDOK_URL = "https://api.pdok.nl/bzk/locatieserver/search/v3_1/free"

# Keyword mapping van 'naam' / 'bestemmingshoofdgroep' -> category
WONEN_KEYS = ("wonen", "woondoeleinden", "woongebied")
GEMENGD_KEYS = ("gemengd", "centrum", "horeca-wonen")
BEDRIJF_KEYS = ("bedrijf", "bedrijven", "bedrijventerrein", "industrie")
KANTOOR_KEYS = ("kantoor", "kantoren")


def _classify(naam: str, hoofdgroep: str = "") -> tuple[str, bool]:
    """Zet een bestemmingsnaam om naar (categorie, wonen_toegestaan)."""
    blob = f"{naam} {hoofdgroep}".lower()
    if any(k in blob for k in WONEN_KEYS):
        return "Wonen", True
    if any(k in blob for k in GEMENGD_KEYS):
        return "Gemengd", True  # gemengd staat wonen meestal toe
    if any(k in blob for k in KANTOOR_KEYS):
        return "Kantoor", False
    if any(k in blob for k in BEDRIJF_KEYS):
        return "Bedrijf", False
    return "Onbekend", False


def _pdok_geocode(adres: str, stad: str, postcode: str = "") -> Optional[dict]:
    """Vraag PDOK Locatieserver om RD-coordinaten. Geen auth nodig."""
    query_parts = [adres, postcode, stad]
    q = " ".join(p for p in query_parts if p)
    r = requests.get(
        PDOK_URL,
        params={"q": q, "fq": "type:adres", "rows": 1},
        timeout=10,
    )
    r.raise_for_status()
    docs = r.json().get("response", {}).get("docs", [])
    if not docs:
        return None
    doc = docs[0]
    m = re.match(r"POINT\(([\d.]+)\s+([\d.]+)\)", doc["centroide_rd"])
    if not m:
        return None
    return {
        "x": float(m.group(1)),
        "y": float(m.group(2)),
        "weergavenaam": doc.get("weergavenaam"),
        "postcode": doc.get("postcode"),
        "gemeente": doc.get("gemeentenaam"),
    }


def _rp_post(path: str, body: dict, api_key: str) -> dict:
    """POST naar RP API v4 met verplichte headers."""
    r = requests.post(
        f"{RP_BASE}{path}",
        json=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Content-Crs": "epsg:28992",
            "Accept-Crs": "epsg:28992",
            "x-api-key": api_key,
        },
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def check_bestemming(adres: str, stad: str, postcode: str = "") -> dict:
    """
    Returns: {
        'bestemming': 'Wonen' | 'Gemengd' | 'Bedrijf' | 'Kantoor' | 'Onbekend',
        'wonen_toegestaan': bool,
        'plan_naam': str,
        'details': str,
    }
    """
    result = {
        "bestemming": "Onbekend",
        "wonen_toegestaan": False,
        "plan_naam": "",
        "details": "",
    }

    # Stap 1: PDOK geocoding
    geo = _pdok_geocode(adres, stad, postcode)
    if not geo:
        result["details"] = f"Adres niet gevonden in PDOK: {adres}, {stad}"
        return result

    api_key = os.environ.get("RP_API_KEY")
    if not api_key:
        result["details"] = (
            f"Gevonden: {geo['weergavenaam']} (RD {geo['x']:.0f},{geo['y']:.0f}). "
            "Geen RP_API_KEY in environment — kan bestemmingsplan niet opvragen."
        )
        return result

    # Stap 2: zoek vigerend bestemmingsplan op dit punt
    geo_body = {
        "_geo": {
            "intersectAndNotTouches": {
                "type": "Point",
                "coordinates": [geo["x"], geo["y"]],
            }
        }
    }
    try:
        plannen = _rp_post(
            "/plannen/_zoek?planType=bestemmingsplan&planStatus=vastgesteld",
            geo_body,
            api_key,
        )
    except requests.HTTPError as e:
        result["details"] = f"RP API plannen fout: {e}"
        return result

    embedded = plannen.get("_embedded", {}).get("plannen", [])
    if not embedded:
        result["details"] = f"Geen vigerend bestemmingsplan gevonden op {geo['weergavenaam']}"
        return result

    # Pak meest recente vastgestelde plan
    plan = embedded[0]
    plan_id = plan.get("id")
    result["plan_naam"] = plan.get("naam", "") or plan.get("planstatusInfo", {}).get("planstatus", "")

    # Stap 3: welke bestemmingsvlakken gelden op dit punt
    time.sleep(0.2)  # wees aardig voor de API
    try:
        vlakken = _rp_post(
            f"/plannen/{plan_id}/bestemmingsvlakken/_zoek",
            geo_body,
            api_key,
        )
    except requests.HTTPError as e:
        result["details"] = f"RP API bestemmingsvlakken fout: {e}"
        return result

    vlak_list = vlakken.get("_embedded", {}).get("bestemmingsvlakken", [])
    if not vlak_list:
        # Fallback: probeer enkelbestemmingen / dubbelbestemmingen endpoint varianten
        result["details"] = f"Geen bestemmingsvlakken gevonden in plan {plan_id}"
        return result

    # Verzamel alle bestemmingen op dit punt; dubbelbestemmingen zijn bonus
    naam = vlak_list[0].get("naam", "")
    hoofdgroep = vlak_list[0].get("bestemmingshoofdgroep", "")
    categorie, wonen = _classify(naam, hoofdgroep)

    result["bestemming"] = categorie
    result["wonen_toegestaan"] = wonen
    result["details"] = (
        f"Adres: {geo['weergavenaam']}. Plan: {result['plan_naam']} ({plan_id}). "
        f"Bestemming: '{naam}' (hoofdgroep: {hoofdgroep or 'n.v.t.'})."
    )
    return result


if __name__ == "__main__":
    tests = [
        ("Zwaluwstraat 25", "Rotterdam", ""),
        ("Bezuidenhoutseweg 60", "Den Haag", ""),
        ("Overschieseweg 204", "Rotterdam", ""),
    ]
    for adres, stad, pc in tests:
        print(f"\n=== {adres}, {stad} ===")
        out = check_bestemming(adres, stad, pc)
        for k, v in out.items():
            print(f"  {k}: {v}")
