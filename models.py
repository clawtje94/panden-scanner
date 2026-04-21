"""
Property dataclass en financieel model.
"""
from dataclasses import dataclass, field
from typing import Optional
from datetime import date


@dataclass
class Property:
    """Vastgoedobject gevonden door de scanner."""
    source: str
    url: str
    adres: str
    stad: str
    postcode: str = ""
    prijs: int = 0
    opp_m2: int = 0
    prijs_per_m2: float = 0.0
    type_woning: str = ""
    bouwjaar: int = 0
    energie_label: str = ""
    kamers: int = 0
    eigen_grond: bool = True
    is_commercieel: bool = False
    datum_online: Optional[date] = None
    foto_url: str = ""
    makelaar: str = ""
    status_tekst: str = ""

    # Berekende velden
    strategie: str = ""
    marge_pct: float = 0.0
    winst_euro: int = 0
    roi_pct: float = 0.0
    totale_kosten: int = 0
    verwachte_opbrengst: int = 0
    score: int = 0

    # Volledige calculatie breakdown
    calc: dict = field(default_factory=dict)


def bereken_fix_flip(prop: Property, cfg: dict, verkoop_m2_override: float = 0, referenties: list = None, renovatie_detail: dict = None) -> Property:
    m2 = max(prop.opp_m2, 1)
    koop = prop.prijs

    # ── AANKOOP ──
    ovb = koop * (cfg["ovb_pct"] / 100)
    notaris_makelaar = koop * 0.013
    aankoop_totaal = koop + ovb + notaris_makelaar

    # ── VERBOUWING (slim of flat rate) ──
    if renovatie_detail:
        bouw_totaal = renovatie_detail["totaal"]
        renovatie_per_m2_actueel = renovatie_detail["per_m2"]
    else:
        renovatie = m2 * cfg["renovatie_per_m2"]
        arch_leges = renovatie * 0.08
        onvoorzien = renovatie * 0.10
        bouw_totaal = renovatie + arch_leges + onvoorzien
        renovatie_per_m2_actueel = cfg["renovatie_per_m2"]

    # ── FINANCIERING ──
    looptijd_mnd = cfg["looptijd_maanden"]
    looptijd_jr = looptijd_mnd / 12
    financiering_basis = aankoop_totaal + bouw_totaal * 0.5
    rente = financiering_basis * (cfg["rente_pct"] / 100) * looptijd_jr

    totaal_kosten = aankoop_totaal + bouw_totaal + rente

    # ── VERKOOP ──
    verkoop_m2 = verkoop_m2_override if verkoop_m2_override > 0 else cfg["verwacht_verkoop_m2"]
    verkoop_bron = "referentie" if verkoop_m2_override > 0 else "config"
    omzet = m2 * verkoop_m2
    makelaar_verkoop = omzet * 0.015
    notaris_verkoop = 2_500
    verkoop_kosten = makelaar_verkoop + notaris_verkoop
    netto_omzet = omzet - verkoop_kosten

    winst = netto_omzet - totaal_kosten
    marge = (winst / netto_omzet * 100) if netto_omzet > 0 else -99
    roi = (winst / totaal_kosten * 100) if totaal_kosten > 0 else -99

    # ── BOD BEREKENING ──
    bod_korting_pct = 10
    bod = int(koop * (1 - bod_korting_pct / 100))
    bod_ovb = bod * (cfg["ovb_pct"] / 100)
    bod_notaris = bod * 0.013
    bod_aankoop = bod + bod_ovb + bod_notaris
    bod_financiering = (bod_aankoop + bouw_totaal * 0.5) * (cfg["rente_pct"] / 100) * looptijd_jr
    bod_totaal = bod_aankoop + bouw_totaal + bod_financiering
    bod_winst = netto_omzet - bod_totaal
    bod_marge = (bod_winst / netto_omzet * 100) if netto_omzet > 0 else -99

    prop.strategie = "fix_flip"
    prop.totale_kosten = int(totaal_kosten)
    prop.verwachte_opbrengst = int(netto_omzet)
    prop.winst_euro = int(winst)
    prop.marge_pct = round(marge, 1)
    prop.roi_pct = round(roi, 1)
    prop.calc = {
        # Aankoop
        "vraagprijs": koop,
        "ovb_pct": cfg["ovb_pct"],
        "ovb": int(ovb),
        "notaris_makelaar_aankoop": int(notaris_makelaar),
        "aankoop_totaal": int(aankoop_totaal),
        # Verbouwing
        "renovatie_per_m2": renovatie_per_m2_actueel,
        "renovatie_detail": renovatie_detail,  # None of volledige breakdown
        "bouw_totaal": int(bouw_totaal),
        # Financiering
        "looptijd_maanden": looptijd_mnd,
        "rente_pct": cfg["rente_pct"],
        "financiering_basis": int(financiering_basis),
        "rente": int(rente),
        # Totaal investering
        "totaal_kosten": int(totaal_kosten),
        # Verkoop
        "verkoop_m2": verkoop_m2,
        "verkoop_bron": verkoop_bron,
        "referenties": referenties or [],
        "bruto_verkoopprijs": int(omzet),
        "makelaar_verkoop": int(makelaar_verkoop),
        "notaris_verkoop": notaris_verkoop,
        "verkoop_kosten": int(verkoop_kosten),
        "netto_opbrengst": int(netto_omzet),
        # Resultaat op vraagprijs
        "winst": int(winst),
        "marge_pct": round(marge, 1),
        "roi_pct": round(roi, 1),
        # Bod
        "bod_korting_pct": bod_korting_pct,
        "bod": bod,
        "bod_totaal_investering": int(bod_totaal),
        "bod_winst": int(bod_winst),
        "bod_marge_pct": round(bod_marge, 1),
    }
    return prop


