"""
Hoofdorchestrator — voert alle scrapers uit en filtert kansen.
"""
import logging
import re
import time
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
from renovatie import schat_renovatie
from config import FIX_FLIP, SPLITSING, TRANSFORMATIE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Funda instance voor status checks
_funda = None

def _get_funda():
    global _funda
    if _funda is None:
        from funda import Funda
        _funda = Funda()
    return _funda


VERKOCHT_KEYWORDS = [
    "verkocht", "sold", "onder bod", "onder optie", "in onderhandeling",
    "niet beschikbaar", "unavailable", "voorbehoud",
]


def _check_url_verkocht(url: str) -> bool:
    """Fetch de listing URL en check of er 'verkocht' op de pagina staat.
    Returns True als het pand VERKOCHT is."""
    if not url:
        return False
    try:
        import requests as req
        r = req.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept-Language": "nl-NL,nl;q=0.9",
        }, timeout=10, allow_redirects=True)
        if r.status_code != 200:
            return False  # pagina laadt niet, kan niet checken
        tekst = r.text.lower()
        for kw in VERKOCHT_KEYWORDS:
            # Check in relevante HTML elementen (niet in footer/nav)
            # Zoek naar het keyword in de buurt van prijs/status elementen
            if f'class="status">{kw}' in tekst:
                return True
            if f'class="label">{kw}' in tekst:
                return True
            if f'"status":"{kw}"' in tekst:
                return True
            if f'verkocht' in tekst and ('onder voorbehoud' in tekst or 'status' in tekst):
                # Generieke check: als "verkocht" EN "status" of "voorbehoud" op de pagina
                import re as _re
                # Check of "verkocht" voorkomt in een status/label context
                if _re.search(r'(?:status|label|badge|tag)[^>]*>.*?verkocht', tekst):
                    return True
                if _re.search(r'verkocht\s*(onder\s*voorbehoud)?', tekst[:5000]):
                    # In de eerste 5000 chars (boven de fold) = waarschijnlijk status
                    return True
        return False
    except Exception:
        return False  # bij fout: niet blokkeren


def _check_funda_api(prop: Property) -> bool:
    """Check Funda detail API voor status. Returns True als beschikbaar."""
    try:
        url = prop.url
        match = re.search(r'/(\d+)/?$', url)
        if not match:
            match = re.search(r'-(\d+)/', url)
        if not match:
            return True

        f = _get_funda()
        detail = f.get_listing(int(match.group(1)))
        d = detail.data if hasattr(detail, 'data') else {}
        status = str(d.get("status", "")).lower().strip()

        if status != "available":
            logger.info("SKIP %s — Funda status: %s", prop.adres, status)
            return False

        if d.get("is_fixer_upper"):
            prop.calc["is_opknapper"] = True
        if d.get("price_per_m2"):
            prop.calc["funda_prijs_per_m2"] = d["price_per_m2"]

        time.sleep(0.2)
        return True
    except Exception as e:
        logger.debug("Funda API check mislukt voor %s: %s", prop.adres, e)
        return True


def is_beschikbaar(prop: Property) -> bool:
    """Check of een pand nog te koop is. Twee checks:
    1. Funda API (voor Funda-panden)
    2. Listing URL ophalen en checken op 'verkocht' tekst (voor alles)
    """
    # Tekst-check in bestaande data
    if hasattr(prop, 'type_woning') and prop.type_woning:
        if any(kw in prop.type_woning.lower() for kw in VERKOCHT_KEYWORDS):
            logger.info("SKIP %s — verkocht in type_woning", prop.adres)
            return False

    # Check 1: Funda API (voor Funda-bron panden)
    if prop.source in ("funda", "funda_ib"):
        if not _check_funda_api(prop):
            return False

    # Check 2: Haal de listing URL op en zoek naar "verkocht" op de pagina
    if prop.url and _check_url_verkocht(prop.url):
        logger.info("SKIP %s — 'verkocht' gevonden op pagina %s", prop.adres, prop.url[:60])
        return False

    return True


def evalueer_property(prop: Property) -> List[Property]:
    """Bereken alle strategieen voor een pand en retourneer degene die kansen bieden."""
    kansen = []

    # Zoek referentieprijzen in dezelfde stad
    ref_pm2, ref_panden = zoek_vergelijkbare(prop.stad, prop.opp_m2, "fix_flip")

    # Slimme renovatie-schatting op basis van pandkenmerken
    is_opknapper = prop.calc.get("is_opknapper", False) if prop.calc else False
    reno = schat_renovatie(
        opp_m2=prop.opp_m2,
        bouwjaar=prop.bouwjaar,
        energie_label=prop.energie_label,
        type_woning=prop.type_woning,
        is_opknapper=is_opknapper,
    )

    if not prop.is_commercieel:
        # Fix & Flip
        if (prop.prijs <= FIX_FLIP["max_aankoopprijs"]
                and prop.opp_m2 >= FIX_FLIP["min_opp_m2"]):
            p = bereken_fix_flip(
                Property(**prop.__dict__), FIX_FLIP,
                verkoop_m2_override=ref_pm2,
                referenties=ref_panden,
                renovatie_detail=reno,
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
            # Check of pand nog beschikbaar is (niet verkocht)
            if not is_beschikbaar(kans):
                logger.info("OVERGESLAGEN (verkocht): %s", kans.adres)
                sla_op(kans)  # sla op zodat we 'm niet opnieuw checken
                continue

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
