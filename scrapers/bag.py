"""
BAG verificatie — officiële gegevens voor een pand.

Gebruikt PDOK Locatieserver (adres → BAG ID) + PDOK BAG WFS (BAG ID → volledige
gegevens: bouwjaar, oppervlakte, gebruiksdoel, pandstatus).

Waarom dit belangrijk is voor Bateau: Funda en makelaars vullen soms verkeerd
in. Bouwjaar 1920 kan in BAG 1890 zijn (impact op monumentstatus), opgegeven
oppervlak van 120 m² kan 95 m² zijn (breekt marge-berekening), en een pand
met `gebruiksdoel: industriefunctie` is géén woning — ook al staat het op Funda.

Caching: BAG-data verandert nauwelijks, dus 90 dagen TTL in SQLite.
"""
from __future__ import annotations

import logging
import requests
from typing import Optional
from urllib.parse import quote

from database import (
    energielabel_cache_get as _unused_import,   # keep import pattern
)

logger = logging.getLogger(__name__)

PDOK_LOCATIESERVER = (
    "https://api.pdok.nl/bzk/locatieserver/search/v3_1/free"
)
BAG_WFS = "https://service.pdok.nl/lv/bag/wfs/v2_0"

# BAG gebruiksdoelen die wél woning zijn
WOON_GEBRUIKSDOEL = {"woonfunctie"}

# Gebruiksdoelen die duiden op niet-woon (maar mogelijk transformeerbaar)
TRANSFORMATIE_GEBRUIKSDOEL = {
    "kantoorfunctie", "winkelfunctie", "bijeenkomstfunctie",
    "logiesfunctie", "gezondheidszorgfunctie", "onderwijsfunctie",
}

# Gebruiksdoelen die nagenoeg altijd ongeschikt zijn voor woon-ontwikkeling
SKIP_GEBRUIKSDOEL = {
    "industriefunctie", "sportfunctie", "celfunctie",
    "overige gebruiksfunctie",
}


def _wfs_filter_identificatie(bag_id: str) -> str:
    return (
        "<Filter xmlns=\"http://www.opengis.net/ogc\">"
        "<PropertyIsEqualTo>"
        "<PropertyName>identificatie</PropertyName>"
        f"<Literal>{bag_id}</Literal>"
        "</PropertyIsEqualTo>"
        "</Filter>"
    )


def locatieserver_lookup(postcode: str, huisnummer: str,
                          huisletter: str = "", toevoeging: str = "") -> Optional[dict]:
    """Zoek adres op via PDOK Locatieserver en retourneer BAG adresseerbaarobject_id
    + woonplaats + wijk + coords. Gratis, geen key."""
    if not postcode or not huisnummer:
        return None
    q_parts = [postcode.replace(" ", "").upper(), str(huisnummer)]
    if huisletter:
        q_parts.append(huisletter)
    if toevoeging:
        q_parts.append(toevoeging)
    q = " ".join(q_parts)
    try:
        r = requests.get(
            PDOK_LOCATIESERVER,
            params={"q": q, "fq": "type:adres", "rows": 1},
            timeout=10,
        )
        r.raise_for_status()
        docs = r.json().get("response", {}).get("docs", [])
        if not docs:
            return None
        d = docs[0]
        return {
            "adresseerbaarobject_id": d.get("adresseerbaarobject_id"),
            "nummeraanduiding_id": d.get("nummeraanduiding_id"),
            "postcode": d.get("postcode"),
            "huisnummer": d.get("huisnummer"),
            "straatnaam": d.get("straatnaam"),
            "woonplaats": d.get("woonplaatsnaam"),
            "gemeente": d.get("gemeentenaam"),
            "wijk": d.get("wijknaam"),
            "buurt": d.get("buurtnaam"),
            "centroide_rd": d.get("centroide_rd"),
            "centroide_ll": d.get("centroide_ll"),
        }
    except Exception as e:
        logger.debug("PDOK locatieserver fout %s: %s", q, e)
        return None


