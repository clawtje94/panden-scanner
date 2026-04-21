"""
Rijksmonument-detectie via RCE (Rijksdienst Cultureel Erfgoed) open data.

WFS: https://data.geo.cultureelerfgoed.nl/openbaar/wfs
Layer: openbaar:rijksmonumentpunten (geen auth, geen key)

Bateau-impact: monument = 30-50% hogere verbouwkosten + vergunningstraject
+ welstandseisen. Moet altijd als risk-flag zichtbaar zijn vóór aankoop.

Beschermde stadsgezichten (andere layer, later uit te breiden) geven
eveneens welstands-restricties maar niet de volledige monumentstatus.

Gemeentelijke monumenten zijn NIET in één landelijke API beschikbaar —
bekende hotspots voor Bateau (Rotterdam, Den Haag, Delft, Leiden, Dordrecht)
hebben eigen datasets die hier later toegevoegd kunnen worden.
"""
from __future__ import annotations

import logging
import re
import sqlite3
import requests
from datetime import datetime
from typing import Optional

from config import DB_PATH

logger = logging.getLogger(__name__)

RCE_WFS = "https://data.geo.cultureelerfgoed.nl/openbaar/wfs"

# Radius in meters om centroide voor bbox-query. 10m is klein genoeg om
# buurpanden uit te sluiten maar groot genoeg voor geometrische afwijking.
BBOX_RADIUS_M = 8


def _init_cache():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS monument_cache (
            cache_key TEXT PRIMARY KEY,
            is_monument INTEGER,
            rijksmonument_nr TEXT,
            hoofdcategorie TEXT,
            subcategorie TEXT,
            url TEXT,
            gecached_op TEXT
        )
    """)
    conn.commit()
    conn.close()


def _cache_get(key: str, max_age_dagen: int = 180) -> Optional[dict]:
    _init_cache()
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute("""
            SELECT is_monument, rijksmonument_nr, hoofdcategorie, subcategorie,
                   url, gecached_op
            FROM monument_cache WHERE cache_key = ?
        """, (key,)).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    try:
        leeftijd = (datetime.now() - datetime.fromisoformat(row[5])).days
        if leeftijd > max_age_dagen:
            return None
    except Exception:
        return None
    return {
        "is_rijksmonument": bool(row[0]),
        "rijksmonument_nr": row[1],
        "hoofdcategorie": row[2],
        "subcategorie": row[3],
        "url": row[4],
    }


def _cache_set(key: str, data: dict):
    _init_cache()
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("""
            INSERT INTO monument_cache
                (cache_key, is_monument, rijksmonument_nr, hoofdcategorie,
                 subcategorie, url, gecached_op)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                is_monument=excluded.is_monument,
                rijksmonument_nr=excluded.rijksmonument_nr,
                hoofdcategorie=excluded.hoofdcategorie,
                subcategorie=excluded.subcategorie,
                url=excluded.url,
                gecached_op=excluded.gecached_op
        """, (
            key, 1 if data.get("is_rijksmonument") else 0,
            data.get("rijksmonument_nr"), data.get("hoofdcategorie"),
            data.get("subcategorie"), data.get("url"), now,
        ))
        conn.commit()
    finally:
        conn.close()


_POINT_RE = re.compile(r"POINT\(([\d.]+)\s+([\d.]+)\)")


def _parse_rd(centroide_rd: str) -> Optional[tuple[float, float]]:
    if not centroide_rd:
        return None
    m = _POINT_RE.search(centroide_rd)
    if not m:
        return None
    return float(m.group(1)), float(m.group(2))


def check_rijksmonument(centroide_rd: str) -> dict:
    """Check of de RD-coordinaat binnen {BBOX_RADIUS_M}m van een rijksmonument ligt.

    Args:
        centroide_rd: "POINT(x y)" string in EPSG:28992 (zoals PDOK teruggeeft)

    Returns:
        dict met is_rijksmonument (bool) + monument-details als gevonden.
        Lege dict als geen coordinaten of API-fout.
    """
    coords = _parse_rd(centroide_rd)
    if not coords:
        return {}
    x, y = coords
    key = f"{round(x, 1)}|{round(y, 1)}"

    cached = _cache_get(key)
    if cached is not None:
        return cached

    r_m = BBOX_RADIUS_M
    bbox = f"{x - r_m},{y - r_m},{x + r_m},{y + r_m},urn:ogc:def:crs:EPSG::28992"

    try:
        r = requests.get(
            RCE_WFS,
            params={
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetFeature",
                "typeNames": "openbaar:rijksmonumentpunten",
                "count": 3,
                "outputFormat": "application/json",
                "BBOX": bbox,
            },
            timeout=10,
        )
        r.raise_for_status()
        feats = r.json().get("features", [])
    except Exception as e:
        logger.debug("RCE WFS fout %s: %s", key, e)
        return {}

    if not feats:
        result = {"is_rijksmonument": False}
        _cache_set(key, result)
        return result

    # Pak dichtste monument (meestal precies 1 in deze bbox)
    p = feats[0].get("properties", {}) or {}
    result = {
        "is_rijksmonument": True,
        "rijksmonument_nr": str(p.get("rijksmonument_nummer") or ""),
        "hoofdcategorie": p.get("hoofdcategorie"),
        "subcategorie": p.get("subcategorie"),
        "url": p.get("rijksmonumenturl"),
    }
    _cache_set(key, result)
    return result


def verrijk_monument_status(prop, bag_data: Optional[dict] = None) -> dict:
    """Verrijk een Property met monument-status.

    Heeft BAG-data nodig voor RD-coordinaten (bag_data uit scrapers.bag.verrijk_bag).
    Als die er niet is, probeert hij zelf via postcode+adres te zoeken.
    """
    if bag_data and bag_data.get("centroide_rd"):
        return check_rijksmonument(bag_data["centroide_rd"])

    # Fallback: zoek via locatieserver
    if getattr(prop, "postcode", "") and prop.adres:
        try:
            from scrapers.bag import locatieserver_lookup, _parse_huisnummer
            hn, hl, tv = _parse_huisnummer(prop.adres)
            if hn:
                loc = locatieserver_lookup(prop.postcode, hn, hl, tv)
                if loc and loc.get("centroide_rd"):
                    return check_rijksmonument(loc["centroide_rd"])
        except Exception as e:
            logger.debug("Monument lookup fallback fout: %s", e)
    return {}
