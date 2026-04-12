"""
Hoofdorchestrator — voert alle scrapers uit en filtert kansen.
"""
import logging
from typing import List
from models import (
    Property,
    bereken_fix_flip,
    bereken_splitsing,
    bereken_transformatie,
    score_property,
)
from database import init_db, is_nieuw, sla_op, haal_stats_op
from notifier import stuur_property_notificatie, stuur_dagelijks_rapport
from scrapers import scrape_funda, scrape_funda_ib, scrape_pararius, scrape_bedrijfspand, scrape_makelaars
from referentie import zoek_vergelijkbare
from config import FIX_FLIP, SPLITSING, TRANSFORMATIE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def evalueer_property(prop: Property) -> List[Property]:
    """Bereken alle strategieen voor een pand en retourneer degene die kansen bieden."""
    kansen = []

    # Zoek referentieprijzen in dezelfde stad
    ref_pm2, ref_panden = zoek_vergelijkbare(prop.stad, prop.opp_m2, "fix_flip")

    if not prop.is_commercieel:
        # Fix & Flip
        if (prop.prijs <= FIX_FLIP["max_aankoopprijs"]
                and prop.opp_m2 >= FIX_FLIP["min_opp_m2"]):
            p = bereken_fix_flip(
                Property(**prop.__dict__), FIX_FLIP,
                verkoop_m2_override=ref_pm2,
                referenties=ref_panden,
            )
            if p.marge_pct >= FIX_FLIP["min_marge_pct"]:
                score_property(p)
                kansen.append(p)

        # Splitsing (als pand groot genoeg is)
        if (prop.opp_m2 >= SPLITSING["min_opp_m2"]
                and prop.prijs <= SPLITSING["max_aankoopprijs"]):
            n_units = 3 if prop.opp_m2 >= 220 else 2
            p = bereken_splitsing(
                Property(**prop.__dict__), SPLITSING, n_units,
                verkoop_m2_override=ref_pm2,
                referenties=ref_panden,
            )
            if p.marge_pct >= SPLITSING["min_marge_pct"]:
                score_property(p)
                kansen.append(p)

    else:
        # Transformatie
        if (prop.prijs <= TRANSFORMATIE["max_aankoopprijs"]
                and prop.opp_m2 >= TRANSFORMATIE["min_opp_m2"]):
            if prop.opp_m2 > 0 and (prop.prijs / prop.opp_m2) <= TRANSFORMATIE["max_prijs_per_m2"]:
                p = bereken_transformatie(
                    Property(**prop.__dict__), TRANSFORMATIE,
                    verkoop_m2_override=ref_pm2,
                    referenties=ref_panden,
                )
                if p.marge_pct >= TRANSFORMATIE["min_marge_pct"]:
                    score_property(p)
                    kansen.append(p)

    return kansen


def run_scan():
    logger.info("=== PANDEN SCANNER GESTART ===")
    init_db()

    # ── Scrapers uitvoeren ────────────────────────────────────────────────
    alle_panden: List[Property] = []

    try:
        alle_panden += scrape_funda(max_pages=3)
    except Exception as e:
        logger.error("Funda scraper gefaald: %s", e)

    try:
        alle_panden += scrape_pararius(max_pages=2)
    except Exception as e:
        logger.error("Pararius scraper gefaald: %s", e)

    try:
        alle_panden += scrape_funda_ib(max_pages=2)
    except Exception as e:
        logger.error("FiB scraper gefaald: %s", e)

    try:
        alle_panden += scrape_bedrijfspand()
    except Exception as e:
        logger.error("Bedrijfspand scraper gefaald: %s", e)

    try:
        alle_panden += scrape_makelaars()
    except Exception as e:
        logger.error("Makelaars scraper gefaald: %s", e)

    totaal_ruw = len(alle_panden)
    logger.info("Totaal gescand: %d panden", totaal_ruw)

    # ── Sanity filter: verwijder onzin-data ──────────────────────────────
    alle_panden = [
        p for p in alle_panden
        if p.prijs >= 25_000         # geen huurprijzen of parse-fouten
        and p.opp_m2 >= 10           # minimaal 10m²
        and p.prijs_per_m2 >= 500    # minimaal €500/m² (anders is het geen koop)
        and p.url                    # moet een URL hebben
    ]
    logger.info("Na sanity filter: %d panden (van %d gescand)", len(alle_panden), totaal_ruw)

    # ── Evalueer en filter ────────────────────────────────────────────────
    nieuw_gevonden = 0
    for prop in alle_panden:
        if not is_nieuw(prop.url):
            continue  # al eerder gezien

        kansen = evalueer_property(prop)
        for kans in kansen:
            sla_op(kans)
            logger.info(
                "KANS: %s | %s | marge %.1f%% | winst EUR%d",
                kans.adres, kans.strategie, kans.marge_pct, kans.winst_euro,
            )
            stuur_property_notificatie(kans)
            nieuw_gevonden += 1

        # Sla alle geziene panden op (ook als geen kans, om duplicaten te voorkomen)
        if not kansen:
            sla_op(prop)

    # ── Dagelijks rapport ─────────────────────────────────────────────────
    stats = haal_stats_op()
    stuur_dagelijks_rapport(
        nieuw=nieuw_gevonden,
        totaal=stats["totaal"],
        gezien=len(alle_panden),
    )
    logger.info("=== SCAN KLAAR — %d nieuwe kansen ===", nieuw_gevonden)


if __name__ == "__main__":
    run_scan()
