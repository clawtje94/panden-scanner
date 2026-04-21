"""
Weekly digest — wekelijks Telegram-overzicht van top deals.

Leest leads.json en stuurt:
  - Top 10 op dealscore
  - Stats van de week (# kansen, gem score, # motivated)
  - 3 grootste nieuwe risk-signalen

Aangeroepen vanuit GitHub Actions workflow weekly_digest.yml op maandag 09:00 NL.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from collections import Counter

from notifier import stuur_telegram, _eur

logger = logging.getLogger(__name__)

LEADS_PATH = "leads.json"
TOP_N = 10


def _load_leads() -> dict:
    if not os.path.exists(LEADS_PATH):
        # Probeer de data-branch file via raw github
        import urllib.request
        url = "https://raw.githubusercontent.com/clawtje94/panden-scanner/data/leads.json"
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                return json.loads(r.read())
        except Exception as e:
            logger.error("Kon leads.json niet laden: %s", e)
            return {}
    return json.loads(open(LEADS_PATH).read())


def samenstel_maand_digest(data: dict) -> str:
    kansen = data.get("kansen", [])
    if not kansen:
        return "<b>Maandrapport</b>\n\nGeen data."
    totaal_winst = sum(k.get("winst_euro", 0) for k in kansen)
    avg_score = int(sum((k.get("dealscore") or {}).get("score", 0) for k in kansen) / len(kansen)) if kansen else 0
    top_deals = sorted(kansen, key=lambda x: -(x.get("dealscore") or {}).get("score", 0))[:15]

    t = f"<b>📅 MAANDRAPPORT</b>\n"
    t += f"{'=' * 32}\n"
    t += f"Peildatum: {data.get('scan_datum', '')[:10]}\n\n"

    t += f"<b>Score de maand</b>\n"
    t += f"Kansen in scan: {len(kansen)}\n"
    t += f"Gem dealscore: {avg_score}/100\n"
    t += f"Totale verwachte winst: {_eur(totaal_winst)}\n"

    # Stad verdeling
    stad_c = Counter(k.get("stad") for k in kansen if k.get("stad"))
    t += f"\n<b>Per stad (top 5)</b>\n"
    for s, n in stad_c.most_common(5):
        stad_winst = sum(k.get("winst_euro", 0) for k in kansen if k.get("stad") == s)
        t += f"  {s}: {n} kansen · {_eur(stad_winst)}\n"

    # Grade verdeling
    grade_c = Counter((k.get("dealscore") or {}).get("grade") for k in kansen)
    t += f"\n<b>Grade</b>\n"
    for g in ("A+", "A", "B", "C", "D"):
        if grade_c.get(g):
            t += f"  {g}: {grade_c[g]}\n"

    t += f"\n<b>🏆 Top 15 deals van de maand</b>\n"
    t += f"{'─' * 32}\n"
    for i, k in enumerate(top_deals, 1):
        ds = k.get("dealscore") or {}
        sc = k.get("scenarios") or {}
        worst = (sc.get("worst") or {}).get("marge_pct", 0)
        t += (
            f"\n{i}. [{ds.get('grade', '?')} {ds.get('score', 0)}] "
            f"{(k.get('adres') or '?')[:35]}\n"
            f"   {k.get('stad', '')} · {_eur(k.get('prijs', 0))} · "
            f"worst {worst}%\n"
        )

    return t


def samenstel_digest(data: dict) -> str:
    kansen = data.get("kansen", [])
    if not kansen:
        return "<b>Weekly Digest</b>\n\nGeen kansen in deze scan."

    scan_dt = data.get("scan_datum", "")
    totaal_winst = sum(k.get("winst_euro", 0) for k in kansen)
    gem_score = int(sum(
        (k.get("dealscore") or {}).get("score", 0) for k in kansen
    ) / len(kansen)) if kansen else 0

    motivated = sum(1 for k in kansen if (k.get("motion") or {}).get("motivated"))
    forced = sum(1 for k in kansen if (k.get("ep_online") or {}).get("forced_renovation"))
    monument = sum(1 for k in kansen if (k.get("monument") or {}).get("is_rijksmonument"))

    stad_c = Counter(k.get("stad") for k in kansen if k.get("stad"))
    grade_c = Counter((k.get("dealscore") or {}).get("grade") for k in kansen)

    # Sort op dealscore
    top = sorted(
        kansen,
        key=lambda x: -(x.get("dealscore") or {}).get("score", 0),
    )[:TOP_N]

    t = f"<b>📊 WEKELIJKSE DIGEST</b>\n"
    t += f"{'=' * 32}\n"
    t += f"Scan: {scan_dt[:10]}\n\n"
    t += f"<b>Overview</b>\n"
    t += f"Kansen: {len(kansen)} (gem {gem_score}/100)\n"
    t += f"Verwachte winst: {_eur(totaal_winst)}\n"
    t += f"🔥 Motivated: {motivated} | ⚡ Forced-reno: {forced} | 🏛️ Monument: {monument}\n"
    t += f"\n<b>Top steden</b>\n"
    for stad, n in stad_c.most_common(5):
        t += f"  {stad}: {n}\n"
    t += f"\n<b>Grade verdeling</b>\n"
    for g in ("A+", "A", "B", "C", "D"):
        if grade_c.get(g):
            t += f"  {g}: {grade_c[g]}\n"

    t += f"\n<b>🏆 Top {min(TOP_N, len(top))} deals</b>\n"
    t += f"{'─' * 32}\n"
    for i, k in enumerate(top, 1):
        ds = k.get("dealscore") or {}
        adres = k.get("adres", "?")[:40]
        grade = ds.get("grade", "?")
        score = ds.get("score", 0)
        marge = k.get("marge_pct", 0)
        prijs = k.get("prijs", 0)
        t += f"\n{i}. [{grade} {score}] {adres}\n"
        t += f"   {k.get('stad', '')} · {_eur(prijs)} · marge {marge}%\n"
        sc = k.get("scenarios") or {}
        if sc.get("worst"):
            t += f"   Worst-case marge: {sc['worst'].get('marge_pct', 0)}%\n"
        if k.get("url"):
            t += f"   <a href='{k['url']}'>link</a>\n"

    t += f"\n<a href='https://panden-scanner.vercel.app'>Open dashboard →</a>"
    return t


def main():
    data = _load_leads()
    if not data:
        logger.error("Geen data — digest afgebroken")
        return 1
    monthly = "--monthly" in sys.argv
    tekst = samenstel_maand_digest(data) if monthly else samenstel_digest(data)
    if len(tekst) > 4000:
        # Telegram HTML limiet ~4096 chars
        tekst = tekst[:3900] + "\n\n<i>...truncated</i>\n<a href='https://panden-scanner.vercel.app'>Open dashboard →</a>"
    ok = stuur_telegram(tekst)
    logger.info("Digest verstuurd: %s (%d chars)", ok, len(tekst))
    return 0 if ok else 2


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    sys.exit(main())