def bag_verblijfsobject(bag_id: str) -> Optional[dict]:
    """Haal BAG verblijfsobject-data op via WFS. Retourneert dict met bouwjaar,
    oppervlakte, gebruiksdoel, pandstatus etc."""
    if not bag_id:
        return None
    try:
        r = requests.get(
            BAG_WFS,
            params={
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetFeature",
                "typeNames": "bag:verblijfsobject",
                "count": 1,
                "outputFormat": "application/json",
                "filter": _wfs_filter_identificatie(bag_id),
            },
            timeout=15,
        )
        r.raise_for_status()
        features = r.json().get("features", [])
        if not features:
            return None
        p = features[0].get("properties", {})
        return {
            "bag_id": bag_id,
            "oppervlakte": p.get("oppervlakte"),
            "gebruiksdoel": (p.get("gebruiksdoel") or "").lower(),
            "status": p.get("status"),
            "pandstatus": p.get("pandstatus"),
            "bouwjaar": p.get("bouwjaar"),
            "pandidentificatie": p.get("pandidentificatie"),
        }
    except Exception as e:
        logger.debug("BAG WFS fout %s: %s", bag_id, e)
        return None


# ── Cache in DB (hergebruik patroon van energielabel_cache) ───────────────
import sqlite3
from datetime import datetime
from config import DB_PATH


