"""
Bod-advies generator.

Berekent 3 bod-niveaus per pand en levert onderhandelings-argumenten:

  - Aggressief bod: motivated seller + slecht label + risks = laag starten
  - Markt-bod: standaard -5% op vraagprijs
  - Plafond-bod: max bod waar worst-case marge nog ≥ 10%

Argumenten-lijst komt uit:
  - motion signalen (dagen online, prijsverlaging, makelaarswissel)
  - risks (monument = duur, erfpacht = onzekerheid, verhuurd = complicatie)
  - forced renovation (label E/F/G → leverage)
  - BAG vs Funda afwijking
  - veiling/biedboek origin
"""
from __future__ import annotations

from typing import Optional


def _bereken_plafond_bod(
    scen_worst: dict,
    vraagprijs: int,
    aankoop_totaal_bij_vraag: int,
    totaal_kosten_bij_vraag: int,
    min_marge: float = 10.0,
) -> Optional[int]:
    """Zoek het hoogste bod waar worst-case marge ≥ min_marge% blijft.

    Ruwe schatting: elke euro lagere aankoop = ~1.1 euro lagere kosten
    (door lagere OVB + notaris + lagere rentebasis). Dus:
        marge_delta = extra_nettobesparing / netto_opbrengst
    """
    netto = scen_worst.get("netto", 0)
    if netto <= 0:
        return None
    huidige_marge = scen_worst.get("marge_pct", 0)
    if huidige_marge >= min_marge:
        return vraagprijs  # vraagprijs voldoet al
    # Hoeveel marge moeten we extra? (min_marge - huidige_marge)/100 * netto
    extra_marge_euro = (min_marge - huidige_marge) / 100 * netto
    # Elke euro lagere aankoop bespaart ~1.1 (OVB 8% + rente + notaris)
    bod_verlaging = extra_marge_euro / 1.1
    plafond = int(vraagprijs - bod_verlaging)
    return max(10_000, plafond)


