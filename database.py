"""
SQLite database voor het bijhouden van geziene panden.
"""
import sqlite3
import logging
from datetime import datetime
from models import Property
from config import DB_PATH

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


def haal_stats_op() -> dict:
    conn = sqlite3.connect(DB_PATH)
    total = conn.execute("SELECT COUNT(*) FROM panden").fetchone()[0]
    vandaag = conn.execute(
        "SELECT COUNT(*) FROM panden WHERE DATE(eerste_gezien) = DATE('now')"
    ).fetchone()[0]
    conn.close()
    return {"totaal": total, "vandaag": vandaag}