def _init_cache():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bag_cache (
            cache_key TEXT PRIMARY KEY,
            bag_id TEXT,
            bouwjaar INTEGER,
            oppervlakte INTEGER,
            gebruiksdoel TEXT,
            pandstatus TEXT,
            status TEXT,
            pandidentificatie TEXT,
            straatnaam TEXT,
            woonplaats TEXT,
            wijk TEXT,
            buurt TEXT,
            gemeente TEXT,
            centroide_rd TEXT,
            centroide_ll TEXT,
            gecached_op TEXT,
            gevonden INTEGER
        )
    """)
    # Migratie: voeg kolommen toe als tabel al bestond zonder centroide
    for col in ("centroide_rd", "centroide_ll"):
        try:
            conn.execute(f"ALTER TABLE bag_cache ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()


def _cache_get(key: str, max_age_dagen: int = 90) -> Optional[dict]:
    _init_cache()
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute("""
            SELECT bag_id, bouwjaar, oppervlakte, gebruiksdoel, pandstatus,
                   status, pandidentificatie, straatnaam, woonplaats, wijk,
                   buurt, gemeente, centroide_rd, centroide_ll,
                   gecached_op, gevonden
            FROM bag_cache WHERE cache_key = ?
        """, (key,)).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    try:
        leeftijd = (datetime.now() - datetime.fromisoformat(row[14])).days
        if leeftijd > max_age_dagen:
            return None
    except Exception:
        return None
    return {
        "bag_id": row[0], "bouwjaar": row[1], "oppervlakte": row[2],
        "gebruiksdoel": row[3], "pandstatus": row[4], "status": row[5],
        "pandidentificatie": row[6], "straatnaam": row[7],
        "woonplaats": row[8], "wijk": row[9], "buurt": row[10],
        "gemeente": row[11], "centroide_rd": row[12], "centroide_ll": row[13],
        "gevonden": bool(row[15]),
    }


def _cache_set(key: str, data: Optional[dict]):
    _init_cache()
    now = datetime.now().isoformat()
    d = data or {}
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("""
            INSERT INTO bag_cache
                (cache_key, bag_id, bouwjaar, oppervlakte, gebruiksdoel,
                 pandstatus, status, pandidentificatie, straatnaam, woonplaats,
                 wijk, buurt, gemeente, centroide_rd, centroide_ll,
                 gecached_op, gevonden)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                bag_id=excluded.bag_id, bouwjaar=excluded.bouwjaar,
                oppervlakte=excluded.oppervlakte, gebruiksdoel=excluded.gebruiksdoel,
                pandstatus=excluded.pandstatus, status=excluded.status,
                pandidentificatie=excluded.pandidentificatie,
                straatnaam=excluded.straatnaam, woonplaats=excluded.woonplaats,
                wijk=excluded.wijk, buurt=excluded.buurt, gemeente=excluded.gemeente,
                centroide_rd=excluded.centroide_rd, centroide_ll=excluded.centroide_ll,
                gecached_op=excluded.gecached_op, gevonden=excluded.gevonden
        """, (
            key, d.get("bag_id"), d.get("bouwjaar"), d.get("oppervlakte"),
            d.get("gebruiksdoel"), d.get("pandstatus"), d.get("status"),
            d.get("pandidentificatie"), d.get("straatnaam"),
            d.get("woonplaats"), d.get("wijk"), d.get("buurt"),
            d.get("gemeente"), d.get("centroide_rd"), d.get("centroide_ll"),
            now, 1 if data else 0,
        ))
        conn.commit()
    finally:
        conn.close()


# ── Publieke API ──────────────────────────────────────────────────────────
import re
_HUISNR_RE = re.compile(r"(\d+)\s*([A-Za-z])?\s*([A-Za-z0-9\-]+)?")


def _parse_huisnummer(adres: str) -> tuple[str, str, str]:
    if not adres:
        return "", "", ""
    m = _HUISNR_RE.search(adres)
    if not m:
        return "", "", ""
    return m.group(1) or "", (m.group(2) or "").strip()[:1].upper(), (m.group(3) or "").strip()[:4]


def verrijk_bag(postcode: str, adres: str) -> dict:
    """Verrijk een pand met BAG-gegevens. Combineert locatieserver + WFS,
    met 90-dagen DB-cache. Retourneert dict (lege dict als niet gevonden)."""
    huisnummer, huisletter, toevoeging = _parse_huisnummer(adres)
    if not postcode or not huisnummer:
        return {}

    key = f"{postcode.replace(' ', '').upper()}|{huisnummer}|{huisletter}|{toevoeging}"
    cached = _cache_get(key)
    if cached is not None:
        return cached if cached.get("gevonden") else {}

    loc = locatieserver_lookup(postcode, huisnummer, huisletter, toevoeging)
    if not loc or not loc.get("adresseerbaarobject_id"):
        _cache_set(key, None)
        return {}

    # PDOK locatieserver doet fuzzy matching — als resultaat-postcode/huisnr
    # niet matcht met aanvraag, wijs af om verkeerde BAG-data te voorkomen.
    loc_pc = (loc.get("postcode") or "").replace(" ", "").upper()
    req_pc = postcode.replace(" ", "").upper()
    if loc_pc != req_pc or str(loc.get("huisnummer") or "") != str(huisnummer):
        logger.debug(
            "BAG mismatch: aanvraag %s %s, gevonden %s %s — skip",
            req_pc, huisnummer, loc_pc, loc.get("huisnummer"),
        )
        _cache_set(key, None)
        return {}

    vo = bag_verblijfsobject(loc["adresseerbaarobject_id"])
    if not vo:
        _cache_set(key, None)
        return {}

    result = {**loc, **vo}
    _cache_set(key, result)
    return result


def classificeer_gebruiksdoel(gebruiksdoel: str) -> str:
    """Classificeer BAG gebruiksdoel naar 'wonen' / 'transformatie' / 'skip'."""
    gd = (gebruiksdoel or "").lower()
    if gd in WOON_GEBRUIKSDOEL:
        return "wonen"
    if gd in TRANSFORMATIE_GEBRUIKSDOEL:
        return "transformatie"
    if gd in SKIP_GEBRUIKSDOEL:
        return "skip"
    return "onbekend"


def bouwjaar_afwijking(funda_bj: int, bag_bj: int) -> Optional[int]:
    """Retourneer verschil Funda vs BAG bouwjaar. None als één ontbreekt.
    >15 jaar verschil = rode vlag (renovatie niet in BAG geregistreerd,
    of Funda opgave onjuist)."""
    if not funda_bj or not bag_bj:
        return None
    return funda_bj - bag_bj