def bereken_splitsing(prop: Property, cfg: dict, n_units: int = 2, verkoop_m2_override: float = 0, referenties: list = None) -> Property:
    m2 = max(prop.opp_m2, 1)
    koop = prop.prijs

    ovb = koop * (cfg["ovb_pct"] / 100)
    notaris_makelaar = koop * 0.013
    aankoop_totaal = koop + ovb + notaris_makelaar

    renovatie = m2 * cfg["renovatie_per_m2"]
    splitsing_kosten = n_units * 15_000
    arch_leges = renovatie * 0.155
    onvoorzien = renovatie * 0.12
    bouw_totaal = renovatie + splitsing_kosten + arch_leges + onvoorzien

    looptijd_mnd = cfg["looptijd_maanden"]
    looptijd_jr = looptijd_mnd / 12
    financiering_basis = aankoop_totaal + bouw_totaal * 0.55
    rente = financiering_basis * (cfg["rente_pct"] / 100) * looptijd_jr

    totaal_kosten = aankoop_totaal + bouw_totaal + rente

    gbo_per_unit = (m2 * 0.80) / n_units
    gbo_totaal = m2 * 0.80
    verkoop_m2 = verkoop_m2_override if verkoop_m2_override > 0 else cfg["verwacht_verkoop_m2"]
    verkoop_bron = "referentie" if verkoop_m2_override > 0 else "config"
    omzet = n_units * gbo_per_unit * verkoop_m2
    makelaar_verkoop = omzet * 0.015
    notaris_verkoop = n_units * 2_500
    verkoop_kosten = makelaar_verkoop + notaris_verkoop
    netto_omzet = omzet - verkoop_kosten

    winst = netto_omzet - totaal_kosten
    marge = (winst / netto_omzet * 100) if netto_omzet > 0 else -99
    roi = (winst / totaal_kosten * 100) if totaal_kosten > 0 else -99

    bod_korting_pct = 10
    bod = int(koop * (1 - bod_korting_pct / 100))
    bod_ovb = bod * (cfg["ovb_pct"] / 100)
    bod_notaris = bod * 0.013
    bod_aankoop = bod + bod_ovb + bod_notaris
    bod_financiering = (bod_aankoop + bouw_totaal * 0.55) * (cfg["rente_pct"] / 100) * looptijd_jr
    bod_totaal = bod_aankoop + bouw_totaal + bod_financiering
    bod_winst = netto_omzet - bod_totaal
    bod_marge = (bod_winst / netto_omzet * 100) if netto_omzet > 0 else -99

    prop.strategie = f"splitsing_{n_units}units"
    prop.totale_kosten = int(totaal_kosten)
    prop.verwachte_opbrengst = int(netto_omzet)
    prop.winst_euro = int(winst)
    prop.marge_pct = round(marge, 1)
    prop.roi_pct = round(roi, 1)
    prop.calc = {
        "vraagprijs": koop,
        "ovb_pct": cfg["ovb_pct"],
        "ovb": int(ovb),
        "notaris_makelaar_aankoop": int(notaris_makelaar),
        "aankoop_totaal": int(aankoop_totaal),
        "renovatie_per_m2": cfg["renovatie_per_m2"],
        "renovatie": int(renovatie),
        "splitsing_kosten": int(splitsing_kosten),
        "n_units": n_units,
        "architect_leges": int(arch_leges),
        "onvoorzien_pct": 12,
        "onvoorzien": int(onvoorzien),
        "bouw_totaal": int(bouw_totaal),
        "looptijd_maanden": looptijd_mnd,
        "rente_pct": cfg["rente_pct"],
        "financiering_basis": int(financiering_basis),
        "rente": int(rente),
        "totaal_kosten": int(totaal_kosten),
        "gbo_totaal": int(gbo_totaal),
        "gbo_per_unit": int(gbo_per_unit),
        "verkoop_m2": verkoop_m2,
        "verkoop_bron": verkoop_bron,
        "referenties": referenties or [],
        "bruto_verkoopprijs": int(omzet),
        "makelaar_verkoop": int(makelaar_verkoop),
        "notaris_verkoop": int(notaris_verkoop),
        "verkoop_kosten": int(verkoop_kosten),
        "netto_opbrengst": int(netto_omzet),
        "winst": int(winst),
        "marge_pct": round(marge, 1),
        "roi_pct": round(roi, 1),
        "bod_korting_pct": bod_korting_pct,
        "bod": bod,
        "bod_totaal_investering": int(bod_totaal),
        "bod_winst": int(bod_winst),
        "bod_marge_pct": round(bod_marge, 1),
    }
    return prop


