"""
CBS Kerncijfers wijken en buurten — gemeente-niveau voor nu.

Publieke Open Data (geen key), dataset 86165NED (2025).
Per pand: gemeente-kenmerken als proxy voor wijk-kwaliteit.

Waarom gemeente en niet wijk? BAG geeft wijknaam maar die matched niet
1-op-1 met CBS WijkenEnBuurten strings (extra spaties, codes etc). Voor
MVP: gemeente-niveau. Later uitbreiden naar wijk-match via CBS Codering_3.

Gecached in DB, gerefreshed elke 30 dagen (CBS updates 1× per jaar).
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

CBS_URL = "https://opendata.cbs.nl/ODataApi/odata/86165NED/TypedDataSet"


def _init_cache():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cbs_buurt_cache (
            gemeente TEXT PRIMARY KEY,
            data TEXT,
            gecached_op TEXT
        )
    """)
    conn.commit()
    conn.close()


def _cache_get(gemeente: str, max_age_dagen: int = 30) -> Optional[dict]:
    _init_cache()
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT data, gecached_op FROM cbs_buurt_cache WHERE gemeente = ?",
            (gemeente.lower(),),
        ).fetchone()
    finally:
        conn.close()
    if not row or not row[0]:
        return None
    try:
        leeftijd = (datetime.now() - datetime.fromisoformat(row[1])).days
        if leeftijd > max_age_dagen:
            return None
        return json.loads(row[0])
    except Exception:
        return None


def _cache_set(gemeente: str, data: dict):
    _init_cache()
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("""
            INSERT INTO cbs_buurt_cache (gemeente, data, gecached_op)
            VALUES (?, ?, ?)
            ON CONFLICT(gemeente) DO UPDATE SET
                data=excluded.data, gecached_op=excluded.gecached_op
        """, (gemeente.lower(), json.dumps(data), now))
        conn.commit()
    finally:
        conn.close()


_ALL_GEMEENTES: dict = {}   # in-process cache van alle NL gemeentes


def _fetch_all_gemeentes() -> dict:
    """Haal alle NL gemeentes in één call op (GM-codes). Server-side filter
    op Gemeentenaam is fragiel door padding — lokaal filteren is robuuster."""
    global _ALL_GEMEENTES
    if _ALL_GEMEENTES:
        return _ALL_GEMEENTES
    try:
        # ~350 gemeentes × ~30KB = ~10MB ruwe response. Acceptabel eenmalig.
        r = requests.get(
            CBS_URL,
            params={
                "$filter": "startswith(WijkenEnBuurten,'GM')",
                "$format": "json",
                "$select": (
                    "WijkenEnBuurten,Gemeentenaam_1,Bevolkingsdichtheid_34,"
                    "GemiddeldeWOZWaardeVanWoningen_39,Koopwoningen_47,"
                    "HuurwoningenTotaal_48,InBezitWoningcorporatie_49,"
                    "PercentageMeergezinswoning_45,NieuwbouwWoningen_36"
                ),
            },
            timeout=30,
        )
        if r.status_code != 200:
            return {}
        for v in r.json().get("value", []):
            naam = (v.get("Gemeentenaam_1") or "").strip()
            if not naam:
                continue
            _ALL_GEMEENTES[naam.lower()] = {
                "wijkcode": (v.get("WijkenEnBuurten") or "").strip(),
                "gemeente": naam,
                "bevolkingsdichtheid": v.get("Bevolkingsdichtheid_34"),
                "gem_woz_x1000": v.get("GemiddeldeWOZWaardeVanWoningen_39"),
                "pct_koop": v.get("Koopwoningen_47"),
                "pct_huur": v.get("HuurwoningenTotaal_48"),
                "pct_corp": v.get("InBezitWoningcorporatie_49"),
                "pct_meergezins": v.get("PercentageMeergezinswoning_45"),
                "nieuwbouw_woningen": v.get("NieuwbouwWoningen_36"),
            }
        logger.info("CBS: %d gemeentes geladen", len(_ALL_GEMEENTES))
    except Exception as e:
        logger.warning("CBS bulk-fetch fout: %s", e)
    return _ALL_GEMEENTES


def _fetch_gemeente(gemeente: str) -> Optional[dict]:
    """Zoek gemeente in de gecachte bulk-data (case-insensitive, fuzzy)."""
    all_g = _fetch_all_gemeentes()
    if not all_g:
        return None
    key = gemeente.strip().lower()
    if key in all_g:
        return all_g[key]
    # Fuzzy: zoek substring-match
    for k, v in all_g.items():
        if key in k or k in key:
            return v
    return None


def get_gemeente_cijfers(gemeente: str) -> Optional[dict]:
    """Retourneer CBS key-cijfers voor gemeente (gecached)."""
    if not gemeente:
        return None
    g = gemeente.strip().title()
    # Normaliseer veelvoorkomende alias
    aliases = {
        "Den Haag": "'s-Gravenhage",
        "S-Gravenhage": "'s-Gravenhage",
    }
    g = aliases.get(g, g)
    cached = _cache_get(g)
    if cached is not None:
        return cached
    data = _fetch_gemeente(g)
    if data:
        _cache_set(g, data)
    return data


def wijk_kwaliteit_score(cbs: dict) -> Optional[int]:
    """Heel ruwe score 0-100 op basis van CBS cijfers.
    Hogere WOZ + hoger % koop + lager % corporatie = "betere" wijk."""
    if not cbs:
        return None
    score = 50
    woz = cbs.get("gem_woz_x1000") or 0
    if woz >= 500: score += 25
    elif woz >= 400: score += 15
    elif woz >= 300: score += 5
    elif woz <= 200: score -= 15
    pct_koop = cbs.get("pct_koop") or 0
    if pct_koop >= 70: score += 15
    elif pct_koop >= 50: score += 5
    elif pct_koop <= 30: score -= 10
    pct_corp = cbs.get("pct_corp") or 0
    if pct_corp >= 40: score -= 10
    elif pct_corp <= 15: score += 5
    return max(0, min(100, score))
