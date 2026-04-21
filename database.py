"""
SQLite database voor het bijhouden van geziene panden + historie van observaties.
De pand_geschiedenis tabel slaat prijs/makelaar/status mutaties op zodat we
motion signals kunnen berekenen (prijsverlaging, makelaarswissel, onder bod → terug).
"""
import sqlite3
import logging
from datetime import datetime, timedelta
from models import Property
from config import DB_PATH, SIGNALEN

logger = logging.getLogger(__name__)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS panden (
            url         TEXT PRIMARY KEY,
            source      TEXT,
            adres       TEXT,
            stad        TEXT,
            prijs       INTEGER,
            opp_m2      INTEGER,
            strategie   TEXT,
            marge_pct   REAL,
            winst_euro  INTEGER,
            score       INTEGER,
            eerste_gezien TEXT,
            laatste_gezien TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pand_geschiedenis (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            url         TEXT NOT NULL,
            ts          TEXT NOT NULL,
            prijs       INTEGER,
            makelaar    TEXT,
            status      TEXT,
            type_woning TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_hist_url ON pand_geschiedenis(url)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS energielabel_cache (
            cache_key   TEXT PRIMARY KEY,   -- postcode+huisnummer+toevoeging, lowercase
            label       TEXT,
            opnamedatum TEXT,
            geldig_tot  TEXT,
            registratiedatum TEXT,
            pand_type   TEXT,
            bouwjaar    INTEGER,
            gebruiksoppervlakte INTEGER,
            raw_json    TEXT,
            gecached_op TEXT,
            gevonden    INTEGER               -- 1 = hit, 0 = niet in EP-Online
        )
    """)
    conn.commit()
    conn.close()
    logger.info("Database geïnitialiseerd: %s", DB_PATH)


def is_nieuw(url: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT url FROM panden WHERE url = ?", (url,)).fetchone()
    conn.close()
    return row is None


def sla_op(prop: Property):
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO panden
            (url, source, adres, stad, prijs, opp_m2, strategie, marge_pct, winst_euro, score, eerste_gezien, laatste_gezien)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(url) DO UPDATE SET laatste_gezien = excluded.laatste_gezien
    """, (
        prop.url, prop.source, prop.adres, prop.stad,
        prop.prijs, prop.opp_m2, prop.strategie,
        prop.marge_pct, prop.winst_euro, prop.score,
        now, now,
    ))
    conn.commit()
    conn.close()


def registreer_observatie(prop: Property):
    """Sla observatie op in pand_geschiedenis als er iets wezenlijk veranderd is.
    Wordt voor élk gescrapet pand aangeroepen (niet alleen kansen). Dit voedt
    motion signal detectie: prijs-, makelaar- en status-mutaties door de tijd."""
    if not prop.url:
        return
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute("""
            SELECT prijs, makelaar, status, type_woning
            FROM pand_geschiedenis
            WHERE url = ?
            ORDER BY id DESC LIMIT 1
        """, (prop.url,)).fetchone()

        huidige = (
            prop.prijs or None,
            (prop.makelaar or "").strip() or None,
            (prop.status_tekst or "").strip() or None,
            (prop.type_woning or "").strip() or None,
        )
        if row is None or tuple(row) != huidige:
            conn.execute("""
                INSERT INTO pand_geschiedenis (url, ts, prijs, makelaar, status, type_woning)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (prop.url, now, *huidige))
            conn.commit()
    finally:
        conn.close()


def _dagen_verschil(iso_ts: str, nu: datetime) -> int:
    try:
        return (nu - datetime.fromisoformat(iso_ts)).days
    except Exception:
        return 0


def get_motion(url: str) -> dict:
    """Bereken motion signalen voor een pand op basis van pand_geschiedenis.
    Retourneert dict met dagen_online, prijs_historie, prijsverlaging_pct,
    aantal_prijsverlagingen, makelaarswissel, onder_bod_terug, motivated_score."""
    if not url:
        return {}
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute("""
            SELECT ts, prijs, makelaar, status, type_woning
            FROM pand_geschiedenis
            WHERE url = ?
            ORDER BY id ASC
        """, (url,)).fetchall()
    finally:
        conn.close()

    if not rows:
        return {}

    nu = datetime.now()
    eerste_ts = rows[0][0]
    laatste_ts = rows[-1][0]
    dagen_online = _dagen_verschil(eerste_ts, nu)

    # ── Prijs historie (alleen wijzigingen) ──
    prijs_historie = []
    vorige_prijs = None
    for ts, prijs, _mak, _stat, _tw in rows:
        if prijs and prijs != vorige_prijs:
            prijs_historie.append({"ts": ts, "prijs": int(prijs)})
            vorige_prijs = prijs

    prijzen = [p["prijs"] for p in prijs_historie]
    eerste_prijs = prijzen[0] if prijzen else 0
    huidige_prijs = prijzen[-1] if prijzen else 0
    prijsverlaging_euro = max(0, eerste_prijs - huidige_prijs) if prijzen else 0
    prijsverlaging_pct = (
        round(prijsverlaging_euro / eerste_prijs * 100, 1)
        if eerste_prijs > 0 else 0.0
    )
    # Aantal verlagingen = afgenomen stappen
    aantal_verlagingen = sum(
        1 for a, b in zip(prijzen, prijzen[1:]) if b < a
    )

    # ── Makelaarswissel binnen configureerbaar window ──
    drempel_mak = nu - timedelta(days=SIGNALEN["makelaarswissel_dagen"])
    mak_in_window = {
        mak for ts, _p, mak, _s, _tw in rows
        if mak and datetime.fromisoformat(ts) >= drempel_mak
    }
    makelaarswissel = len(mak_in_window) >= 2

    # ── Onder-bod-terug detectie ──
    statussen = [(ts, (stat or "").lower()) for ts, _p, _m, stat, _tw in rows]
    type_woningen = [(ts, (tw or "").lower()) for ts, _p, _m, _s, tw in rows]
    onder_bod_keywords = ("onder bod", "onder optie", "in onderhandeling", "onder bieding")
    zag_onder_bod = any(
        any(kw in s for kw in onder_bod_keywords)
        for _ts, s in statussen + type_woningen
    )
    laatste_status = (statussen[-1][1] if statussen else "")
    laatste_type = (type_woningen[-1][1] if type_woningen else "")
    nu_beschikbaar = not any(
        kw in (laatste_status + " " + laatste_type) for kw in onder_bod_keywords
    )
    onder_bod_terug = zag_onder_bod and nu_beschikbaar

    # ── Motivated score (0-10) ──
    score = 0
    if prijsverlaging_pct >= SIGNALEN["prijsverlaging_sterk_pct"]:
        score += 3
    elif prijsverlaging_pct >= 3.0:
        score += 2
    elif prijsverlaging_pct >= SIGNALEN["prijsverlaging_min_pct"]:
        score += 1

    if aantal_verlagingen >= 2:
        score += 1

    if dagen_online >= SIGNALEN["motivated_dagen_zeer_lang"]:
        score += 4
    elif dagen_online >= SIGNALEN["motivated_dagen_lang"]:
        score += 3
    elif dagen_online >= SIGNALEN["motivated_dagen_online"]:
        score += 2

    if makelaarswissel:
        score += 2
    if onder_bod_terug:
        score += 3

    score = min(score, 10)

    return {
        "dagen_online": dagen_online,
        "eerste_gezien": eerste_ts,
        "laatste_gezien": laatste_ts,
        "prijs_historie": prijs_historie,
        "eerste_prijs": eerste_prijs,
        "huidige_prijs": huidige_prijs,
        "prijsverlaging_euro": prijsverlaging_euro,
        "prijsverlaging_pct": prijsverlaging_pct,
        "aantal_prijsverlagingen": aantal_verlagingen,
        "makelaarswissel": makelaarswissel,
        "makelaars_recent": sorted(mak_in_window),
        "onder_bod_terug": onder_bod_terug,
        "motivated_score": score,
        "motivated": score >= SIGNALEN["motivated_score_drempel"],
    }


def energielabel_cache_get(cache_key: str, max_age_dagen: int = 60) -> dict | None:
    """Haal gecachte EP-Online lookup op. Retourneert None als niet gevonden of te oud."""
    if not cache_key:
        return None
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute("""
            SELECT label, opnamedatum, geldig_tot, registratiedatum, pand_type,
                   bouwjaar, gebruiksoppervlakte, raw_json, gecached_op, gevonden
            FROM energielabel_cache WHERE cache_key = ?
        """, (cache_key,)).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    try:
        leeftijd = (datetime.now() - datetime.fromisoformat(row[8])).days
        if leeftijd > max_age_dagen:
            return None
    except Exception:
        return None
    return {
        "label": row[0], "opnamedatum": row[1], "geldig_tot": row[2],
        "registratiedatum": row[3], "pand_type": row[4], "bouwjaar": row[5],
        "gebruiksoppervlakte": row[6], "gevonden": bool(row[9]),
    }


def energielabel_cache_set(cache_key: str, data: dict | None):
    """Sla EP-Online lookup op in cache. None = niet gevonden (voorkomt herhaald vragen)."""
    if not cache_key:
        return
    import json
    now = datetime.now().isoformat()
    gevonden = 1 if data else 0
    d = data or {}
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("""
            INSERT INTO energielabel_cache
                (cache_key, label, opnamedatum, geldig_tot, registratiedatum,
                 pand_type, bouwjaar, gebruiksoppervlakte, raw_json, gecached_op, gevonden)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                label=excluded.label, opnamedatum=excluded.opnamedatum,
                geldig_tot=excluded.geldig_tot, registratiedatum=excluded.registratiedatum,
                pand_type=excluded.pand_type, bouwjaar=excluded.bouwjaar,
                gebruiksoppervlakte=excluded.gebruiksoppervlakte,
                raw_json=excluded.raw_json, gecached_op=excluded.gecached_op,
                gevonden=excluded.gevonden
        """, (
            cache_key, d.get("label"), d.get("opnamedatum"), d.get("geldig_tot"),
            d.get("registratiedatum"), d.get("pand_type"), d.get("bouwjaar"),
            d.get("gebruiksoppervlakte"),
            json.dumps(d) if d else None, now, gevonden,
        ))
        conn.commit()
    finally:
        conn.close()


def haal_stats_op() -> dict:
    conn = sqlite3.connect(DB_PATH)
    total = conn.execute("SELECT COUNT(*) FROM panden").fetchone()[0]
    vandaag = conn.execute(
        "SELECT COUNT(*) FROM panden WHERE DATE(eerste_gezien) = DATE('now')"
    ).fetchone()[0]
    conn.close()
    return {"totaal": total, "vandaag": vandaag}
