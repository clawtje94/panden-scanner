"""
Altum AI — Kadaster transactieprijzen + woningwaarde.

Altum biedt een gratis tier van ~50 calls/maand met o.a.:
  - Koopsom (Kadaster transactiehistorie per adres)
  - Modelwaarde (ML-schatting marktwaarde)
  - Vraagprijs-vergelijking

Dit is de enige betrouwbare *gratis* publieke bron voor échte
transactieprijzen (Funda = vraag, NVM Brainbay = betaald).

Registratie:
  1. https://altum.ai/sign-up
  2. Create API key (gratis tier: koopsom + modelwaarde endpoints)
  3. Zet `ALTUM_API_KEY` als GH-secret + env-var

Zonder key: deze module faalt stil (lookups retourneren {}). Scanner
blijft werken met alleen Funda-referenties.

Budget-bewust: de 50 calls/maand zijn KOSTBAAR. We cachen agressief
(90 dagen) en roepen alleen aan voor panden met dealscore ≥ 65 (A/A+).
"""
from __future__ import annotations

import logging
import sqlite3
import json
import requests
from datetime import datetime
from typing import Optional

from config import DB_PATH

logger = logging.getLogger(__name__)

# API endpoints (Altum publiceert meerdere — we gebruiken de Koopsom endpoint)
ALTUM_KOOPSOM_URL = "https://api.altum.ai/koopsom"
ALTUM_MODELWAARDE_URL = "https://api.altum.ai/modelwaarde"

# Key via env; als leeg dan module doet niks
import os
ALTUM_API_KEY = os.environ.get("ALTUM_API_KEY", "")


def _init_cache():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS altum_cache (
            cache_key TEXT PRIMARY KEY,
            type TEXT,
            raw_json TEXT,
            gecached_op TEXT,
            gevonden INTEGER
        )
    """)
    conn.commit()
    conn.close()


def _cache_get(key: str, max_age_dagen: int = 90) -> Optional[dict]:
    _init_cache()
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute("""
            SELECT raw_json, gecached_op, gevonden FROM altum_cache
            WHERE cache_key = ?
        """, (key,)).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    try:
        leeftijd = (datetime.now() - datetime.fromisoformat(row[1])).days
        if leeftijd > max_age_dagen:
            return None
    except Exception:
        return None
    if not row[2]:
        return {}  # gecached als leeg = niet gevonden
    try:
        return json.loads(row[0])
    except Exception:
        return None


def _cache_set(key: str, kind: str, data: Optional[dict]):
    _init_cache()
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("""
            INSERT INTO altum_cache (cache_key, type, raw_json, gecached_op, gevonden)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                type=excluded.type, raw_json=excluded.raw_json,
                gecached_op=excluded.gecached_op, gevonden=excluded.gevonden
        """, (
            key, kind,
            json.dumps(data) if data else None,
            now, 1 if data else 0,
        ))
        conn.commit()
    finally:
        conn.close()


def _call(url: str, postcode: str, huisnummer: str, toevoeging: str = "") -> Optional[dict]:
    if not ALTUM_API_KEY:
        return None
    params = {
        "postcode": postcode.replace(" ", "").upper(),
        "huisnummer": huisnummer,
    }
    if toevoeging:
        params["huisnummer_toevoeging"] = toevoeging
    try:
        r = requests.get(
            url,
            params=params,
            headers={"x-api-key": ALTUM_API_KEY, "Accept": "application/json"},
            timeout=15,
        )
    except Exception as e:
        logger.debug("Altum request fout %s: %s", url, e)
        return None
    if r.status_code == 401:
        logger.warning("Altum 401 — key ongeldig of quota op")
        return None
    if r.status_code == 429:
        logger.warning("Altum 429 — rate limit / quota op")
        return None
    if r.status_code == 404:
        return {}  # niet gevonden, expliciet leeg
    if r.status_code != 200:
        logger.debug("Altum status %d op %s %s", r.status_code, postcode, huisnummer)
        return None
    try:
        return r.json()
    except Exception:
        return None


def get_koopsom(postcode: str, huisnummer: str, toevoeging: str = "") -> Optional[dict]:
    """Kadaster-transactie historie: laatste koopsom, datum, prijs/m²."""
    if not postcode or not huisnummer:
        return None
    key = f"koopsom|{postcode}|{huisnummer}|{toevoeging}".lower().replace(" ", "")
    cached = _cache_get(key)
    if cached is not None:
        return cached or None  # lege dict = cached leeg
    data = _call(ALTUM_KOOPSOM_URL, postcode, huisnummer, toevoeging)
    if data is None:
        return None  # tijdelijke fout — niet cachen
    _cache_set(key, "koopsom", data)
    return data or None


def get_modelwaarde(postcode: str, huisnummer: str, toevoeging: str = "") -> Optional[dict]:
    """ML-schatting marktwaarde voor woningwaarde-validatie."""
    if not postcode or not huisnummer:
        return None
    key = f"modelwaarde|{postcode}|{huisnummer}|{toevoeging}".lower().replace(" ", "")
    cached = _cache_get(key)
    if cached is not None:
        return cached or None
    data = _call(ALTUM_MODELWAARDE_URL, postcode, huisnummer, toevoeging)
    if data is None:
        return None
    _cache_set(key, "modelwaarde", data)
    return data or None


def is_available() -> bool:
    return bool(ALTUM_API_KEY)
