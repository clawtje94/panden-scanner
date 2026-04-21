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


def _scenario_verkoop(verkoop_oppervlak: float, verkoop_m2: float,
                       totaal_kosten: float, n_units: int = 1) -> dict:
    """Generieke verkoop-calc voor fix_flip/splitsen/transformatie.

    Args:
        verkoop_oppervlak: verkoopbare m² (fix_flip=opp, splits/trafo=gbo_totaal)
        verkoop_m2: prijs per m²
        totaal_kosten: alle investeringskosten
        n_units: aantal afzonderlijke units (bepaalt notariskosten)
    """
    omzet = verkoop_oppervlak * verkoop_m2
    makelaar = omzet * 0.015
    notaris = n_units * 2_500
    netto = omzet - makelaar - notaris
    winst = netto - totaal_kosten
    marge = (winst / netto * 100) if netto > 0 else -99
    roi = (winst / totaal_kosten * 100) if totaal_kosten > 0 else -99
    return {
        "verkoop_m2": verkoop_m2, "omzet": int(omzet),
        "makelaar": int(makelaar), "notaris": int(notaris),
        "netto": int(netto), "winst": int(winst),
        "marge_pct": round(marge, 1), "roi_pct": round(roi, 1),
    }


def bereken_fix_flip(prop: Property, cfg: dict, verkoop_m2_override: float = 0, referenties: list = None, renovatie_detail: dict = None, ref_detail: dict = None) -> Property:
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

    # ── VERKOOP (scenarios P25/P50/P75) ──
    if ref_detail and ref_detail.get("p50_pm2"):
        verkoop_m2 = ref_detail["p50_pm2"]  # realistisch (mediaan)
        verkoop_bron = "referentie_p50"
        scen_worst = _scenario_verkoop(m2, ref_detail.get("p25_pm2") or verkoop_m2, totaal_kosten)
        scen_real = _scenario_verkoop(m2, verkoop_m2, totaal_kosten)
        scen_best = _scenario_verkoop(m2, ref_detail.get("p75_pm2") or verkoop_m2, totaal_kosten)
    else:
        verkoop_m2 = verkoop_m2_override if verkoop_m2_override > 0 else cfg["verwacht_verkoop_m2"]
        verkoop_bron = "referentie_p50" if verkoop_m2_override > 0 else "config"
        scen_real = _scenario_verkoop(m2, verkoop_m2, totaal_kosten)
        # Fallback zonder spread: worst = -10%, best = +10% als ruwe indicatie
        scen_worst = _scenario_verkoop(m2, verkoop_m2 * 0.90, totaal_kosten)
        scen_best = _scenario_verkoop(m2, verkoop_m2 * 1.10, totaal_kosten)

    omzet = scen_real["omzet"]
    makelaar_verkoop = scen_real["makelaar"]
    notaris_verkoop = scen_real["notaris"]
    verkoop_kosten = makelaar_verkoop + notaris_verkoop
    netto_omzet = scen_real["netto"]
    winst = scen_real["winst"]
    marge = scen_real["marge_pct"]
    roi = scen_real["roi_pct"]

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
        # Scenarios P25/P50/P75
        "scenarios": {
            "worst": scen_worst,
            "realistic": scen_real,
            "best": scen_best,
        },
        "verkoop_referentie": {
            "p25_pm2": ref_detail.get("p25_pm2") if ref_detail else 0,
            "p50_pm2": ref_detail.get("p50_pm2") if ref_detail else verkoop_m2,
            "p75_pm2": ref_detail.get("p75_pm2") if ref_detail else 0,
            "n_refs": ref_detail.get("n_refs", 0) if ref_detail else 0,
            "n_high_label": ref_detail.get("n_high_label", 0) if ref_detail else 0,
            "spread_pct": ref_detail.get("spread_pct", 0) if ref_detail else 0,
            "avg_days_online": ref_detail.get("avg_days_online") if ref_detail else None,
            "match_niveau": ref_detail.get("match_niveau", "config") if ref_detail else "config",
            "confidence": ref_detail.get("confidence", 0) if ref_detail else 0,
            "confidence_label": ref_detail.get("confidence_label", "onvoldoende") if ref_detail else "onvoldoende",
            "waarschuwingen": ref_detail.get("waarschuwingen", []) if ref_detail else [],
            "wijk": ref_detail.get("wijk", "") if ref_detail else "",
        } if ref_detail else None,
    }
    return prop


