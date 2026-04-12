"""
Property dataclass en financieel model.
"""
from dataclasses import dataclass
from typing import Optional
from datetime import date


@dataclass
class Property:
    """Vastgoedobject gevonden door de scanner."""
    source: str               # "funda", "funda_ib", "pararius", "bedrijfspand"
    url: str
    adres: str
    stad: str
    postcode: str = ""
    prijs: int = 0            # Vraagprijs in €
    opp_m2: int = 0           # Woonoppervlak in m²
    prijs_per_m2: float = 0.0
    type_woning: str = ""     # "appartement", "woonhuis", "kantoor", etc.
    bouwjaar: int = 0
    energie_label: str = ""
    kamers: int = 0
    eigen_grond: bool = True
    is_commercieel: bool = False
    datum_online: Optional[date] = None
    foto_url: str = ""

    # Berekende velden
    strategie: str = ""       # "fix_flip", "splitsing", "transformatie"
    marge_pct: float = 0.0
    winst_euro: int = 0
    roi_pct: float = 0.0
    totale_kosten: int = 0
    verwachte_opbrengst: int = 0
    score: int = 0            # 0-10 totaalscore


def bereken_fix_flip(prop: Property, cfg: dict) -> Property:
    """Bereken rendement voor fix & flip strategie."""
    m2 = max(prop.opp_m2, 1)
    koop = prop.prijs
    ovb = koop * (cfg["ovb_pct"] / 100)
    aankoop_totaal = koop + ovb + koop * 0.013  # notaris + makelaar

    renovatie = m2 * cfg["renovatie_per_m2"]
    arch_leges = renovatie * 0.08
    bouw_totaal = renovatie + arch_leges + renovatie * 0.10  # 10% onvoorzien

    looptijd_jr = cfg["looptijd_maanden"] / 12
    rente = (aankoop_totaal + bouw_totaal * 0.5) * (cfg["rente_pct"] / 100) * looptijd_jr

    totaal_kosten = aankoop_totaal + bouw_totaal + rente

    omzet = m2 * cfg["verwacht_verkoop_m2"]
    verkoop_kosten = omzet * 0.015 + 2_500  # makelaar + notaris
    netto_omzet = omzet - verkoop_kosten

    winst = netto_omzet - totaal_kosten
    marge = (winst / netto_omzet * 100) if netto_omzet > 0 else -99
    roi = (winst / totaal_kosten * 100) if totaal_kosten > 0 else -99

    prop.strategie = "fix_flip"
    prop.totale_kosten = int(totaal_kosten)
    prop.verwachte_opbrengst = int(netto_omzet)
    prop.winst_euro = int(winst)
    prop.marge_pct = round(marge, 1)
    prop.roi_pct = round(roi, 1)
    return prop


def bereken_splitsing(prop: Property, cfg: dict, n_units: int = 2) -> Property:
    """Bereken rendement voor splitsing naar meerdere appartementen."""
    m2 = max(prop.opp_m2, 1)
    koop = prop.prijs
    ovb = koop * (cfg["ovb_pct"] / 100)
    aankoop_totaal = koop + ovb + koop * 0.013

    renovatie = m2 * cfg["renovatie_per_m2"]
    splitsing_kosten = n_units * 15_000   # vergunning + architect per unit
    arch_leges = renovatie * 0.155        # architect 10% + leges 4.5% + constructeur
    onvoorzien = renovatie * 0.12
    bouw_totaal = renovatie + splitsing_kosten + arch_leges + onvoorzien

    looptijd_jr = cfg["looptijd_maanden"] / 12
    rente = (aankoop_totaal + bouw_totaal * 0.55) * (cfg["rente_pct"] / 100) * looptijd_jr

    totaal_kosten = aankoop_totaal + bouw_totaal + rente

    gbo_per_unit = (m2 * 0.80) / n_units
    omzet = n_units * gbo_per_unit * cfg["verwacht_verkoop_m2"]
    verkoop_kosten = omzet * 0.015 + n_units * 2_500
    netto_omzet = omzet - verkoop_kosten

    winst = netto_omzet - totaal_kosten
    marge = (winst / netto_omzet * 100) if netto_omzet > 0 else -99
    roi = (winst / totaal_kosten * 100) if totaal_kosten > 0 else -99

    prop.strategie = f"splitsing_{n_units}units"
    prop.totale_kosten = int(totaal_kosten)
    prop.verwachte_opbrengst = int(netto_omzet)
    prop.winst_euro = int(winst)
    prop.marge_pct = round(marge, 1)
    prop.roi_pct = round(roi, 1)
    return prop


def bereken_transformatie(prop: Property, cfg: dict) -> Property:
    """Bereken rendement voor transformatie commercieel → wonen."""
    m2 = max(prop.opp_m2, 1)
    koop = prop.prijs
    ovb = koop * (cfg["ovb_pct"] / 100)
    aankoop_totaal = koop + ovb + koop * 0.013

    bouw = m2 * cfg["renovatie_per_m2"]
    arch_leges = bouw * 0.155
    onvoorzien = bouw * 0.12
    bouw_totaal = bouw + arch_leges + onvoorzien

    proj_mgmt = (aankoop_totaal + bouw_totaal) * 0.035
    overig = 25_000

    looptijd_jr = cfg["looptijd_maanden"] / 12
    rente = (aankoop_totaal + (bouw_totaal + proj_mgmt) * 0.55) * (cfg["rente_pct"] / 100) * looptijd_jr

    totaal_kosten = aankoop_totaal + bouw_totaal + proj_mgmt + overig + rente

    n_units = max(1, int(m2 * 0.75 / 75))  # schat aantal units (75m² per unit)
    gbo_totaal = m2 * 0.75
    omzet = gbo_totaal * cfg["verwacht_verkoop_m2"]
    verkoop_kosten = omzet * 0.015 + n_units * 2_500
    netto_omzet = omzet - verkoop_kosten

    winst = netto_omzet - totaal_kosten
    marge = (winst / netto_omzet * 100) if netto_omzet > 0 else -99
    roi = (winst / totaal_kosten * 100) if totaal_kosten > 0 else -99

    prop.strategie = f"transformatie_{n_units}units"
    prop.totale_kosten = int(totaal_kosten)
    prop.verwachte_opbrengst = int(netto_omzet)
    prop.winst_euro = int(winst)
    prop.marge_pct = round(marge, 1)
    prop.roi_pct = round(roi, 1)
    return prop


def score_property(prop: Property) -> int:
    """Geef een score 0-10 aan een property op basis van aantrekkelijkheid."""
    score = 0
    if prop.marge_pct >= 20: score += 4
    elif prop.marge_pct >= 15: score += 3
    elif prop.marge_pct >= 12: score += 2
    elif prop.marge_pct >= 8: score += 1

    if prop.eigen_grond: score += 1
    if prop.energie_label in ("F", "G", "Geen label"): score += 1  # extra korting mogelijk
    if prop.bouwjaar and 1900 <= prop.bouwjaar <= 1940: score += 1  # karakteristiek
    if prop.opp_m2 >= 150: score += 1  # splitsbaar
    if prop.prijs > 0 and prop.opp_m2 > 0:
        if (prop.prijs / prop.opp_m2) < 3_000: score += 1  # goedkoop per m²

    prop.score = min(score, 10)
    return prop.score
