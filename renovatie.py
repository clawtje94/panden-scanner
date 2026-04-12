"""
Slimme renovatie-calculator — schat verbouwkosten per component
op basis van bouwjaar, energielabel, type woning en oppervlak.
"""
import logging

logger = logging.getLogger(__name__)


def schat_renovatie(
    opp_m2: int,
    bouwjaar: int = 0,
    energie_label: str = "",
    type_woning: str = "",
    is_opknapper: bool = False,
) -> dict:
    """
    Bereken renovatiekosten per component op basis van pandkenmerken.

    Returns dict met:
        - componenten: lijst van {naam, kosten, reden}
        - totaal: totale renovatiekosten
        - per_m2: kosten per m²
    """
    m2 = max(opp_m2, 1)
    label = energie_label.upper().strip() if energie_label else ""
    bj = bouwjaar if bouwjaar and bouwjaar > 1800 else 0
    type_l = type_woning.lower() if type_woning else ""
    componenten = []

    # ── 1. KEUKEN ──
    if is_opknapper or not label or label in ("D", "E", "F", "G"):
        componenten.append({
            "naam": "Keuken (volledig nieuw)",
            "kosten": 15_000,
            "reden": "Opknapper/slecht label → volledige keuken vervanging",
        })
    else:
        componenten.append({
            "naam": "Keuken (opfrissen)",
            "kosten": 6_000,
            "reden": "Redelijk label → cosmetisch opknappen",
        })

    # ── 2. BADKAMER ──
    if is_opknapper or (bj and bj < 1980):
        componenten.append({
            "naam": "Badkamer (volledig nieuw)",
            "kosten": 14_000,
            "reden": f"{'Opknapper' if is_opknapper else f'Bouwjaar {bj}'} → complete vervanging",
        })
    elif bj and bj < 2000:
        componenten.append({
            "naam": "Badkamer (renovatie)",
            "kosten": 9_000,
            "reden": f"Bouwjaar {bj} → tegels, sanitair vervangen",
        })
    else:
        componenten.append({
            "naam": "Badkamer (opfrissen)",
            "kosten": 4_000,
            "reden": "Recent bouwjaar → cosmetisch",
        })

    # ── 3. VLOEREN ──
    if is_opknapper or (bj and bj < 1970):
        kosten_m2 = 85
        reden = "Volledige vloer vervanging + egaliseren"
    elif bj and bj < 1995:
        kosten_m2 = 60
        reden = "Nieuwe vloer leggen"
    else:
        kosten_m2 = 40
        reden = "Vloer opfrissen/schuren"
    componenten.append({
        "naam": f"Vloeren ({kosten_m2}/m\u00b2)",
        "kosten": m2 * kosten_m2,
        "reden": reden,
    })

    # ── 4. SCHILDERWERK + WANDEN ──
    if is_opknapper:
        kosten_m2 = 45
        reden = "Stucwerk + schilderwerk volledig"
    else:
        kosten_m2 = 25
        reden = "Schilderwerk + kleine reparaties"
    componenten.append({
        "naam": f"Wanden/schilderwerk ({kosten_m2}/m\u00b2)",
        "kosten": m2 * kosten_m2,
        "reden": reden,
    })

    # ── 5. ELEKTRA ──
    if bj and bj < 1975:
        componenten.append({
            "naam": "Elektra (volledig vernieuwen)",
            "kosten": max(7_500, m2 * 75),
            "reden": f"Bouwjaar {bj} → groepenkast + bedrading vervangen",
        })
    elif bj and bj < 1995:
        componenten.append({
            "naam": "Elektra (deels vernieuwen)",
            "kosten": 4_500,
            "reden": f"Bouwjaar {bj} → groepenkast upgraden",
        })
    else:
        componenten.append({
            "naam": "Elektra (check + uitbreiden)",
            "kosten": 2_000,
            "reden": "Recenter bouwjaar → alleen uitbreiden",
        })

    # ── 6. LEIDINGWERK ──
    if bj and bj < 1970:
        componenten.append({
            "naam": "Leidingwerk (volledig vernieuwen)",
            "kosten": max(6_000, m2 * 65),
            "reden": f"Bouwjaar {bj} → loden/koperen leidingen vervangen",
        })
    elif bj and bj < 1990:
        componenten.append({
            "naam": "Leidingwerk (deels vernieuwen)",
            "kosten": 3_500,
            "reden": f"Bouwjaar {bj} → deels vervangen",
        })
    else:
        componenten.append({
            "naam": "Leidingwerk (kleine aanpassingen)",
            "kosten": 1_500,
            "reden": "Recent → alleen aanpassingen",
        })

    # ── 7. ISOLATIE (afhankelijk van energielabel) ──
    if label in ("F", "G", ""):
        # Volledige isolatie nodig
        iso_kosten = m2 * 120
        componenten.append({
            "naam": f"Isolatie volledig (120/m\u00b2)",
            "kosten": iso_kosten,
            "reden": f"Label {label or '?'} → vloer + dak + spouw + glas",
        })
    elif label in ("D", "E"):
        iso_kosten = m2 * 65
        componenten.append({
            "naam": f"Isolatie deels (65/m\u00b2)",
            "kosten": iso_kosten,
            "reden": f"Label {label} → dak + glas upgraden",
        })
    elif label == "C":
        iso_kosten = m2 * 30
        componenten.append({
            "naam": f"Isolatie bijwerken (30/m\u00b2)",
            "kosten": iso_kosten,
            "reden": f"Label {label} → kleine verbeteringen",
        })
    # A/B: geen isolatie nodig

    # ── 8. RAMEN/KOZIJNEN ──
    if label in ("E", "F", "G", "") or (bj and bj < 1980):
        n_ramen = max(6, m2 // 10)
        kosten_raam = 1_200
        componenten.append({
            "naam": f"Ramen/kozijnen ({n_ramen}x)",
            "kosten": n_ramen * kosten_raam,
            "reden": f"{'Slecht label' if label in ('E','F','G','') else f'Bouwjaar {bj}'} → HR++ glas",
        })
    elif label == "D" or (bj and bj < 1995):
        n_ramen = max(3, m2 // 20)
        componenten.append({
            "naam": f"Ramen deels ({n_ramen}x)",
            "kosten": n_ramen * 1_000,
            "reden": "Deels dubbelglas upgraden",
        })

    # ── 9. CV / VERWARMING ──
    if label in ("E", "F", "G") or (bj and bj < 1990):
        componenten.append({
            "naam": "CV-ketel (nieuw HR107)",
            "kosten": 4_500,
            "reden": f"Verouderd systeem → nieuwe HR-ketel",
        })
    elif label in ("C", "D"):
        componenten.append({
            "naam": "CV-ketel (onderhoud/check)",
            "kosten": 1_500,
            "reden": "Mogelijk nog goed → onderhoud",
        })

    # ── 10. DAK (bij oud bouwjaar) ──
    if bj and bj < 1960:
        dak_m2 = m2 * 0.5  # schatting dakoppervlak
        componenten.append({
            "naam": "Dak renovatie",
            "kosten": int(max(8_000, dak_m2 * 120)),
            "reden": f"Bouwjaar {bj} → dakbedekking + isolatie",
        })
    elif bj and bj < 1985:
        componenten.append({
            "naam": "Dak check/reparatie",
            "kosten": 3_500,
            "reden": f"Bouwjaar {bj} → preventief onderhoud",
        })

    # ── 11. ONVOORZIEN ──
    subtotaal = sum(c["kosten"] for c in componenten)
    onvoorzien_pct = 15 if (is_opknapper or (bj and bj < 1960)) else 10
    onvoorzien = int(subtotaal * onvoorzien_pct / 100)
    componenten.append({
        "naam": f"Onvoorzien ({onvoorzien_pct}%)",
        "kosten": onvoorzien,
        "reden": f"{'Hoog risico (oud/opknapper)' if onvoorzien_pct == 15 else 'Standaard buffer'}",
    })

    # ── 12. ARCHITECT + LEGES ──
    arch = int(subtotaal * 0.06)
    componenten.append({
        "naam": "Architect + leges (6%)",
        "kosten": arch,
        "reden": "Ontwerp + vergunning",
    })

    totaal = sum(c["kosten"] for c in componenten)
    per_m2 = round(totaal / m2)

    logger.info(
        "Renovatie %dm2 bj%s label%s: %d/m2 (totaal %d)",
        m2, bj or "?", label or "?", per_m2, totaal,
    )

    return {
        "componenten": componenten,
        "totaal": totaal,
        "per_m2": per_m2,
        "onvoorzien_pct": onvoorzien_pct,
    }
