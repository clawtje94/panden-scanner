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
from database import init_db, is_nieuw, sla_op, haal_stats_op, registreer_observatie, get_motion
from notifier import stuur_property_notificatie, stuur_dagelijks_rapport
from scrapers.funda import scrape_funda
from scrapers.funda_ib import scrape_funda_ib
from scrapers.pararius import scrape_pararius
from scrapers.bedrijfspand import scrape_bedrijfspand
from scrapers.makelaars import scrape_makelaars
from scrapers.trovit import scrape_trovit
from scrapers.biedboek import scrape_biedboek
from scrapers.beleggingspanden import scrape_beleggingspanden
from scrapers.vastiva import scrape_vastiva
from scrapers.veilingen import scrape_veilingen
from scrapers.kavels import scrape_kavels
from scrapers.ep_online import verrijk_energielabel
from scrapers.bag import verrijk_bag
from scrapers.monument import verrijk_monument_status
from scrapers.cbs_buurt import get_gemeente_cijfers, wijk_kwaliteit_score
from classificatie import classificeer_property
from erfpacht import detect_erfpacht
from risks import aggregate_risks
from dealscore import bereken_dealscore
from bod_advies import genereer_bod_advies
from referentie import zoek_vergelijkbare_detail
from renovatie import schat_renovatie
from looptijd import bereken_looptijd
from validatie import valideer_verkoopprijs
from bestemmingsplan import mag_splitsen, mag_opbouwen
from config import FIX_FLIP, SPLITSING, TRANSFORMATIE, VERKOOP_KWALITEIT

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
        # Bewaar status op het property zodat pand_geschiedenis transities detecteert
        prop.status_tekst = status

        # Makelaar uit detail API voor makelaarswissel detectie
        agents = d.get("agents") or d.get("agent") or []
        if isinstance(agents, list) and agents:
            a = agents[0] if isinstance(agents[0], dict) else {}
            prop.makelaar = str(a.get("name") or a.get("title") or "").strip()
        elif isinstance(agents, dict):
            prop.makelaar = str(agents.get("name") or agents.get("title") or "").strip()

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
            # Bewaar raw beschrijving voor latere regex-parses (erfpacht, etc)
            prop.calc["beschrijving_raw"] = description[:2000]
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

    # EP-Online verrijking — officieel energielabel + forced_renovation flag.
    # Gebeurt vóór renovatie-schatting zodat het label in reno-input meegenomen
    # kan worden. Gecached in DB (60 dagen), dus veilig voor dagelijkse scan.
    ep_online_data = {}
    try:
        ep_online_data = verrijk_energielabel(prop)
    except Exception as e:
        logger.debug("EP-Online verrijking fout %s: %s", prop.adres, e)

    # Zoek referentieprijzen — rijke versie met P25/P50/P75 + confidence
    ref_detail = zoek_vergelijkbare_detail(
        prop.stad, prop.opp_m2,
        type_woning=prop.type_woning,
        postcode=prop.postcode,
    )
    ref_pm2 = ref_detail.get("p50_pm2") or 0
    ref_panden = ref_detail.get("top") or []

    # Slimme renovatie-schatting op basis van pandkenmerken
    is_opknapper = prop.calc.get("is_opknapper", False) if prop.calc else False
    reno = schat_renovatie(
        opp_m2=prop.opp_m2,
        bouwjaar=prop.bouwjaar,
        energie_label=prop.energie_label,
        type_woning=prop.type_woning,
        is_opknapper=is_opknapper,
        postcode=prop.postcode,
        stad=prop.stad,
    )

    # Dynamische looptijd — voed ook avg_days_online uit referentie-engine
    # terug voor realistische verkoop-duur per wijk.
    looptijd_info = bereken_looptijd(
        renovatie_per_m2=reno["per_m2"],
        opp_m2=prop.opp_m2,
        stad=prop.stad,
        type_woning=prop.type_woning,
        is_opknapper=is_opknapper,
        avg_days_online_wijk=ref_detail.get("avg_days_online"),
    )

    # Splitsen/opbouwen mogelijkheden — postcode meegeven voor wijk-checks
    # (Den Haag Leefbaarometer + parkeerdruk, Rotterdam NPRZ 85m²-regime).
    splitsen_info = mag_splitsen(prop.stad, prop.opp_m2, postcode=prop.postcode)
    opbouwen_info = mag_opbouwen(prop.stad, prop.type_woning)

    if not prop.is_commercieel:
        # Fix & Flip — gebruik dynamische looptijd
        cfg_dynamic = {**FIX_FLIP, "looptijd_maanden": looptijd_info["totaal_maanden"]}
        if (prop.prijs <= FIX_FLIP["max_aankoopprijs"]
                and prop.opp_m2 >= FIX_FLIP["min_opp_m2"]):
            p = bereken_fix_flip(
                Property(**prop.__dict__), cfg_dynamic,
                verkoop_m2_override=ref_pm2,
                referenties=ref_panden,
                renovatie_detail=reno,
                ref_detail=ref_detail,
            )
            if p.marge_pct >= FIX_FLIP["min_marge_pct"]:
                p.calc["splitsen"] = splitsen_info
                p.calc["opbouwen"] = opbouwen_info
                p.calc["looptijd_detail"] = looptijd_info
                if ep_online_data:
                    p.calc["ep_online"] = ep_online_data
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
                ref_detail=ref_detail,
            )
            if p.marge_pct >= SPLITSING["min_marge_pct"]:
                if ep_online_data:
                    p.calc["ep_online"] = ep_online_data
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
                    ref_detail=ref_detail,
                )
                if p.marge_pct >= TRANSFORMATIE["min_marge_pct"]:
                    if ep_online_data:
                        p.calc["ep_online"] = ep_online_data
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

    try:
        alle_panden += scrape_beleggingspanden()
    except Exception as e:
        logger.error("Beleggingspanden scraper gefaald: %s", e)

    try:
        alle_panden += scrape_vastiva()
    except Exception as e:
        logger.error("Vastiva scraper gefaald: %s", e)

    # ── Aparte categorieen (info-only, geen standaard calc) ──
    biedboek_panden = []
    try:
        biedboek_panden = scrape_biedboek()
        logger.info("Biedboek: %d panden (info-only)", len(biedboek_panden))
    except Exception as e:
        logger.error("Biedboek scraper gefaald: %s", e)

    veiling_panden = []
    try:
        veiling_panden = scrape_veilingen()
        logger.info("Veilingen: %d panden", len(veiling_panden))
    except Exception as e:
        logger.error("Veilingen scraper gefaald: %s", e)

    kavel_panden = []
    try:
        kavel_panden = scrape_kavels()
        logger.info("Kavels: %d kavels", len(kavel_panden))
    except Exception as e:
        logger.error("Kavels scraper gefaald: %s", e)

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

    # ── Classificatie filter: hallen/boten/kavels/verhuurd eruit ─────────
    # Developer-pipeline wil alleen wonen + transformatie-kandidaten.
    # Verhuurde panden, bedrijfshallen en beleggingsobjecten gaan naar aparte
    # categorieën, niet de ontwikkel-feed.
    beleggingen_export = []
    ontwikkel_panden = []
    audit = {"wonen": 0, "transformatie": 0, "verhuurd_wonen": 0, "skip": 0}
    skip_redenen = {}
    for p in alle_panden:
        klass = classificeer_property(p)
        p.calc = p.calc or {}
        p.calc["classificatie"] = klass
        audit[klass["category"]] = audit.get(klass["category"], 0) + 1

        if klass["category"] == "skip":
            for reden in klass.get("redenen", []):
                skip_redenen[reden] = skip_redenen.get(reden, 0) + 1
            logger.debug("FILTER skip: %s — %s", p.adres, "; ".join(klass["redenen"]))
            continue

        # Verhuurd pand = belegging, geen ontwikkeling. Apart bewaren.
        if klass["is_verhuurd"] or p.calc.get("is_belegging"):
            beleggingen_export.append(p)
            continue

        # Transformatie: alleen als scraper het expliciet commercieel markeerde
        # of als classificatie het als transformatie zag (kantoor/winkel).
        if klass["category"] == "transformatie":
            p.is_commercieel = True

        ontwikkel_panden.append(p)

    logger.info(
        "Na classificatie: %d ontwikkel-panden, %d beleggingen/verhuurd (van %d)",
        len(ontwikkel_panden), len(beleggingen_export), len(alle_panden),
    )
    # Top-5 skip redenen loggen voor inzicht
    top_skip = sorted(skip_redenen.items(), key=lambda x: -x[1])[:5]
    for reden, aantal in top_skip:
        logger.info("  skip reden: %d× '%s'", aantal, reden[:80])
    alle_panden = ontwikkel_panden
    classificatie_audit = {
        "per_category": audit,
        "top_skip_redenen": dict(top_skip),
        "totaal_voor_filter": len(alle_panden) + audit.get("skip", 0) + len(beleggingen_export),
    }

    # ── Observatie-historie registreren (voor motion signals) ────────────
    # Doen we voor élk gefilterd pand — ook panden die uiteindelijk geen kans
    # blijken, zodat we later bij her-opduiken prijsverlagingen kunnen zien.
    for prop in alle_panden:
        try:
            registreer_observatie(prop)
        except Exception as e:
            logger.debug("registreer_observatie fout %s: %s", prop.url[:60], e)

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

            # Motion signalen aanhaken (prijsverlaging, dagen online, etc)
            try:
                motion = get_motion(kans.url)
                if motion:
                    kans.calc["motion"] = motion
            except Exception as e:
                logger.debug("motion fout %s: %s", kans.adres, e)

            # BAG verificatie — officieel bouwjaar/oppervlak/gebruiksdoel
            try:
                bag_data = verrijk_bag(kans.postcode, kans.adres)
                if bag_data:
                    kans.calc["bag"] = {
                        "bouwjaar": bag_data.get("bouwjaar"),
                        "oppervlakte": bag_data.get("oppervlakte"),
                        "gebruiksdoel": bag_data.get("gebruiksdoel"),
                        "pandstatus": bag_data.get("pandstatus"),
                        "status": bag_data.get("status"),
                        "wijk": bag_data.get("wijk"),
                        "buurt": bag_data.get("buurt"),
                    }
                    # Hard filter: BAG zegt dat het een hal / industrie /
                    # sport / cel is — dan is dit geen woning, punt.
                    # Bateau wil geen ruis in de pipeline.
                    gd = (bag_data.get("gebruiksdoel") or "").lower()
                    if gd in ("industriefunctie", "sportfunctie", "celfunctie"):
                        logger.info(
                            "BAG-skip %s — gebruiksdoel=%s (geen woning)",
                            kans.adres, gd,
                        )
                        continue
            except Exception as e:
                logger.debug("BAG fout %s: %s", kans.adres, e)
                bag_data = {}

            # CBS buurt-data (gemeente-niveau) + wijk-kwaliteit-score
            try:
                cbs = get_gemeente_cijfers(kans.stad)
                if cbs:
                    kans.calc["cbs"] = cbs
                    kans.calc["wijk_kwaliteit"] = wijk_kwaliteit_score(cbs)
            except Exception as e:
                logger.debug("CBS fout %s: %s", kans.adres, e)

            # Monument check via RCE WFS (gebruikt BAG-coords als aanwezig)
            try:
                mon = verrijk_monument_status(kans, bag_data)
                if mon:
                    kans.calc["monument"] = mon
            except Exception as e:
                logger.debug("Monument fout %s: %s", kans.adres, e)
                mon = {}

            # Erfpacht detectie uit Funda-beschrijving (als beschikbaar)
            try:
                beschrijving = kans.calc.get("beschrijving_raw", "") or ""
                if not beschrijving and kans.calc.get("erfpacht") is not None:
                    # Minimale info uit _parse_description — stel kunstmatige zin op
                    beschrijving = "erfpacht" if kans.calc.get("erfpacht") else "eigen grond"
                erf = detect_erfpacht(beschrijving, kans.stad)
                if erf.get("is_erfpacht") or erf.get("toelichting"):
                    kans.calc["erfpacht_detail"] = erf
            except Exception as e:
                logger.debug("Erfpacht parse fout %s: %s", kans.adres, e)
                erf = {}

            # Risks aggregeren
            risks = aggregate_risks(
                classificatie=kans.calc.get("classificatie"),
                ep_online=kans.calc.get("ep_online"),
                bag=bag_data,
                monument=mon,
                erfpacht=erf,
                wijkcheck=kans.calc.get("splitsen", {}).get("wijkcheck"),
                motion=kans.calc.get("motion"),
                prop_bouwjaar=kans.bouwjaar,
                prop_opp_m2=kans.opp_m2,
            )
            kans.calc["risks"] = risks

            # Hard-skip als verkoop-data onbetrouwbaar is én worst-case
            # marge te krap — dat is geen deal, dat is gokken.
            vref = kans.calc.get("verkoop_referentie") or {}
            scen_worst = (kans.calc.get("scenarios") or {}).get("worst") or {}
            worst_marge = scen_worst.get("marge_pct", kans.marge_pct)
            if VERKOOP_KWALITEIT["skip_bij_onvoldoende_confidence"]:
                conf_lbl = vref.get("confidence_label", "onvoldoende")
                drempel = None
                if conf_lbl == "onvoldoende":
                    drempel = VERKOOP_KWALITEIT["min_worst_marge_bij_onvoldoende"]
                elif conf_lbl == "laag":
                    drempel = VERKOOP_KWALITEIT["min_worst_marge_bij_laag"]
                if drempel is not None and worst_marge < drempel:
                    logger.info(
                        "SKIP %s — verkoop-data %s, worst-marge %.1f%% < %.1f%%",
                        kans.adres, conf_lbl, worst_marge, drempel,
                    )
                    sla_op(kans)
                    continue

            # Altum AI — alleen voor top-deals om gratis-tier (50/mnd) te sparen.
            if kans.marge_pct >= 12 and kans.postcode and kans.adres:
                try:
                    from scrapers.altum import (
                        get_koopsom, get_modelwaarde, is_available,
                        inschat_eigenaarsduur,
                    )
                    from scrapers.bag import _parse_huisnummer
                    if is_available():
                        hn, hl, tv = _parse_huisnummer(kans.adres)
                        if hn:
                            koop = get_koopsom(kans.postcode, hn, tv)
                            mw = get_modelwaarde(kans.postcode, hn, tv)
                            eigen = inschat_eigenaarsduur(koop)
                            if koop or mw or eigen:
                                kans.calc["altum"] = {
                                    "koopsom": koop,
                                    "modelwaarde": mw,
                                    "eigenaarsduur": eigen,
                                }
                except Exception as e:
                    logger.debug("Altum fout %s: %s", kans.adres, e)

            # Dealscore — composite 0-100 voor triage.
            # Gebruikt WORST-case scenario (P25) om te voorkomen dat deals die
            # alleen bij gemiddelde verkoopprijs rendabel zijn hoog scoren.
            dscore = bereken_dealscore(
                marge_pct=kans.marge_pct,
                score_basis=kans.score,
                motion=kans.calc.get("motion"),
                ep_online=kans.calc.get("ep_online"),
                erfpacht=erf,
                risks=risks,
                wijkcheck=kans.calc.get("splitsen", {}).get("wijkcheck"),
                verkoop_referentie=kans.calc.get("verkoop_referentie"),
                scenarios=kans.calc.get("scenarios"),
            )
            kans.calc["dealscore"] = dscore

            # Bod-advies met onderhandelings-argumenten
            try:
                bod = genereer_bod_advies(
                    vraagprijs=kans.prijs,
                    calc=kans.calc,
                    motion=kans.calc.get("motion"),
                    risks=risks,
                    ep_online=kans.calc.get("ep_online"),
                    erfpacht=erf,
                    bag=bag_data,
                    opp_m2=kans.opp_m2,
                )
                kans.calc["bod_advies"] = bod
            except Exception as e:
                logger.debug("bod_advies fout %s: %s", kans.adres, e)

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

    # ── Veilingen + kavels naar dashboard format ────────────────────────
    def _prop_to_dict(p, source_override=None):
        return {
            "adres": p.adres, "stad": p.stad, "postcode": p.postcode,
            "prijs": p.prijs, "opp_m2": p.opp_m2, "prijs_per_m2": p.prijs_per_m2,
            "type_woning": p.type_woning, "url": p.url,
            "source": source_override or p.source,
            "bouwjaar": p.bouwjaar, "foto_url": p.foto_url or "",
            "calc": p.calc or {},
        }

    veilingen_dashboard = [_prop_to_dict(v) for v in veiling_panden]
    kavels_dashboard = [_prop_to_dict(k) for k in kavel_panden]

    # ── Export naar leads.json voor dashboard ─────────────────────────────
    import json
    from datetime import datetime
    # Beleggingen/verhuurd naar eigen categorie in leads.json
    beleggingen_dashboard = []
    for p in beleggingen_export:
        beleggingen_dashboard.append({
            "adres": p.adres, "stad": p.stad, "postcode": p.postcode,
            "prijs": p.prijs, "opp_m2": p.opp_m2,
            "prijs_per_m2": p.prijs_per_m2,
            "type_woning": p.type_woning, "url": p.url,
            "source": p.source,
            "foto_url": p.foto_url or "",
            "bouwjaar": p.bouwjaar,
            "is_commercieel": p.is_commercieel,
            "makelaar": p.makelaar,
            "huursom_jaar": (p.calc or {}).get("huursom_jaar", 0),
            "factor": (p.calc or {}).get("factor", 0),
            "bar_pct": (p.calc or {}).get("bar_pct", 0),
            "is_verhuurd": (p.calc or {}).get("is_verhuurd", False),
            "calc": p.calc or {},
        })

    leads_export = {
        "scan_datum": datetime.now().isoformat(),
        "totaal_gescand": totaal_ruw,
        "na_filter": len(alle_panden),
        "classificatie_audit": classificatie_audit,
        "kansen": [],
        "biedboek": biedboek_dashboard,
        "veilingen": veilingen_dashboard,
        "kavels": kavels_dashboard,
        "beleggingen": beleggingen_dashboard,
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
            "motion": k.calc.get("motion", {}),
            "ep_online": k.calc.get("ep_online", {}),
            "bag": k.calc.get("bag", {}),
            "monument": k.calc.get("monument", {}),
            "erfpacht_detail": k.calc.get("erfpacht_detail", {}),
            "risks": k.calc.get("risks", {}),
            "dealscore": k.calc.get("dealscore", {}),
            "scenarios": k.calc.get("scenarios", {}),
            "verkoop_referentie": k.calc.get("verkoop_referentie", {}),
            "bod_advies": k.calc.get("bod_advies", {}),
            "calc": k.calc,
        })
    # Sorteer op dealscore (hoogste eerst), fallback marge
    leads_export["kansen"].sort(
        key=lambda x: (
            -(x.get("dealscore", {}).get("score", 0)),
            -x["marge_pct"],
        )
    )

    with open("leads.json", "w", encoding="utf-8") as f:
        json.dump(leads_export, f, indent=2, ensure_ascii=False, default=str)
    logger.info(
        "leads.json geschreven: %d kansen + %d biedboek + %d veilingen + %d kavels + %d beleggingen",
        len(leads_export["kansen"]), len(biedboek_dashboard),
        len(veilingen_dashboard), len(kavels_dashboard),
        len(beleggingen_dashboard),
    )

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