def genereer_bod_advies(
    vraagprijs: int,
    calc: dict,
    motion: Optional[dict] = None,
    risks: Optional[dict] = None,
    ep_online: Optional[dict] = None,
    erfpacht: Optional[dict] = None,
    bag: Optional[dict] = None,
    opp_m2: int = 0,
) -> dict:
    """Retourneer dict met 3 bod-niveaus + argumenten + onderhandel-strategie."""
    scen = calc.get("scenarios") or {}
    scen_worst = scen.get("worst") or {}
    scen_real = scen.get("realistic") or {}
    aankoop_totaal = calc.get("aankoop_totaal", 0)
    totaal_kosten = calc.get("totaal_kosten", 0)

    argumenten = []
    korting_modifier = 0.0  # extra % boven markt-bod

    # ── Motion signalen (verkoper onder druk) ──
    if motion:
        if motion.get("prijsverlaging_pct", 0) >= 5:
            argumenten.append(
                f"Vraagprijs al {motion['prijsverlaging_pct']}% verlaagd — "
                "verkoper is onder druk."
            )
            korting_modifier += 3
        if motion.get("aantal_prijsverlagingen", 0) >= 2:
            argumenten.append(
                f"{motion['aantal_prijsverlagingen']}× prijsverlaging — "
                "moeilijk verkoopbaar, onderhandelingsruimte."
            )
            korting_modifier += 2
        if motion.get("dagen_online", 0) >= 180:
            argumenten.append(
                f"{motion['dagen_online']} dagen online — "
                "zichtbaar niet-verkocht, verkoper gefrustreerd."
            )
            korting_modifier += 3
        elif motion.get("dagen_online", 0) >= 120:
            argumenten.append(f"{motion['dagen_online']} dagen online — langer dan gemiddeld.")
            korting_modifier += 1.5
        if motion.get("makelaarswissel"):
            argumenten.append("Makelaarswissel — eerdere strategie faalde, nieuwe aanpak nodig.")
            korting_modifier += 2
        if motion.get("onder_bod_terug"):
            argumenten.append(
                "Pand heeft onder bod gestaan en kwam terug — "
                "vorige koper haakte af (financiering/bouwkundig?)."
            )
            korting_modifier += 2

    # ── Risico-flags als onderhandel-argument ──
    if risks:
        for f in risks.get("flags", []):
            lbl = f["label"].lower()
            if "rijksmonument" in lbl:
                argumenten.append("Rijksmonument — verbouwing 30-50% duurder, leverage voor lager bod.")
                korting_modifier += 3
            elif "bag:" in lbl and any(x in lbl for x in ("industrie", "kantoor")):
                argumenten.append("BAG gebruiksdoel niet-woonfunctie — transformatie-kosten + vergunningsrisico.")
                korting_modifier += 4
            elif "oppervlak afwijking" in lbl:
                argumenten.append(f"Oppervlakte-afwijking tussen Funda en BAG — kleiner pand dan geadverteerd.")
                korting_modifier += 2
            elif "erfpacht" in lbl and f.get("niveau") == "rood":
                argumenten.append("Korte erfpacht-looptijd — waarde-afslag bij canon-heronderhandeling.")
                korting_modifier += 5
            elif "bouwjaar afwijking" in lbl:
                argumenten.append("Bouwjaar afwijkt van BAG — mogelijk ongeregistreerde verbouwing of onjuiste opgave.")
                korting_modifier += 1

    # ── Forced renovation leverage ──
    if ep_online and ep_online.get("forced_renovation"):
        label = ep_online.get("label", "?")
        argumenten.append(
            f"Energielabel {label} — verhuurverbod 2028 dreigt, "
            "eigenaar moet renoveren of verkopen."
        )
        korting_modifier += 3 if ep_online.get("forced_renovation_sterk") else 2

    # ── Erfpacht (tijdelijk / hoog risico) ──
    if erfpacht and erfpacht.get("is_erfpacht") and not erfpacht.get("is_afgekocht"):
        jr = erfpacht.get("jaren_resterend")
        if jr is not None and jr < 30:
            argumenten.append(f"Tijdelijke erfpacht, nog {jr} jaar — waarde-afslag in bod.")
            korting_modifier += 4
        elif erfpacht.get("rotterdam_afkoopkans"):
            argumenten.append(
                "Rotterdam erfpacht-afkoopregeling 2026 (60%) — "
                "kosten meenemen in bod-berekening."
            )
            korting_modifier += 2

    # ── Bod-niveaus berekenen ──
    # Aggressief: 12% + korting_modifier% onder vraag
    aggressief_pct = min(30, 12 + korting_modifier)
    aggressief = int(vraagprijs * (1 - aggressief_pct / 100))

    # Markt: 5% onder vraag standaard
    markt_pct = 5 + min(5, korting_modifier / 2)
    markt = int(vraagprijs * (1 - markt_pct / 100))

    # Plafond: waar worst-case marge nog ≥ 10%
    plafond = _bereken_plafond_bod(scen_worst, vraagprijs, aankoop_totaal, totaal_kosten, 10.0)
    if plafond and plafond > vraagprijs:
        plafond_tekst = f"Vraagprijs ({plafond:,})"
    elif plafond:
        plafond_tekst = f"{plafond:,}"
    else:
        plafond_tekst = "n.v.t."

    # Strategie-advies
    if korting_modifier >= 8:
        strategie = "Aggressief starten — sterke onderhandelingspositie."
    elif korting_modifier >= 4:
        strategie = "Markt-bod als start, ruimte om te zakken."
    elif scen_worst.get("marge_pct", 0) >= 15:
        strategie = "Solide deal — markt-bod, niet te veel bieden."
    else:
        strategie = "Krappe deal — pas bij aggressief bod rendabel."

    return {
        "vraagprijs": vraagprijs,
        "aggressief": {
            "bod": aggressief,
            "korting_pct": round(aggressief_pct, 1),
            "label": "Agressief",
        },
        "markt": {
            "bod": markt,
            "korting_pct": round(markt_pct, 1),
            "label": "Markt",
        },
        "plafond": {
            "bod": plafond,
            "tekst": plafond_tekst,
            "label": "Plafond (10% worst-marge)",
        },
        "korting_modifier": round(korting_modifier, 1),
        "argumenten": argumenten,
        "strategie": strategie,
    }
