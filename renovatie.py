"""
Renovatie-calculator — actuele verbouwkosten 2025/2026 Nederland.
Alle prijzen INCLUSIEF arbeid + materiaal + BTW.

Bronnen: Verbouwkosten.com, Werkspot.nl, Homeproof.nl, Homedeal.nl, VEH.

Wijk-multipliers: regionale verschillen in aannemersprijzen en
welstandseisen. Kralingen/Statenkwartier duurder door premium-vraag +
monument-straatjes; Moerwijk/Schiedam-oost goedkoper door veel ZZP-aannemers
en lagere consumenten-eisen. Gebaseerd op Bouwnij/EIB-regiodata 2024-2025.
"""
import logging
import re

logger = logging.getLogger(__name__)

# PC4-based multipliers. Default = 1.0 (landelijk gemiddelde).
# > 1.0 = duurder dan gemiddeld, < 1.0 = goedkoper.
_WIJK_MULT_PC4 = {
    # Den Haag premium (monument-gebieden, welstand streng)
    **{pc: 1.15 for pc in (2582, 2585, 2586, 2517, 2518, 2594, 2593, 2595)},
    # Den Haag middensegment
    **{pc: 1.08 for pc in (2511, 2512, 2513, 2562, 2563, 2564, 2565, 2566)},
    # Den Haag goedkoop (aannemers-marge lager, minder welstand)
    **{pc: 0.92 for pc in (2521, 2522, 2524, 2525, 2526, 2527,
                             2531, 2532, 2533, 2543, 2544, 2572, 2573, 2574)},
    # Rotterdam premium (Kralingen, Hillegersberg, centrum-noord)
    **{pc: 1.15 for pc in (3062, 3063, 3051, 3052, 3053, 3054, 3055, 3056)},
    **{pc: 1.08 for pc in (3011, 3012, 3013, 3014, 3015, 3016, 3021, 3022, 3023, 3024, 3025)},
    # Rotterdam-zuid (NPRZ + goedkopere arbeid)
    **{pc: 0.90 for pc in (3071, 3072, 3073, 3074, 3075, 3081, 3082, 3083, 3085, 3086, 3087, 3088)},
    # Schiedam (ruwweg goedkoper dan RDAM-centrum)
    **{pc: 0.93 for pc in (3111, 3112, 3113, 3114, 3116, 3117, 3118, 3119)},
    # Delft/Leiden centrum
    **{pc: 1.10 for pc in (2611, 2612, 2613, 2311, 2312, 2313, 2314, 2315)},
    # Dordrecht binnenstad (historisch, welstand)
    **{pc: 1.05 for pc in (3311, 3312, 3313)},
    # Rijswijk/Zoetermeer standaard
    **{pc: 0.98 for pc in (2281, 2282, 2283, 2284, 2285, 2286, 2287, 2288,
                             2711, 2712, 2713, 2714, 2715, 2716, 2717, 2718)},
}

# Stad-fallback als PC4 niet gevonden
_WIJK_MULT_STAD = {
    "den haag": 1.05, "'s-gravenhage": 1.05,
    "rotterdam": 1.02,
    "delft": 1.05, "leiden": 1.08, "dordrecht": 1.00,
    "schiedam": 0.95, "rijswijk": 1.00, "zoetermeer": 0.98,
    "westland": 1.00, "pijnacker-nootdorp": 1.02, "capelle aan den ijssel": 0.98,
}

_PC4_RE = re.compile(r"([1-9]\d{3})")


def _wijk_multiplier(postcode: str, stad: str) -> tuple[float, str]:
    """Retourneer (factor, bron-label) voor renovatie-kosten aanpassing."""
    if postcode:
        m = _PC4_RE.search(postcode.upper().replace(" ", ""))
        if m:
            pc4 = int(m.group(1))
            if pc4 in _WIJK_MULT_PC4:
                return _WIJK_MULT_PC4[pc4], f"PC4 {pc4}"
    stad_n = (stad or "").lower().strip()
    if stad_n in _WIJK_MULT_STAD:
        return _WIJK_MULT_STAD[stad_n], f"stad {stad}"
    return 1.0, "landelijk"