def bereken_transformatie(prop: Property, cfg: dict, verkoop_m2_override: float = 0, referenties: list = None) -> Property:
    m2 = max(prop.opp_m2, 1)
    koop = prop.prijs

    ovb = koop * (cfg["ovb_pct"] / 100)
    notaris_makelaar = koop * 0.013
    aankoop_totaal = koop + ovb + notaris_makelaar

    bouw = m2 * cfg["renovatie_per_m2"]
    arch_leges = bouw * 0.155
    onvoorzien = bouw * 0.12
    bouw_totaal = bouw + arch_leges + onvoorzien

    proj_mgmt = (aankoop_totaal + bouw_totaal) * 0.035
    overig = 25_000

    looptijd_mnd = cfg["looptijd_maanden"]
    looptijd_jr = looptijd_mnd / 12
    financiering_basis = aankoop_totaal + (bouw_totaal + proj_mgmt) * 0.55
    rente = financiering_basis * (cfg["rente_pct"] / 100) * looptijd_jr

    totaal_kosten = aankoop_totaal + bouw_totaal + proj_mgmt + overig + rente

    n_units = max(1, int(m2 * 0.75 / 75))
    gbo_totaal = m2 * 0.75
    verkoop_m2 = verkoop_m2_override if verkoop_m2_override > 0 else cfg["verwacht_verkoop_m2"]
    verkoop_bron = "referentie" if verkoop_m2_override > 0 else "config"
    omzet = gbo_totaal * verkoop_m2
    makelaar_verkoop = omzet * 0.015
    notaris_verkoop = n_units * 2_500
    verkoop_kosten = makelaar_verkoop + notaris_verkoop
    netto_omzet = omzet - verkoop_kosten

    winst = netto_omzet - totaal_kosten
    marge = (winst / netto_omzet * 100) if netto_omzet > 0 else -99
    roi = (winst / totaal_kosten * 100) if totaal_kosten > 0 else -99

    bod_korting_pct = 12
    bod = int(koop * (1 - bod_korting_pct / 100))
    bod_ovb = bod * (cfg["ovb_pct"] / 100)
    bod_notaris = bod * 0.013
    bod_aankoop = bod + bod_ovb + bod_notaris
    bod_financiering = (bod_aankoop + (bouw_totaal + proj_mgmt) * 0.55) * (cfg["rente_pct"] / 100) * looptijd_jr
    bod_totaal = bod_aankoop + bouw_totaal + proj_mgmt + overig + bod_financiering
    bod_winst = netto_omzet - bod_totaal
    bod_marge = (bod_winst / netto_omzet * 100) if netto_omzet > 0 else -99

    prop.strategie = f"transformatie_{n_units}units"
    prop.totale_kosten = int(totaal_kosten)
    prop.verwachte_opbrengst = int(netto_omzet)
    prop.winst_euro = int(winst)
    prop.marge_pct = round(marge, 1)
    prop.roi_pct = round(roi, 1)
    prop.calc = {
        "vraagprijs": koop,
        "ovb_pct": cfg["ovb_pct"],
        "ovb": int(ovb),
        "notaris_makelaar_aankoop": int(notaris_makelaar),
        "aankoop_totaal": int(aankoop_totaal),
        "renovatie_per_m2": cfg["renovatie_per_m2"],
        "renovatie": int(bouw),
        "architect_leges": int(arch_leges),
        "onvoorzien_pct": 12,
        "onvoorzien": int(onvoorzien),
        "bouw_totaal": int(bouw_totaal),
        "projectmanagement": int(proj_mgmt),
        "overige_kosten": overig,
        "looptijd_maanden": looptijd_mnd,
        "rente_pct": cfg["rente_pct"],
        "financiering_basis": int(financiering_basis),
        "rente": int(rente),
        "totaal_kosten": int(totaal_kosten),
        "n_units": n_units,
        "bvo_m2": m2,
        "gbo_totaal": int(gbo_totaal),
        "gbo_per_unit": int(gbo_totaal / n_units) if n_units > 0 else 0,
        "verkoop_m2": verkoop_m2,
        "verkoop_bron": verkoop_bron,
        "referenties": referenties or [],
        "bruto_verkoopprijs": int(omzet),
        "makelaar_verkoop": int(makelaar_verkoop),
        "notaris_verkoop": int(notaris_verkoop),
        "verkoop_kosten": int(verkoop_kosten),
        "netto_opbrengst": int(netto_omzet),
        "winst": int(winst),
        "marge_pct": round(marge, 1),
        "roi_pct": round(roi, 1),
        "bod_korting_pct": bod_korting_pct,
        "bod": bod,
        "bod_totaal_investering": int(bod_totaal),
        "bod_winst": int(bod_winst),
        "bod_marge_pct": round(bod_marge, 1),
    }
    return prop


def score_property(prop: Property) -> int:
    score = 0
    if prop.marge_pct >= 20: score += 4
    elif prop.marge_pct >= 15: score += 3
    elif prop.marge_pct >= 12: score += 2
    elif prop.marge_pct >= 8: score += 1

    if prop.eigen_grond: score += 1
    if prop.energie_label in ("F", "G", "Geen label"): score += 1
    if prop.bouwjaar and 1900 <= prop.bouwjaar <= 1940: score += 1
    if prop.opp_m2 >= 150: score += 1
    if prop.prijs > 0 and prop.opp_m2 > 0:
        if (prop.prijs / prop.opp_m2) < 3_000: score += 1

    prop.score = min(score, 10)
    return prop.score
