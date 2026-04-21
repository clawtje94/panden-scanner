"""
Risk-aggregator.

Verzamelt alle risico-signalen voor een pand in één dict — bruikbaar voor het
dashboard, dealscore, en Telegram notificatie. Eén lijst met flags zodat een
developer in 3 seconden ziet wat de gekte-factoren zijn.

Bronnen (elk optioneel, None/leeg is OK):
  - classificatie          (category + is_verhuurd)
  - ep_online              (forced_renovation, label)
  - bag                    (oppervlakte-afwijking, gebruiksdoel-mismatch)
  - monument               (rijksmonument)
  - erfpacht               (tijdelijk + eindjaar, Rotterdam afkoopkans)
  - wijkcheck / splitsen   (regime conflicten)
  - motion                 (verhuurd-signaal was al afgevangen elders)
"""
from __future__ import annotations

from typing import Any, Optional


# Risk levels: groen/geel/oranje/rood (analoog verkeerslicht + rood)
def _flag(niveau: str, label: str, details: str = "") -> dict:
    return {"niveau": niveau, "label": label, "details": details}


def aggregate_risks(
    classificatie: Optional[dict] = None,
    ep_online: Optional[dict] = None,
    bag: Optional[dict] = None,
    monument: Optional[dict] = None,
    erfpacht: Optional[dict] = None,
    wijkcheck: Optional[dict] = None,
    motion: Optional[dict] = None,
    prop_bouwjaar: Optional[int] = None,
    prop_opp_m2: Optional[int] = None,
) -> dict:
    """Bundel alle risk-signalen in één dict.

    Returns:
        dict met:
          - flags: list[{niveau, label, details}]
          - kansen: list[{label, details}]  (positieve arbitragekansen)
          - zwaarste: 'geen' | 'geel' | 'oranje' | 'rood'
          - aantal: int
    """
    flags = []
    kansen = []

    # ── Classificatie risks ──
    if classificatie:
        if classificatie.get("is_verhuurd"):
            flags.append(_flag(
                "rood", "Verhuurd",
                "Zittende huurder — geen directe ontwikkelkans."
            ))
        if classificatie.get("category") == "transformatie":
            flags.append(_flag(
                "oranje", "Commercieel → transformatie",
                "Woonbestemming check vereist vóór aankoop."
            ))

    # ── Monument ──
    if monument and monument.get("is_rijksmonument"):
        cat = monument.get("subcategorie") or "monument"
        flags.append(_flag(
            "oranje", "Rijksmonument",
            f"{cat} — verbouwing 30-50% duurder + vergunningstraject."
        ))

    # ── Erfpacht ──
    if erfpacht and erfpacht.get("is_erfpacht"):
        risk = erfpacht.get("risk_level", "middel")
        niv = {"hoog": "rood", "middel": "oranje", "laag": "geel"}.get(risk, "geel")
        if not erfpacht.get("is_afgekocht") and not erfpacht.get("is_eeuwigdurend"):
            flags.append(_flag(
                niv, f"Erfpacht ({risk})",
                erfpacht.get("toelichting", ""),
            ))
        if erfpacht.get("rotterdam_afkoopkans"):
            kansen.append({
                "label": "Rotterdam erfpacht-afkoop 60%",
                "details": "Eenmalige regeling 2026 — directe waardestijging na afkoop.",
            })

    # ── EP-Online ──
    if ep_online and ep_online.get("forced_renovation"):
        label = ep_online.get("label", "?")
        if ep_online.get("forced_renovation_sterk"):
            flags.append(_flag(
                "geel", f"Label {label} (pre-1992)",
                "Verhuurverbod 2028 dreigt; eigenaar vaak verkoop-gemotiveerd. Zwaardere renovatie nodig.",
            ))
            kansen.append({
                "label": "Forced renovation leverage",
                "details": "Pand-eigenaar staat onder regeldruk — onderhandelingsvoordeel.",
            })
        else:
            flags.append(_flag(
                "geel", f"Label {label}",
                "Verhuurverbod 2028 dreigt — energiesprong verplicht.",
            ))

    # ── BAG mismatch ──
    if bag:
        gd = (bag.get("gebruiksdoel") or "").lower()
        if gd and gd != "woonfunctie":
            # Niet-woonfunctie in BAG = wezenlijk risico voor fix&flip
            niveau = "rood" if gd in (
                "industriefunctie", "sportfunctie", "celfunctie",
            ) else "oranje"
            flags.append(_flag(
                niveau, f"BAG: {gd}",
                "Officieel geen woonbestemming in BAG — transformatie-vergunning nodig.",
            ))

        # Oppervlakte afwijking Funda vs BAG
        if prop_opp_m2 and bag.get("oppervlakte"):
            funda_m2 = int(prop_opp_m2)
            bag_m2 = int(bag["oppervlakte"])
            if bag_m2 > 0:
                afwijking = abs(funda_m2 - bag_m2) / bag_m2 * 100
                if afwijking >= 15:
                    flags.append(_flag(
                        "oranje",
                        f"Oppervlak afwijking {afwijking:.0f}%",
                        f"Funda: {funda_m2} m², BAG: {bag_m2} m². Controleer NEN 2580.",
                    ))

        # Bouwjaar afwijking (kan parse-fout of ongeregistreerde verbouwing zijn)
        if prop_bouwjaar and bag.get("bouwjaar"):
            diff = abs(int(prop_bouwjaar) - int(bag["bouwjaar"]))
            if diff >= 20:
                flags.append(_flag(
                    "geel",
                    f"Bouwjaar afwijking {diff}j",
                    f"Funda: {prop_bouwjaar}, BAG: {bag['bouwjaar']}. Mogelijk verbouwing of parse-fout.",
                ))

        # Pandstatus
        pandstatus = (bag.get("pandstatus") or "").lower()
        if pandstatus and "in gebruik" not in pandstatus:
            flags.append(_flag(
                "geel", f"Pandstatus: {bag.get('pandstatus')}",
                "Check BAG — pand mogelijk niet actief in gebruik.",
            ))

    # ── Wijk / splitsen regime ──
    if wijkcheck:
        if wijkcheck.get("mag") is False:
            redenen = wijkcheck.get("redenen", [])
            flags.append(_flag(
                "oranje", "Splitsen verboden (wijk)",
                "; ".join(redenen)[:200],
            ))
        elif wijkcheck.get("mag") is True:
            regime = wijkcheck.get("regime", "")
            if regime == "den_haag_2026":
                kansen.append({
                    "label": "DH splits-wijk (1-4-2026)",
                    "details": f"Leefbaarometer-score {wijkcheck.get('wijkscore', '?')} — splitsen toegestaan onder nieuwe regeling.",
                })
            elif regime == "rotterdam_2025" and not wijkcheck.get("is_nprz"):
                kansen.append({
                    "label": "RDAM splits-gebied (50 m²)",
                    "details": "Versoepeld regime 2025 — buiten NPRZ-kerngebied.",
                })

    # ── Leegstand-detectie ──
    if motion:
        dagen = motion.get("dagen_online") or 0
        if dagen >= 365:
            flags.append(_flag(
                "oranje", f"Leegstand {dagen}d",
                "Pand staat >1 jaar online — vaak verborgen probleem "
                "(juridisch/bouwkundig/overlast). Grondige due diligence vereist.",
            ))
        elif dagen >= 270:
            flags.append(_flag(
                "geel", f"Lang online {dagen}d",
                "Bijna een jaar niet verkocht — prijs of pand heeft issue.",
            ))

    zwaarste = "geen"
    order = {"geen": 0, "geel": 1, "oranje": 2, "rood": 3}
    for f in flags:
        if order.get(f["niveau"], 0) > order.get(zwaarste, 0):
            zwaarste = f["niveau"]

    return {
        "flags": flags,
        "kansen": kansen,
        "zwaarste": zwaarste,
        "aantal": len(flags),
    }
