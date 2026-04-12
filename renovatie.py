"""
Slimme renovatie-calculator — realistische verbouwkosten per component
op basis van bouwjaar, energielabel, type woning en oppervlak.

Bronnen: Verbouwkosten.com, Homeproof, Vereniging Eigen Huis 2025/2026.
Prijzen zijn INCLUSIEF arbeid en materiaal, excl. BTW.
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

    Realistische prijsniveaus 2025/2026 Nederland:
    - Cosmetisch (label A/B, recent bj): €800-1.000/m²
    - Medium (label C/D, bj 1980-2000): €1.000-1.400/m²
    - Zwaar (label E-G, bj <1980): €1.400-2.000/m²
    - Casco (opknapper, bj <1960): €1.800-2.500/m²
    """
    m2 = max(opp_m2, 1)
    label = energie_label.upper().strip() if energie_label else ""
    bj = bouwjaar if bouwjaar and bouwjaar > 1800 else 0
    is_oud = bj > 0 and bj < 1975
    is_heel_oud = bj > 0 and bj < 1950
    slecht_label = label in ("E", "F", "G", "")
    matig_label = label in ("C", "D")
    componenten = []

    # ── 1. KEUKEN ──
    if is_opknapper or is_oud:
        componenten.append({
            "naam": "Keuken compleet nieuw",
            "kosten": 22_000,
            "reden": "Volledig nieuwe keuken met apparatuur en aanrecht",
        })
    elif slecht_label or matig_label:
        componenten.append({
            "naam": "Keuken renovatie",
            "kosten": 16_000,
            "reden": "Nieuwe fronten, apparatuur, blad",
        })
    else:
        componenten.append({
            "naam": "Keuken opfrissen",
            "kosten": 8_000,
            "reden": "Nieuwe fronten en apparatuur",
        })

    # ── 2. BADKAMER ──
    if is_opknapper or is_oud:
        componenten.append({
            "naam": "Badkamer compleet nieuw",
            "kosten": 18_000,
            "reden": "Volledig strippen, nieuw sanitair, tegels, leidingwerk",
        })
    elif slecht_label or matig_label:
        componenten.append({
            "naam": "Badkamer renovatie",
            "kosten": 13_000,
            "reden": "Nieuw sanitair en tegelwerk",
        })
    else:
        componenten.append({
            "naam": "Badkamer opfrissen",
            "kosten": 7_000,
            "reden": "Sanitair vervangen, voegen vernieuwen",
        })

    # ── 3. TOILET (apart) ──
    if is_opknapper or is_oud:
        componenten.append({
            "naam": "Toilet nieuw",
            "kosten": 3_500,
            "reden": "Volledig nieuw toilet met tegels",
        })
    else:
        componenten.append({
            "naam": "Toilet opknappen",
            "kosten": 1_500,
            "reden": "Nieuw toilet, kleine aanpassingen",
        })

    # ── 4. VLOEREN ──
    if is_opknapper or is_heel_oud:
        kosten_m2 = 130  # balken controleren, egaliseren, nieuwe vloer
        reden = "Ondervloer controleren/vervangen + egaliseren + nieuwe vloer"
    elif is_oud or slecht_label:
        kosten_m2 = 95
        reden = "Egaliseren + nieuwe vloer (PVC/laminaat)"
    elif matig_label:
        kosten_m2 = 75
        reden = "Nieuwe vloer leggen"
    else:
        kosten_m2 = 55
        reden = "Vloer vervangen/opschuren"
    componenten.append({
        "naam": f"Vloeren ({kosten_m2}/m\u00b2)",
        "kosten": m2 * kosten_m2,
        "reden": reden,
    })

    # ── 5. SCHILDERWERK + WANDEN + PLAFONDS ──
    if is_opknapper or is_heel_oud:
        kosten_m2 = 75  # stucwerk eraf, opnieuw stuken, schilderen
        reden = "Stucwerk vernieuwen + schilderen (hele woning)"
    elif is_oud or slecht_label:
        kosten_m2 = 55
        reden = "Wanden repareren + latex + houtwerk schilderen"
    else:
        kosten_m2 = 38
        reden = "Schilderwerk binnen + buiten (kozijnen)"
    componenten.append({
        "naam": f"Wanden/plafonds/schilderwerk",
        "kosten": m2 * kosten_m2,
        "reden": reden,
    })

    # ── 6. ELEKTRA ──
    if is_heel_oud:
        componenten.append({
            "naam": "Elektra volledig vernieuwen",
            "kosten": max(12_000, m2 * 110),
            "reden": f"Bouwjaar {bj} — groepenkast + alle bedrading + stopcontacten",
        })
    elif is_oud:
        componenten.append({
            "naam": "Elektra grotendeels vernieuwen",
            "kosten": max(8_000, m2 * 80),
            "reden": f"Bouwjaar {bj} — groepenkast + deels bedrading",
        })
    elif slecht_label or matig_label:
        componenten.append({
            "naam": "Elektra upgraden",
            "kosten": 5_500,
            "reden": "Groepenkast + extra groepen + stopcontacten",
        })
    else:
        componenten.append({
            "naam": "Elektra uitbreiden",
            "kosten": 3_000,
            "reden": "Extra stopcontacten en groepen",
        })

    # ── 7. LEIDINGWERK / SANITAIR ──
    if is_heel_oud:
        componenten.append({
            "naam": "Leidingwerk volledig vervangen",
            "kosten": max(10_000, m2 * 90),
            "reden": f"Bouwjaar {bj} — water + afvoer + gas vervangen",
        })
    elif is_oud:
        componenten.append({
            "naam": "Leidingwerk grotendeels vervangen",
            "kosten": max(6_500, m2 * 60),
            "reden": f"Bouwjaar {bj} — water + afvoer deels vervangen",
        })
    elif slecht_label:
        componenten.append({
            "naam": "Leidingwerk deels vervangen",
            "kosten": 4_500,
            "reden": "Verouderd leidingwerk upgraden",
        })
    else:
        componenten.append({
            "naam": "Leidingwerk aanpassen",
            "kosten": 2_500,
            "reden": "Kleine aanpassingen sanitair",
        })

    # ── 8. ISOLATIE ──
    if slecht_label or (label == "" and (not bj or bj < 1990)):
        # Volledige isolatie nodig
        componenten.append({
            "naam": "Isolatie volledig",
            "kosten": m2 * 180,
            "reden": f"Label {label or '?'} — vloer + dak + gevel + kierdichting",
        })
    elif matig_label:
        componenten.append({
            "naam": "Isolatie verbeteren",
            "kosten": m2 * 90,
            "reden": f"Label {label} — dak + vloer isolatie bijwerken",
        })
    elif label == "B":
        componenten.append({
            "naam": "Isolatie bijwerken",
            "kosten": m2 * 30,
            "reden": "Label B — kierdichting + kleine verbeteringen",
        })
    # A/A+: geen isolatie nodig

    # ── 9. RAMEN/KOZIJNEN ──
    if slecht_label or (bj and bj < 1980):
        n_ramen = max(8, m2 // 8)
        kosten_raam = 1_500  # incl. kozijn + HR++ glas + plaatsing
        componenten.append({
            "naam": f"Ramen + kozijnen ({n_ramen}x HR++)",
            "kosten": n_ramen * kosten_raam,
            "reden": f"Enkel/dubbel glas → HR++ met nieuwe kozijnen",
        })
    elif matig_label or (bj and bj < 1995):
        n_ramen = max(4, m2 // 15)
        componenten.append({
            "naam": f"Ramen deels vervangen ({n_ramen}x)",
            "kosten": n_ramen * 1_200,
            "reden": "Oudere ramen upgraden naar HR++",
        })

    # ── 10. CV / VERWARMING ──
    if slecht_label or (bj and bj < 1990):
        componenten.append({
            "naam": "CV-ketel nieuw (HR107)",
            "kosten": 5_500,
            "reden": "Verouderde ketel → nieuwe HR-combi",
        })
        if m2 > 100:
            componenten.append({
                "naam": "Radiatoren vervangen",
                "kosten": max(4_000, int(m2 * 35)),
                "reden": "Oude radiatoren → nieuwe convectoren",
            })
    elif matig_label:
        componenten.append({
            "naam": "CV-ketel onderhoud/vervanging",
            "kosten": 3_000,
            "reden": "Mogelijk verouderd — budget voor vervanging",
        })

    # ── 11. DAK ──
    if is_heel_oud:
        dak_m2 = int(m2 * 0.55)
        componenten.append({
            "naam": "Dak renovatie",
            "kosten": max(12_000, dak_m2 * 160),
            "reden": f"Bouwjaar {bj} — dakbedekking + constructie + isolatie",
        })
    elif is_oud:
        componenten.append({
            "naam": "Dak reparatie + isolatie",
            "kosten": max(6_000, int(m2 * 0.5 * 100)),
            "reden": f"Bouwjaar {bj} — dakpannen + isolatie verbeteren",
        })

    # ── 12. BUITENWERK (kozijnen, gevel, tuin) ──
    if is_oud:
        componenten.append({
            "naam": "Buitenwerk (gevel/tuin)",
            "kosten": max(5_000, int(m2 * 40)),
            "reden": "Voegwerk, buitenschilderwerk, tuin opknappen",
        })
    else:
        componenten.append({
            "naam": "Buitenschilderwerk",
            "kosten": 3_500,
            "reden": "Kozijnen buiten schilderen + kleine reparaties",
        })

    # ── SUBTOTAAL ──
    subtotaal = sum(c["kosten"] for c in componenten)

    # ── 13. ONVOORZIEN ──
    if is_opknapper or is_heel_oud:
        onvoorzien_pct = 15
    elif is_oud or slecht_label:
        onvoorzien_pct = 12
    else:
        onvoorzien_pct = 10
    onvoorzien = int(subtotaal * onvoorzien_pct / 100)
    componenten.append({
        "naam": f"Onvoorzien ({onvoorzien_pct}%)",
        "kosten": onvoorzien,
        "reden": "Buffer voor verrassingen tijdens verbouwing",
    })

    # ── 14. ARCHITECT + LEGES + BOUWBEGELEIDING ──
    arch_pct = 8 if (is_oud or slecht_label) else 6
    arch = int(subtotaal * arch_pct / 100)
    componenten.append({
        "naam": f"Architect + leges ({arch_pct}%)",
        "kosten": arch,
        "reden": "Ontwerp, vergunning, bouwbegeleiding",
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