def bereken_splitsing(prop: Property, cfg: dict, n_units: int = 2, verkoop_m2_override: float = 0, referenties: list = None, ref_detail: dict = None) -> Property:
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

    if ref_detail and ref_detail.get("p50_pm2"):
        verkoop_m2 = ref_detail["p50_pm2"]
        verkoop_bron = "referentie_p50"
        scen_worst = _scenario_verkoop(gbo_totaal, ref_detail.get("p25_pm2") or verkoop_m2, totaal_kosten, n_units)
        scen_real = _scenario_verkoop(gbo_totaal, verkoop_m2, totaal_kosten, n_units)
        scen_best = _scenario_verkoop(gbo_totaal, ref_detail.get("p75_pm2") or verkoop_m2, totaal_kosten, n_units)
    else:
        verkoop_m2 = verkoop_m2_override if verkoop_m2_override > 0 else cfg["verwacht_verkoop_m2"]
        verkoop_bron = "referentie_p50" if verkoop_m2_override > 0 else "config"
        scen_real = _scenario_verkoop(gbo_totaal, verkoop_m2, totaal_kosten, n_units)
        scen_worst = _scenario_verkoop(gbo_totaal, verkoop_m2 * 0.90, totaal_kosten, n_units)
        scen_best = _scenario_verkoop(gbo_totaal, verkoop_m2 * 1.10, totaal_kosten, n_units)

    omzet = scen_real["omzet"]
    makelaar_verkoop = scen_real["makelaar"]
    notaris_verkoop = scen_real["notaris"]
    verkoop_kosten = makelaar_verkoop + notaris_verkoop
    netto_omzet = scen_real["netto"]
    winst = scen_real["winst"]
    marge = scen_real["marge_pct"]
    roi = scen_real["roi_pct"]

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
        "scenarios": {
            "worst": scen_worst,
            "realistic": scen_real,
            "best": scen_best,
        },
        "verkoop_referentie": _ref_detail_dict(ref_detail, verkoop_m2) if ref_detail else None,
    }
    return prop


def _ref_detail_dict(ref_detail: dict, fallback_p50: float) -> dict:
    """Serializeer referentie-info voor calc-dict (dashboard/Telegram)."""
    return {
        "p25_pm2": ref_detail.get("p25_pm2", 0),
        "p50_pm2": ref_detail.get("p50_pm2", fallback_p50),
        "p75_pm2": ref_detail.get("p75_pm2", 0),
        "n_refs": ref_detail.get("n_refs", 0),
        "n_high_label": ref_detail.get("n_high_label", 0),
        "spread_pct": ref_detail.get("spread_pct", 0),
        "avg_days_online": ref_detail.get("avg_days_online"),
        "match_niveau": ref_detail.get("match_niveau", "config"),
        "confidence": ref_detail.get("confidence", 0),
        "confidence_label": ref_detail.get("confidence_label", "onvoldoende"),
        "waarschuwingen": ref_detail.get("waarschuwingen", []),
        "wijk": ref_detail.get("wijk", ""),
    }


def bereken_transformatie(prop: Property, cfg: dict, verkoop_m2_override: float = 0, referenties: list = None, ref_detail: dict = None) -> Property:
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

    if ref_detail and ref_detail.get("p50_pm2"):
        verkoop_m2 = ref_detail["p50_pm2"]
        verkoop_bron = "referentie_p50"
        scen_worst = _scenario_verkoop(gbo_totaal, ref_detail.get("p25_pm2") or verkoop_m2, totaal_kosten, n_units)
        scen_real = _scenario_verkoop(gbo_totaal, verkoop_m2, totaal_kosten, n_units)
        scen_best = _scenario_verkoop(gbo_totaal, ref_detail.get("p75_pm2") or verkoop_m2, totaal_kosten, n_units)
    else:
        verkoop_m2 = verkoop_m2_override if verkoop_m2_override > 0 else cfg["verwacht_verkoop_m2"]
        verkoop_bron = "referentie_p50" if verkoop_m2_override > 0 else "config"
        scen_real = _scenario_verkoop(gbo_totaal, verkoop_m2, totaal_kosten, n_units)
        scen_worst = _scenario_verkoop(gbo_totaal, verkoop_m2 * 0.90, totaal_kosten, n_units)
        scen_best = _scenario_verkoop(gbo_totaal, verkoop_m2 * 1.10, totaal_kosten, n_units)

    omzet = scen_real["omzet"]
    makelaar_verkoop = scen_real["makelaar"]
    notaris_verkoop = scen_real["notaris"]
    verkoop_kosten = makelaar_verkoop + notaris_verkoop
    netto_omzet = scen_real["netto"]
    winst = scen_real["winst"]
    marge = scen_real["marge_pct"]
    roi = scen_real["roi_pct"]

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
        "scenarios": {
            "worst": scen_worst,
            "realistic": scen_real,
            "best": scen_best,
        },
        "verkoop_referentie": _ref_detail_dict(ref_detail, verkoop_m2) if ref_detail else None,
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
