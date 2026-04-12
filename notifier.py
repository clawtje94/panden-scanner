"""
Telegram notificaties voor gevonden kansen.
"""
import logging
import requests
from models import Property
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)

EMOJI = {
    "fix_flip":     "\U0001f528",
    "splitsing":    "\u2702\ufe0f",
    "transformatie": "\U0001f3d7",
}


def stuur_telegram(tekst: str) -> bool:
    if TELEGRAM_TOKEN == "VERVANG_MET_JOUW_BOT_TOKEN":
        logger.warning("Telegram niet geconfigureerd — sla notificatie over.")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    resp = requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": tekst,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }, timeout=10)
    if not resp.ok:
        logger.error("Telegram fout: %s", resp.text)
    return resp.ok


def stuur_property_notificatie(prop: Property) -> bool:
    strat_key = prop.strategie.split("_")[0] if "_" in prop.strategie else prop.strategie
    emoji = EMOJI.get(strat_key, "\U0001f3e0")
    sterren = "\u2b50" * prop.score

    tekst = (
        f"{emoji} <b>NIEUWE KANS — {prop.strategie.upper().replace('_',' ')}</b>\n"
        f"{'─' * 30}\n"
        f"\U0001f4cd <b>{prop.adres}</b>\n"
        f"\U0001f3d9 {prop.stad}\n\n"
        f"\U0001f4b0 Vraagprijs: <b>\u20ac{prop.prijs:,.0f}</b>\n"
        f"\U0001f4d0 Oppervlak: {prop.opp_m2} m\u00b2\n"
        f"\U0001f3f7 \u20ac{prop.prijs_per_m2:,.0f}/m\u00b2\n"
    )
    if prop.energie_label:
        tekst += f"\u26a1 Energielabel: {prop.energie_label}\n"
    if prop.bouwjaar:
        tekst += f"\U0001f5d3 Bouwjaar: {prop.bouwjaar}\n"

    tekst += (
        f"\n\U0001f4ca <b>RENDEMENT</b>\n"
        f"{'─' * 30}\n"
        f"\U0001f4c8 Netto marge: <b>{prop.marge_pct}%</b>\n"
        f"\U0001f4b5 Verwachte winst: <b>\u20ac{prop.winst_euro:,.0f}</b>\n"
        f"\U0001f504 ROI: {prop.roi_pct}%\n"
        f"\U0001f4e6 Totale investering: \u20ac{prop.totale_kosten:,.0f}\n"
        f"\U0001f3af Score: {sterren} ({prop.score}/10)\n\n"
        f"\U0001f517 <a href='{prop.url}'>Bekijk pand</a>\n"
        f"\U0001f4e1 Bron: {prop.source}"
    )
    return stuur_telegram(tekst)


def stuur_dagelijks_rapport(nieuw: int, totaal: int, gezien: int):
    import datetime
    tekst = (
        f"\U0001f4cb <b>DAGELIJKSE SCAN RAPPORT</b>\n"
        f"{'─' * 30}\n"
        f"\U0001f195 Nieuwe kansen gevonden: <b>{nieuw}</b>\n"
        f"\U0001f441 Panden gescand: {gezien}\n"
        f"\U0001f4e6 Totaal in database: {totaal}\n"
        f"\U0001f4c5 {datetime.date.today().strftime('%d-%m-%Y')}"
    )
    stuur_telegram(tekst)
