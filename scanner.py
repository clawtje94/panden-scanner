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
from scrapers import (
    scrape_funda, scrape_funda_ib, scrape_pararius,
    scrape_bedrijfspand, scrape_makelaars,
    scrape_trovit, scrape_biedboek,
)
from referentie import zoek_vergelijkbare
from renovatie import schat_renovatie
from validatie import valideer_verkoopprijs
from bestemmingsplan import mag_splitsen, mag_opbouwen
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
    "niet beschikbaar", "unavailable", "voorbehoud", "onder bieding",
    "bieden niet meer mogelijk", "already sold", "under offer",
    "sold subject to contract", "bid accepted",
]


def _parse_description(text: str) -> dict:
    """Extraheer gestructureerde data uit Funda beschrijving."""
    if not text:
        return {}
    result = {}
    lower = text.lower()

    # Erfpacht
    if "erfpacht" in lower:
        result["erfpacht"] = True
    elif "eigen grond" in lower:
        result["erfpacht"] = False

    # VvE bijdrage
    vve_match = re.search(r'v\.?v\.?e\.?[^€\d]{0,30}[€]\s*([\d.,]+)', lower)
    if not vve_match:
        vve_match = re.search(r'v\.?v\.?e\.?[^€\d]{0,30}([\d.,]+)\s*(?:euro|per maand|p/?m)', lower)
    if vve_match:
        try:
            result["vve_bijdrage"] = round(float(vve_match.group(1).replace(".", "").replace(",", ".")), 2)
        except ValueError:
            pass

    # Verdieping/bouwlaag
    verd_match = re.search(r'(\d+)e?\s*(?:verdieping|bouwlaag|etage|woonlaag)', lower)
    if verd_match:
        result["verdieping"] = int(verd_match.group(1))

    # Kelder/souterrain
    if "souterrain" in lower or "kelder" in lower:
        result["heeft_kelder"] = True

    # Zolder/vliering
    if "zolder" in lower or "vliering" in lower:
        result["heeft_zolder"] = True

    return result


_browser = None
_browser_context = None

def _get_browser():
    """Hergebruik 1 browser voor alle verkocht-checks."""
    global _browser, _browser_context
    if _browser is None:
        from playwright.sync_api import sync_playwright
        _pw = sync_playwright().start()
        _browser = _pw.chromium.launch(headless=True, args=["--no-sandbox"])
        _browser_context = _browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            locale="nl-NL",
        )
    return _browser_context


