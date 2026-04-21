"""
EP-Online (RVO) energielabel lookups.

Publieke REST API v5 op https://public.ep-online.nl/api/v5/PandEnergielabel/Adres
Auth via Authorization-header (raw key, geen Bearer-prefix). Gratis key te
verkrijgen op https://apikey.ep-online.nl.

Twee taken:
1. Verrijk een Property met het officiële energielabel (als het pand er nog geen
   heeft, of om de Funda-opgave te verifieren).
2. Flag panden met label E/F/G als 'forced_renovation'-kandidaat — verhuurverbod
   2028 en energieprestatie-eis maken eigenaren vatbaarder voor verkoop.

Lookups worden in de energielabel_cache tabel gecached (default 60 dagen),
zodat we EP-Online niet voor elke scan opnieuw bevragen.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Optional

import requests

from config import EP_ONLINE_API_KEY
from database import energielabel_cache_get, energielabel_cache_set
from models import Property

logger = logging.getLogger(__name__)

EP_ONLINE_URL = "https://public.ep-online.nl/api/v5/PandEnergielabel/Adres"

_HUISNR_RE = re.compile(r"(\d+)\s*([A-Za-z])?\s*([A-Za-z0-9\-]+)?")
_POSTCODE_RE = re.compile(r"\b([1-9]\d{3})\s?([A-Z]{2})\b")

_FORCED_RENOVATION_LABELS = {"E", "F", "G"}


def _parse_huisnummer(adres: str) -> tuple[str, str, str]:
    """Extract huisnummer, huisletter, toevoeging uit een adresregel.
    Retourneert ('', '', '') als niets herkend is."""
    if not adres:
        return "", "", ""
    m = _HUISNR_RE.search(adres)
    if not m:
        return "", "", ""
    nr = m.group(1) or ""
    letter = (m.group(2) or "").strip()
    toevoeging = (m.group(3) or "").strip()
    # Als de letter eigenlijk deel van de toevoeging is (bv "34bis"), laat toevoeging primeren
    if toevoeging and not letter:
        pass
    return nr, letter.upper()[:1], toevoeging[:4]


def _normaliseer_postcode(pc: str) -> str:
    if not pc:
        return ""
    m = _POSTCODE_RE.search(pc.upper().replace(" ", ""))
    if not m:
        return ""
    return f"{m.group(1)}{m.group(2)}"


def _cache_key(postcode: str, huisnummer: str, huisletter: str, toevoeging: str) -> str:
    return "|".join([
        postcode.lower(), huisnummer, huisletter.lower(), toevoeging.lower(),
    ])


def get_energielabel(
    postcode: str,
    huisnummer: str,
    huisletter: str = "",
    toevoeging: str = "",
    timeout: int = 10,
) -> Optional[dict]:
    """Vraag energielabel op bij EP-Online.
    Retourneert dict met label/opnamedatum/geldig_tot/pand_type/bouwjaar/gebruiksoppervlakte,
    of None als niet gevonden. Gebruikt cache (60 dagen).
    """
    postcode = _normaliseer_postcode(postcode)
    if not postcode or not huisnummer:
        return None

    key = _cache_key(postcode, huisnummer, huisletter, toevoeging)
    cached = energielabel_cache_get(key)
    if cached is not None:
        return cached if cached.get("gevonden") else None

    if not EP_ONLINE_API_KEY:
        logger.debug("EP_ONLINE_API_KEY niet gezet — skip lookup %s %s", postcode, huisnummer)
        return None

    params = {"postcode": postcode, "huisnummer": huisnummer}
    if huisletter:
        params["huisletter"] = huisletter
    if toevoeging:
        params["huisnummertoevoeging"] = toevoeging

    try:
        r = requests.get(
            EP_ONLINE_URL,
            params=params,
            headers={
                "Authorization": EP_ONLINE_API_KEY,
                "Accept": "application/json",
            },
            timeout=timeout,
        )
    except Exception as e:
        logger.debug("EP-Online request fout %s %s: %s", postcode, huisnummer, e)
        return None

    if r.status_code == 401:
        logger.warning("EP-Online 401 — key ongeldig of verlopen")
        return None
    if r.status_code == 429:
        logger.warning("EP-Online rate limit 429 — even wachten")
        time.sleep(2.0)
        return None
    if r.status_code == 404:
        energielabel_cache_set(key, None)
        return None
    if r.status_code != 200:
        logger.debug("EP-Online status %d op %s %s", r.status_code, postcode, huisnummer)
        return None

    try:
        data = r.json()
    except Exception:
        return None

    arr = data if isinstance(data, list) else data.get("value") or []
    if not arr:
        energielabel_cache_set(key, None)
        return None

    # Meest recente / geldige record kiezen
    def _sleutel(rec):
        return rec.get("registratiedatum") or rec.get("opnamedatum") or ""
    rec = sorted(arr, key=_sleutel, reverse=True)[0]

    resultaat = {
        "label": str(rec.get("energieklasse") or rec.get("labelLetter") or "").strip().upper(),
        "opnamedatum": rec.get("opnamedatum"),
        "geldig_tot": rec.get("geldigTotDatum"),
        "registratiedatum": rec.get("registratiedatum"),
        "pand_type": rec.get("gebouwklasse") or rec.get("gebouwtype"),
        "bouwjaar": rec.get("bouwjaar"),
        "gebruiksoppervlakte": rec.get("gebruiksoppervlakte"),
        "gevonden": True,
    }
    energielabel_cache_set(key, resultaat)
    return resultaat


def verrijk_energielabel(prop: Property) -> dict:
    """Haal officieel EP-Online label op voor een Property.
    Muteert prop.energie_label als die leeg/onbekend was, en vult een dict terug
    met het EP-Online resultaat + forced_renovation vlag."""
    if not prop.postcode or not prop.adres:
        return {}

    huisnummer, huisletter, toevoeging = _parse_huisnummer(prop.adres)
    if not huisnummer:
        return {}

    data = get_energielabel(prop.postcode, huisnummer, huisletter, toevoeging)
    if not data:
        return {}

    label = (data.get("label") or "").upper()[:1]
    if label and not prop.energie_label:
        prop.energie_label = label

    forced = label in _FORCED_RENOVATION_LABELS
    # Forced renovation redenering: label E/F/G + bouwjaar < 1992 is extra sterk
    # omdat naoorlogse bouw tot 1992 slechte schil heeft — groot renovatie-delta.
    bj = data.get("bouwjaar") or prop.bouwjaar or 0
    forced_sterk = forced and (bj and bj < 1992)

    return {
        "label": label,
        "opnamedatum": data.get("opnamedatum"),
        "geldig_tot": data.get("geldig_tot"),
        "pand_type": data.get("pand_type"),
        "bouwjaar": data.get("bouwjaar"),
        "gebruiksoppervlakte": data.get("gebruiksoppervlakte"),
        "forced_renovation": forced,
        "forced_renovation_sterk": forced_sterk,
        "bron": "ep-online",
    }


def is_forced_renovation(label: str) -> bool:
    return (label or "").upper()[:1] in _FORCED_RENOVATION_LABELS