def schat_renovatie(
    opp_m2: int,
    bouwjaar: int = 0,
    energie_label: str = "",
    type_woning: str = "",
    is_opknapper: bool = False,
    postcode: str = "",
    stad: str = "",
) -> dict:
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
            "naam": "Keuken compleet nieuw (midden)",
            "kosten": 18_000,
            "reden": "Volledige keuken met apparatuur, tegels, aanrechtblad, leidingwerk",
        })
    elif slecht_label or matig_label:
        componenten.append({
            "naam": "Keuken renovatie",
            "kosten": 14_000,
            "reden": "Nieuwe fronten, apparatuur, blad, tegelwerk",
        })
    else:
        componenten.append({
            "naam": "Keuken opfrissen",
            "kosten": 8_000,
            "reden": "Nieuwe fronten, werkblad, apparatuur behouden",
        })

    # ── 2. BADKAMER ──
    if is_opknapper or is_oud:
        componenten.append({
            "naam": "Badkamer compleet nieuw (midden)",
            "kosten": 15_000,
            "reden": "Strippen, tegels wand+vloer, sanitair, leidingwerk, vloerverwarming",
        })
    elif slecht_label or matig_label:
        componenten.append({
            "naam": "Badkamer renovatie",
            "kosten": 12_000,
            "reden": "Nieuwe tegels, sanitair, kranen",
        })
    else:
        componenten.append({
            "naam": "Badkamer opfrissen",
            "kosten": 7_000,
            "reden": "Sanitair + kranen vervangen, voegen vernieuwen",
        })

    # ── 3. TOILET ──
    if is_opknapper or is_oud:
        componenten.append({
            "naam": "Toilet compleet nieuw",
            "kosten": 4_000,
            "reden": "Tegels wand+vloer, hang-WC, fontein, spiegel, kraan, arbeid",
        })
    else:
        componenten.append({
            "naam": "Toilet opknappen",
            "kosten": 2_500,
            "reden": "Nieuwe WC pot, fontein, kleine tegelreparaties",
        })

    # ── 4. VLOEREN (PVC click = meest gangbaar voor flip) ──
    if is_opknapper or is_heel_oud:
        kosten_m2 = 85  # egaliseren + PVC click midden
        reden = "Ondervloer egaliseren + PVC click vloer (midden kwaliteit)"
    elif is_oud or slecht_label:
        kosten_m2 = 70
        reden = "Egaliseren + PVC click vloer leggen"
    elif matig_label:
        kosten_m2 = 60
        reden = "PVC click vloer leggen (licht egaliseren)"
    else:
        kosten_m2 = 50
        reden = "Nieuwe PVC click vloer leggen"
    componenten.append({
        "naam": f"Vloeren ({kosten_m2}/m\u00b2)",
        "kosten": m2 * kosten_m2,
        "reden": reden,
    })

    # ── 5. SCHILDERWERK + WANDEN + PLAFONDS ──
    if is_opknapper or is_heel_oud:
        kosten_m2 = 45  # volledig: stucwerk repareren + latex + houtwerk
        reden = "Stucwerk herstellen, latex muren+plafonds, houtwerk+kozijnen+deuren"
    elif is_oud or slecht_label:
        kosten_m2 = 35
        reden = "Latex muren+plafonds + binnenkozijnen schilderen"
    else:
        kosten_m2 = 20
        reden = "Latex muren en plafonds"
    componenten.append({
        "naam": f"Schilderwerk ({kosten_m2}/m\u00b2)",
        "kosten": m2 * kosten_m2,
        "reden": reden,
    })

    # ── 6. ELEKTRA ──
    if is_heel_oud:
        kosten = max(8_000, m2 * 120)
        componenten.append({
            "naam": "Elektra volledig vernieuwen",
            "kosten": kosten,
            "reden": f"Bj {bj}: groepenkast + alle bedrading + stopcontacten ({kosten})",
        })
    elif is_oud:
        componenten.append({
            "naam": "Elektra grotendeels vernieuwen",
            "kosten": max(5_000, m2 * 80),
            "reden": f"Bj {bj}: groepenkast + deels bedrading",
        })
    elif slecht_label or matig_label:
        componenten.append({
            "naam": "Elektra upgraden",
            "kosten": 3_500,
            "reden": "Groepenkast + extra groepen + stopcontacten",
        })
    else:
        componenten.append({
            "naam": "Elektra check + uitbreiden",
            "kosten": 1_500,
            "reden": "Keuring + extra groepen/stopcontacten",
        })

    # ── 7. LEIDINGWERK ──
    if is_heel_oud:
        kosten = max(5_000, m2 * 50)
        componenten.append({
            "naam": "Leidingwerk vervangen",
            "kosten": kosten,
            "reden": f"Bj {bj}: water + afvoer volledig vervangen",
        })
    elif is_oud:
        componenten.append({
            "naam": "Leidingwerk deels vervangen",
            "kosten": 3_000,
            "reden": f"Bj {bj}: waterleiding deels + afvoer check",
        })
    elif slecht_label:
        componenten.append({
            "naam": "Leidingwerk aanpassen",
            "kosten": 2_000,
            "reden": "Verouderd leidingwerk bijwerken",
        })

    # ── 8. ISOLATIE ──
    if slecht_label or (label == "" and (not bj or bj < 1990)):
        dak_iso = m2 * 0.5 * 55   # halve m2 = dakoppervlak, €55/m2 binnenzijde
        vloer_iso = m2 * 30        # €30/m2
        spouw_iso = m2 * 0.7 * 25  # geveloppervlak schatting, €25/m2
        iso_totaal = int(dak_iso + vloer_iso + spouw_iso)
        componenten.append({
            "naam": "Isolatie (dak+vloer+spouw)",
            "kosten": iso_totaal,
            "reden": f"Label {label or '?'}: dak {int(dak_iso)}, vloer {int(vloer_iso)}, spouw {int(spouw_iso)}",
        })
    elif matig_label:
        iso_totaal = int(m2 * 40)
        componenten.append({
            "naam": "Isolatie verbeteren",
            "kosten": iso_totaal,
            "reden": f"Label {label}: dak + vloer bijwerken",
        })

    # ── 9. RAMEN/KOZIJNEN ──
    if slecht_label or (bj and bj < 1980):
        n_ramen = max(8, m2 // 8)
        kosten_raam = 1_500  # HR++ incl kozijn gemiddeld
        componenten.append({
            "naam": f"Ramen HR++ ({n_ramen}x)",
            "kosten": n_ramen * kosten_raam,
            "reden": f"Enkel/dubbel glas naar HR++ incl nieuwe kozijnen",
        })
    elif matig_label or (bj and bj < 1995):
        n_ramen = max(4, m2 // 15)
        componenten.append({
            "naam": f"Ramen deels ({n_ramen}x)",
            "kosten": n_ramen * 1_200,
            "reden": "Oudere ramen upgraden naar HR++",
        })

    # ── 10. CV / VERWARMING ──
    if slecht_label or (bj and bj < 1990):
        componenten.append({
            "naam": "CV-ketel nieuw (HR-combi)",
            "kosten": 2_200,
            "reden": "Nieuwe HR-combi ketel incl installatie",
        })
        if m2 > 80:
            n_rad = max(5, m2 // 15)
            componenten.append({
                "naam": f"Radiatoren ({n_rad}x)",
                "kosten": n_rad * 180,
                "reden": f"Oude radiatoren vervangen ({n_rad} stuks)",
            })
    elif matig_label:
        componenten.append({
            "naam": "CV-ketel onderhoud/reserve",
            "kosten": 1_500,
            "reden": "Mogelijk verouderd, budget voor vervanging",
        })

    # ── 11. DAK ──
    if is_heel_oud:
        dak_m2 = int(m2 * 0.5)
        componenten.append({
            "naam": "Dak renovatie",
            "kosten": max(8_000, dak_m2 * 110),
            "reden": f"Bj {bj}: dakbedekking + isolatie vernieuwen ({dak_m2}m2)",
        })
    elif is_oud:
        componenten.append({
            "naam": "Dak reparatie",
            "kosten": 4_000,
            "reden": f"Bj {bj}: dakpannen check + kleine reparaties",
        })

    # ── 12. BUITENWERK ──
    if is_oud:
        componenten.append({
            "naam": "Buitenwerk (voegen+schilderwerk)",
            "kosten": max(5_000, int(m2 * 45)),
            "reden": "Voegwerk repareren + kozijnen buiten schilderen",
        })
    else:
        componenten.append({
            "naam": "Buitenschilderwerk",
            "kosten": 2_500,
            "reden": "Kozijnen buiten schilderen",
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
        "reden": "Buffer voor verrassingen (asbest, fundering, verborgen gebreken)",
    })

    # ── 14. ARCHITECT + LEGES ──
    arch_pct = 8 if (is_oud or slecht_label) else 6
    arch = int(subtotaal * arch_pct / 100)
    componenten.append({
        "naam": f"Architect + leges ({arch_pct}%)",
        "kosten": arch,
        "reden": "Ontwerp, vergunning, bouwbegeleiding",
    })

    subtotaal_pre_wijk = sum(c["kosten"] for c in componenten)

    # Wijk-multiplier: lokale aannemersprijzen en welstandseisen.
    wijk_factor, wijk_bron = _wijk_multiplier(postcode, stad)
    if wijk_factor != 1.0:
        # Pas elke component aan behalve onvoorzien/architect (die schalen
        # mee automatisch via het subtotaal — we herbereken ze hieronder).
        # Bewaar origineel kost-veld voor audit.
        for c in componenten:
            c["kosten_basis"] = c["kosten"]
            # Onvoorzien + architect zijn % over subtotaal — niet apart schalen
            if c["naam"].startswith("Onvoorzien") or c["naam"].startswith("Architect"):
                continue
            c["kosten"] = int(c["kosten"] * wijk_factor)
        # Herbereken onvoorzien + architect op nieuwe subtotaal
        subtotaal_new = sum(
            c["kosten"] for c in componenten
            if not c["naam"].startswith("Onvoorzien") and not c["naam"].startswith("Architect")
        )
        for c in componenten:
            if c["naam"].startswith("Onvoorzien"):
                c["kosten"] = int(subtotaal_new * onvoorzien_pct / 100)
            elif c["naam"].startswith("Architect"):
                c["kosten"] = int(subtotaal_new * arch_pct / 100)

    totaal = sum(c["kosten"] for c in componenten)
    per_m2 = round(totaal / m2)

    logger.info(
        "Renovatie %dm2 bj%s label%s wijk=%s(%.2fx): %d/m2 (totaal %d)",
        m2, bj or "?", label or "?", wijk_bron, wijk_factor, per_m2, totaal,
    )

    return {
        "componenten": componenten,
        "totaal": totaal,
        "per_m2": per_m2,
        "onvoorzien_pct": onvoorzien_pct,
        "wijk_factor": round(wijk_factor, 3),
        "wijk_bron": wijk_bron,
    }
