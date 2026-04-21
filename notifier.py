"""
Telegram notificaties met volledige businesscase.
"""
import logging
import requests
from models import Property
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)


def _eur(bedrag: int) -> str:
    """Format als euro bedrag."""
    return f"\u20ac{bedrag:,.0f}".replace(",", ".")


def stuur_telegram(tekst: str) -> bool:
    if TELEGRAM_TOKEN == "VERVANG_MET_JOUW_BOT_TOKEN":
        logger.warning("Telegram niet geconfigureerd.")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    resp = requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": tekst,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }, timeout=10)
    if not resp.ok:
        logger.error("Telegram fout: %s", resp.text)
    return resp.ok


def stuur_property_notificatie(prop: Property) -> bool:
    c = prop.calc
    if not c:
        return False

    strat_key = prop.strategie.split("_")[0]
    strat_labels = {
        "fix": "FIX & FLIP",
        "splitsing": "SPLITSING",
        "transformatie": "TRANSFORMATIE",
    }
    strat_label = strat_labels.get(strat_key, prop.strategie.upper())

    sterren = "\u2b50" * prop.score

    # ── Header met dealscore (als beschikbaar) ──
    ds = c.get("dealscore") or {}
    if ds.get("grade"):
        tekst = f"<b>[{ds['grade']}] {ds['score']}/100 — {strat_label}</b>\n"
    else:
        tekst = f"<b>{strat_label}</b>\n"
    tekst += f"{'=' * 32}\n\n"

    # ── Pand info ──
    tekst += f"<b>{prop.adres}</b>\n"
    tekst += f"{prop.stad}"
    if prop.postcode:
        tekst += f" | {prop.postcode}"
    tekst += "\n"
    if prop.opp_m2:
        tekst += f"{prop.opp_m2} m\u00b2"
    if prop.kamers:
        tekst += f" | {prop.kamers} kamers"
    if prop.bouwjaar:
        tekst += f" | bj {prop.bouwjaar}"
    if prop.energie_label:
        tekst += f" | label {prop.energie_label}"
    tekst += f"\nBron: {prop.source}"
    if c.get("is_opknapper"):
        tekst += " | OPKNAPPER"
    if c.get("funda_prijs_per_m2"):
        try:
            fpm2 = int(float(str(c['funda_prijs_per_m2']).replace('.', '').replace(',', '').replace('\u20ac', '').strip()))
            tekst += f" | Funda: {_eur(fpm2)}/m\u00b2"
        except (ValueError, TypeError):
            pass
    tekst += "\n"

    # ── AANKOOP ──
    tekst += f"\n<b>AANKOOP</b>\n"
    tekst += f"{'─' * 32}\n"
    tekst += f"Vraagprijs:      {_eur(c['vraagprijs'])}\n"
    tekst += f"OVB {c['ovb_pct']}%:          {_eur(c['ovb'])}\n"
    tekst += f"Notaris+makelaar: {_eur(c['notaris_makelaar_aankoop'])}\n"
    tekst += f"<b>Totaal aankoop:  {_eur(c['aankoop_totaal'])}</b>\n"

    # ── VERBOUWING ──
    tekst += f"\n<b>VERBOUWING ({_eur(c['renovatie_per_m2'])}/m\u00b2)</b>\n"
    tekst += f"{'─' * 32}\n"

    reno = c.get("renovatie_detail")
    if reno and reno.get("componenten"):
        # Slimme renovatie — toon top componenten
        comps = reno["componenten"]
        for comp in comps:
            if comp["kosten"] >= 1_000:  # toon alleen posten >= 1k
                tekst += f"{comp['naam']}: {_eur(comp['kosten'])}\n"
    else:
        # Flat rate fallback
        tekst += f"Renovatie: {_eur(c.get('renovatie', c['bouw_totaal']))}\n"
        if "splitsing_kosten" in c:
            tekst += f"Splitsing ({c['n_units']}x): {_eur(c['splitsing_kosten'])}\n"

    tekst += f"<b>Totaal bouw:     {_eur(c['bouw_totaal'])}</b>\n"

    # ── FINANCIERING ──
    tekst += f"\n<b>FINANCIERING</b>\n"
    tekst += f"{'─' * 32}\n"
    tekst += f"Looptijd:         {c['looptijd_maanden']} maanden\n"
    tekst += f"Rente:            {c['rente_pct']}% over {_eur(c['financiering_basis'])}\n"
    tekst += f"<b>Rentekosten:     {_eur(c['rente'])}</b>\n"

    # ── TOTAAL INVESTERING ──
    tekst += f"\n<b>TOTAAL INVESTERING: {_eur(c['totaal_kosten'])}</b>\n"

    # ── VERKOOP ──
    tekst += f"\n<b>VERKOOP NA RENOVATIE</b>\n"
    tekst += f"{'─' * 32}\n"

    if "n_units" in c and c.get("n_units", 1) > 1:
        tekst += f"Aantal units:     {c['n_units']}x\n"
        tekst += f"GBO per unit:     {c.get('gbo_per_unit', 0)} m\u00b2\n"
        tekst += f"GBO totaal:       {c.get('gbo_totaal', 0)} m\u00b2\n"

    verkoop_bron = c.get("verkoop_bron", "config")
    verkoop_m2 = c["verkoop_m2"]
    if verkoop_bron == "referentie":
        tekst += f"Verkoopprijs/m\u00b2: <b>{_eur(verkoop_m2)}</b>\n"
        # Toon welk type vergeleken is
        refs = c.get("referenties", [])
        if refs:
            ref_type = refs[0].get("type", "")
            type_nl = "appartementen" if ref_type == "apartment" else "huizen" if ref_type == "house" else "panden"
            tekst += f"  (gem. vergelijkbare {type_nl})\n"
        else:
            tekst += f"  (gem. vergelijkbare panden)\n"
    else:
        tekst += f"Verkoopprijs/m\u00b2: {_eur(verkoop_m2)} (standaard)\n"

    tekst += f"Bruto verkoop:    {_eur(c['bruto_verkoopprijs'])}\n"
    tekst += f"Makelaar 1.5%:    -{_eur(c['makelaar_verkoop'])}\n"
    tekst += f"Notaris:          -{_eur(c['notaris_verkoop'])}\n"
    tekst += f"<b>Netto opbrengst: {_eur(c['netto_opbrengst'])}</b>\n"

    # ── REFERENTIE PANDEN ──
    refs = c.get("referenties", [])
    if refs:
        wijk = refs[0].get("wijk", "")
        tekst += f"\n<b>REFERENTIE PANDEN</b>\n"
        tekst += f"{'─' * 32}\n"
        if wijk:
            tekst += f"(wijk: {wijk})\n"
        tekst += f"(basis voor {_eur(verkoop_m2)}/m\u00b2)\n"
        for i, ref in enumerate(refs[:5], 1):
            tekst += (
                f"{i}. {ref['adres']}\n"
                f"   {_eur(ref['prijs'])} | {ref['opp_m2']}m\u00b2 | "
                f"{_eur(ref['prijs_per_m2'])}/m\u00b2 | label {ref['energie_label']}\n"
            )
    else:
        tekst += f"\n<i>Geen vergelijkbare panden gevonden\n"
        tekst += f"Verkoopprijs is standaard schatting</i>\n"

    # ── RESULTAAT ──
    tekst += f"\n<b>RESULTAAT OP VRAAGPRIJS</b>\n"
    tekst += f"{'=' * 32}\n"
    tekst += f"Winst:  <b>{_eur(c['winst'])}</b>\n"
    tekst += f"Marge:  <b>{c['marge_pct']}%</b>\n"
    tekst += f"ROI:    <b>{c['roi_pct']}%</b>\n"

    # ── BOD SCENARIO ──
    tekst += f"\n<b>BIJ BOD VAN {_eur(c['bod'])} (-{c['bod_korting_pct']}%)</b>\n"
    tekst += f"{'=' * 32}\n"
    tekst += f"Investering: {_eur(c['bod_totaal_investering'])}\n"
    tekst += f"Winst:  <b>{_eur(c['bod_winst'])}</b>\n"
    tekst += f"Marge:  <b>{c['bod_marge_pct']}%</b>\n"

    # ── Verkoop scenarios + confidence ──
    scen = c.get("scenarios") or {}
    vref = c.get("verkoop_referentie") or {}
    if scen.get("realistic"):
        tekst += f"\n<b>VERKOOP SCENARIOS</b>\n"
        tekst += f"{'─' * 32}\n"
        w = scen.get("worst", {})
        r = scen.get("realistic", {})
        b = scen.get("best", {})
        tekst += f"Worst  (P25): {_eur(w.get('verkoop_m2', 0))}/m² | marge {w.get('marge_pct', 0)}% | winst {_eur(w.get('winst', 0))}\n"
        tekst += f"Real   (P50): {_eur(r.get('verkoop_m2', 0))}/m² | marge {r.get('marge_pct', 0)}% | winst {_eur(r.get('winst', 0))}\n"
        tekst += f"Best   (P75): {_eur(b.get('verkoop_m2', 0))}/m² | marge {b.get('marge_pct', 0)}% | winst {_eur(b.get('winst', 0))}\n"
        if vref:
            conf = vref.get("confidence", 0)
            lbl = vref.get("confidence_label", "?")
            n = vref.get("n_refs", 0)
            match = vref.get("match_niveau", "?")
            tekst += f"\n<i>Confidence {lbl} ({conf}/100) · N={n} · {match}</i>\n"
            for w in (vref.get("waarschuwingen") or [])[:3]:
                tekst += f"⚠ {w}\n"

    # ── Risico-profiel ──
    risks = c.get("risks") or {}
    if risks.get("aantal", 0) > 0 or risks.get("kansen"):
        tekst += f"\n<b>RISICO-PROFIEL</b>\n"
        tekst += f"{'─' * 32}\n"
        niveau_icon = {"rood": "🚫", "oranje": "⚠️", "geel": "⚡"}
        for f in risks.get("flags", []):
            ic = niveau_icon.get(f["niveau"], "•")
            tekst += f"{ic} {f['label']}\n"
        kansen = risks.get("kansen") or []
        if kansen:
            tekst += "\n<i>Kansen:</i>\n"
            for k in kansen:
                tekst += f"✓ {k['label']}\n"

    # ── EP-Online officieel energielabel ──
    ep = c.get("ep_online") or {}
    if ep.get("label"):
        tekst += f"\n<b>EP-ONLINE (RVO)</b>\n"
        tekst += f"{'─' * 32}\n"
        tekst += f"Label: {ep['label']}"
        if ep.get("forced_renovation"):
            tekst += " — FORCED RENOVATION"
        if ep.get("forced_renovation_sterk"):
            tekst += " (sterk)"
        tekst += "\n"
        if ep.get("bouwjaar"):
            tekst += f"Bouwjaar (EP): {ep['bouwjaar']}\n"
        if ep.get("geldig_tot"):
            tekst += f"Label geldig tot: {str(ep['geldig_tot'])[:10]}\n"

    # ── Motion signalen (motivated seller) ──
    m = c.get("motion") or {}
    if m:
        signalen = []
        if m.get("prijsverlaging_pct", 0) >= 1.0:
            signalen.append(
                f"Prijs {m['prijsverlaging_pct']}% verlaagd "
                f"(-{_eur(m['prijsverlaging_euro'])})"
            )
        if m.get("aantal_prijsverlagingen", 0) >= 2:
            signalen.append(f"{m['aantal_prijsverlagingen']}x verlaagd")
        if m.get("dagen_online", 0) >= 120:
            signalen.append(f"{m['dagen_online']} dagen online")
        if m.get("makelaarswissel"):
            signalen.append("Makelaarswissel")
        if m.get("onder_bod_terug"):
            signalen.append("Onder bod → terug te koop")
        if signalen:
            label = "MOTIVATED SELLER" if m.get("motivated") else "Motion signalen"
            tekst += f"\n<b>{label}</b>\n"
            tekst += f"{'─' * 32}\n"
            for s in signalen:
                tekst += f"• {s}\n"

    # ── Score + link ──
    tekst += f"\nScore: {sterren} ({prop.score}/10)\n"
    tekst += f"\n<a href='{prop.url}'>Bekijk pand</a>"

    return stuur_telegram(tekst)


def stuur_dagelijks_rapport(nieuw: int, totaal: int, gezien: int):
    import datetime
    tekst = (
        f"<b>DAGELIJKS SCAN RAPPORT</b>\n"
        f"{'=' * 32}\n"
        f"Nieuwe kansen: <b>{nieuw}</b>\n"
        f"Panden gescand: {gezien}\n"
        f"Totaal in database: {totaal}\n"
        f"{datetime.date.today().strftime('%d-%m-%Y')}"
    )
    stuur_telegram(tekst)