def _check_url_verkocht(url: str) -> bool:
    """Open de listing URL in een echte browser en check of er
    'verkocht' zichtbaar op de pagina staat. Returns True als VERKOCHT."""
    if not url:
        return False
    try:
        ctx = _get_browser()
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=15_000)
        time.sleep(1.5)  # wacht op JS rendering

        # Haal alle zichtbare tekst op (na JS rendering)
        body_text = page.inner_text("body").lower()
        page.close()

        # Check op verkocht-keywords in de zichtbare tekst
        for kw in VERKOCHT_KEYWORDS:
            if kw in body_text:
                return True
        return False
    except Exception as e:
        logger.debug("URL verkocht-check fout voor %s: %s", url[:60], e)
        return False


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

        # Fix de URL naar de juiste Funda link
        correct_url = d.get("url", "")
        if correct_url and correct_url.startswith("http"):
            prop.url = correct_url

        # Foto URLs uit detail API (eerste = hoofdfoto/gevel)
        photo_urls = d.get("photo_urls", [])
        if photo_urls:
            prop.foto_url = photo_urls[0]
            prop.calc["foto_urls"] = photo_urls[:6]

        # Plattegronden
        floorplan_urls = d.get("floorplan_urls", [])
        if floorplan_urls:
            prop.calc["plattegrond_urls"] = floorplan_urls

        # Voorzieningen
        for key in ("has_garden", "has_balcony", "has_roof_terrace",
                     "has_parking_on_site", "has_solar_panels",
                     "has_heat_pump", "is_monument"):
            val = d.get(key)
            if val is not None:
                prop.calc[key] = val

        # Bouwjaar verificatie
        detail_bj = d.get("construction_year")
        if detail_bj and isinstance(detail_bj, int) and prop.bouwjaar == 0:
            prop.bouwjaar = detail_bj

        # Perceeloppervlak
        if d.get("plot_area"):
            prop.calc["plot_area"] = int(d["plot_area"])

        # Beschrijving parsen: erfpacht, VvE, verdieping, etc
        description = d.get("description") or ""
        if description:
            parsed = _parse_description(description)
            if parsed:
                prop.calc["beschrijving_parsed"] = parsed
                if "erfpacht" in parsed:
                    prop.eigen_grond = not parsed["erfpacht"]
                    prop.calc["erfpacht"] = parsed["erfpacht"]
                if "vve_bijdrage" in parsed:
                    prop.calc["vve_bijdrage"] = parsed["vve_bijdrage"]
                if "verdieping" in parsed:
                    prop.calc["verdieping"] = parsed["verdieping"]

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
    ref_pm2, ref_panden = zoek_vergelijkbare(
        prop.stad, prop.opp_m2, "fix_flip",
        type_woning=prop.type_woning,
        postcode=prop.postcode,
    )

    # Slimme renovatie-schatting op basis van pandkenmerken
    is_opknapper = prop.calc.get("is_opknapper", False) if prop.calc else False
    reno = schat_renovatie(
        opp_m2=prop.opp_m2,
        bouwjaar=prop.bouwjaar,
        energie_label=prop.energie_label,
        type_woning=prop.type_woning,
        is_opknapper=is_opknapper,
    )

    # Splitsen/opbouwen mogelijkheden
    splitsen_info = mag_splitsen(prop.stad, prop.opp_m2)
    opbouwen_info = mag_opbouwen(prop.stad, prop.type_woning)

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
                # Voeg splitsen/opbouwen info toe
                p.calc["splitsen"] = splitsen_info
                p.calc["opbouwen"] = opbouwen_info
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

    # Trovit tijdelijk uit — aggregator data te ruw, dupliceert Funda
    # try:
    #     alle_panden += scrape_trovit(max_pages=3)
    # except Exception as e:
    #     logger.error("Trovit scraper gefaald: %s", e)

    # Biedboek: aparte lijst, geen standaard calc (veilingen)
    biedboek_panden = []
    try:
        biedboek_panden = scrape_biedboek()
        logger.info("Biedboek: %d panden (info-only, geen calc)", len(biedboek_panden))
    except Exception as e:
        logger.error("Biedboek scraper gefaald: %s", e)

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

    # ── Evalueer, valideer en filter ─────────────────────────────────────
    nieuw_gevonden = 0
    alle_kansen = []  # voor leads.json export
    validatie_skips = 0
    for prop in alle_panden:
        kansen = evalueer_property(prop)
        for kans in kansen:
            # Stap 1: Check of pand nog beschikbaar is (niet verkocht)
            if not is_beschikbaar(kans):
                logger.info("OVERGESLAGEN (verkocht): %s", kans.adres)
                sla_op(kans)
                continue

            # Stap 2: Valideer verkoopprijs tegen externe bronnen
            calc = kans.calc or {}
            verkoop_pm2 = calc.get("verkoop_m2", 0)
            bruto = calc.get("bruto_verkoopprijs", 0)
            funda_pm2 = calc.get("funda_prijs_per_m2", 0)

            # Validatie: log voor info maar blokkeer NIET
            # (Huispedia/WOZ geeft huidige waarde, niet na-renovatie waarde)
            if verkoop_pm2 > 0 and kans.opp_m2 > 0 and kans.postcode:
                try:
                    validatie = valideer_verkoopprijs(
                        onze_pm2=verkoop_pm2,
                        onze_bruto=bruto,
                        opp_m2=kans.opp_m2,
                        postcode=kans.postcode,
                        adres=kans.adres,
                        stad=kans.stad,
                        funda_pm2=funda_pm2,
                    )
                    kans.calc["validatie"] = validatie
                    if not validatie["goedgekeurd"]:
                        logger.info(
                            "VALIDATIE WAARSCHUWING %s: %s",
                            kans.adres, validatie["reden"],
                        )
                except Exception as e:
                    logger.debug("Validatie fout %s: %s", kans.adres, e)

            alle_kansen.append(kans)
            sla_op(kans)

            # Alleen Telegram notificatie voor NIEUWE kansen
            if is_nieuw(kans.url):
                logger.info(
                    "KANS NIEUW: %s | %s | marge %.1f%% | winst EUR%d",
                    kans.adres, kans.strategie, kans.marge_pct, kans.winst_euro,
                )
                stuur_property_notificatie(kans)
                nieuw_gevonden += 1

        if not kansen:
            sla_op(prop)

    if validatie_skips > 0:
        logger.info("Validatie: %d kansen afgekeurd (prijs te optimistisch)", validatie_skips)

    # ── Biedboek info-only toevoegen aan dashboard ────────────────────────
    biedboek_dashboard = []
    for bp in biedboek_panden:
        biedboek_dashboard.append({
            "adres": bp.adres, "stad": bp.stad, "postcode": bp.postcode,
            "prijs": bp.prijs, "opp_m2": bp.opp_m2, "prijs_per_m2": bp.prijs_per_m2,
            "type_woning": bp.type_woning, "url": bp.url,
            "source": "biedboek", "is_commercieel": bp.is_commercieel,
            "bouwjaar": bp.bouwjaar,
        })

    # ── Export naar leads.json voor dashboard ─────────────────────────────
    import json
    from datetime import datetime
    leads_export = {
        "scan_datum": datetime.now().isoformat(),
        "totaal_gescand": totaal_ruw,
        "na_filter": len(alle_panden),
        "kansen": [],
        "biedboek": biedboek_dashboard,
    }
    for k in alle_kansen:
        leads_export["kansen"].append({
            "adres": k.adres,
            "stad": k.stad,
            "postcode": k.postcode,
            "wijk": k.calc.get("referenties", [{}])[0].get("wijk", "") if k.calc.get("referenties") else "",
            "prijs": k.prijs,
            "opp_m2": k.opp_m2,
            "prijs_per_m2": k.prijs_per_m2,
            "type_woning": k.type_woning,
            "bouwjaar": k.bouwjaar,
            "energie_label": k.energie_label,
            "kamers": k.kamers,
            "source": k.source,
            "url": k.url,
            "foto_url": k.foto_url or "",
            "foto_urls": k.calc.get("foto_urls", [k.foto_url] if k.foto_url else []),
            "strategie": k.strategie,
            "marge_pct": k.marge_pct,
            "winst_euro": k.winst_euro,
            "roi_pct": k.roi_pct,
            "totale_kosten": k.totale_kosten,
            "verwachte_opbrengst": k.verwachte_opbrengst,
            "score": k.score,
            "is_opknapper": k.calc.get("is_opknapper", False),
            "calc": k.calc,
        })
    # Sorteer op marge (hoogste eerst)
    leads_export["kansen"].sort(key=lambda x: -x["marge_pct"])

    with open("leads.json", "w", encoding="utf-8") as f:
        json.dump(leads_export, f, indent=2, ensure_ascii=False, default=str)
    logger.info("leads.json geschreven: %d kansen + %d biedboek",
                len(leads_export["kansen"]), len(biedboek_dashboard))

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
