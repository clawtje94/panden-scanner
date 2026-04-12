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

    # ── Header ──
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
    tekst += f"\nBron: {prop.source}\n"

    # ── AANKOOP ──
    tekst += f"\n<b>AANKOOP</b>\n"
    tekst += f"{'─' * 32}\n"
    tekst += f"Vraagprijs:      {_eur(c['vraagprijs'])}\n"
    tekst += f"OVB {c['ovb_pct']}%:          {_eur(c['ovb'])}\n"
    tekst += f"Notaris+makelaar: {_eur(c['notaris_makelaar_aankoop'])}\n"
    tekst += f"<b>Totaal aankoop:  {_eur(c['aankoop_totaal'])}</b>\n"

    # ── VERBOUWING ──
    tekst += f"\n<b>VERBOUWING</b>\n"
    tekst += f"{'─' * 32}\n"
    tekst += f"Renovatie ({_eur(c['renovatie_per_m2'])}/m\u00b2): {_eur(c['renovatie'])}\n"

    if "splitsing_kosten" in c:
        tekst += f"Splitsing ({c['n_units']}x):   {_eur(c['splitsing_kosten'])}\n"
    tekst += f"Architect+leges:  {_eur(c['architect_leges'])}\n"
    tekst += f"Onvoorzien {c['onvoorzien_pct']}%:   {_eur(c['onvoorzien'])}\n"
    if "projectmanagement" in c:
        tekst += f"Projectmanagement: {_eur(c['projectmanagement'])}\n"
        tekst += f"Overig:           {_eur(c['overige_kosten'])}\n"
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
        tekst += f"  (gem. van vergelijkbare panden)\n"
    else:
        tekst += f"Verkoopprijs/m\u00b2: {_eur(verkoop_m2)} (standaard)\n"

    tekst += f"Bruto verkoop:    {_eur(c['bruto_verkoopprijs'])}\n"
    tekst += f"Makelaar 1.5%:    -{_eur(c['makelaar_verkoop'])}\n"
    tekst += f"Notaris:          -{_eur(c['notaris_verkoop'])}\n"
    tekst += f"<b>Netto opbrengst: {_eur(c['netto_opbrengst'])}</b>\n"

    # ── REFERENTIE PANDEN ──
    refs = c.get("referenties", [])
    if refs:
        tekst += f"\n<b>REFERENTIE PANDEN</b>\n"
        tekst += f"{'─' * 32}\n"
        tekst += f"(basis voor {_eur(verkoop_m2)}/m\u00b2)\n"
        for i, ref in enumerate(refs[:3], 1):
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
