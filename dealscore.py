"""
Composite dealscore (0-100).

Één getal per pand dat in één oogopslag zegt: hoe goed is deze deal?
Bedoeld voor snelle triage bij honderden leads. Hoge score = belangrijk om
nu te bekijken, lage score = niet vandaag.

Componenten:
  - marge_pct             0-40 punten (schaalt lineair tot 30% marge)
  - motivated_score       0-20 punten (prijsverlaging, dagen online, etc)
  - forced_renovation     0-10 punten (leverage in onderhandeling)
  - splits_wijk_kans      0-10 punten (DH 1-4-2026 of RDAM versoepeld)
  - erfpacht_afkoopkans   0-5  punten (Rotterdam 60% regeling)
  - score_basis (1-10)    0-15 punten (bestaande kwaliteits-score)

Aftrekposten:
  - verhuurd            : hard naar 0 (geen ontwikkeling)
  - rijksmonument       : -10 (dure renovatie)
  - BAG niet woonfunctie: -15
  - erfpacht hoog risico: -15

Clipped op [0, 100].
"""
from __future__ import annotations

from typing import Optional


def bereken_dealscore(
    marge_pct: float = 0,
    score_basis: int = 0,
    motion: Optional[dict] = None,
    ep_online: Optional[dict] = None,
    erfpacht: Optional[dict] = None,
    risks: Optional[dict] = None,
    wijkcheck: Optional[dict] = None,
) -> dict:
    """Bereken dealscore en retourneer breakdown.

    Returns:
        dict met:
          - score: int (0-100)
          - breakdown: list[{onderdeel, punten, uitleg}]
          - grade: 'A+' | 'A' | 'B' | 'C' | 'D'
    """
    breakdown = []
    totaal = 0

    # Harde kill switches
    if risks:
        for f in risks.get("flags", []):
            if f["niveau"] == "rood" and "verhuurd" in f["label"].lower():
                return {
                    "score": 0,
                    "grade": "D",
                    "breakdown": [{
                        "onderdeel": "KILL",
                        "punten": 0,
                        "uitleg": "Verhuurd — geen ontwikkelkans",
                    }],
                }

    # ── Marge (tot 40 pt, schaalt lineair tot 30% marge) ──
    pt_marge = min(40, max(0, int(marge_pct * 40 / 30))) if marge_pct > 0 else 0
    breakdown.append({
        "onderdeel": "Marge",
        "punten": pt_marge,
        "uitleg": f"{marge_pct}% → {pt_marge}/40",
    })
    totaal += pt_marge

    # ── Motion (tot 20 pt) ──
    m_score = (motion or {}).get("motivated_score", 0) if motion else 0
    pt_motion = min(20, m_score * 2)  # motivated_score 0-10 → 0-20 pt
    if pt_motion:
        uitleg = f"motivated_score {m_score}/10"
        if (motion or {}).get("prijsverlaging_pct", 0) >= 5:
            uitleg += f" (prijs -{motion['prijsverlaging_pct']}%)"
        breakdown.append({
            "onderdeel": "Motion signalen",
            "punten": pt_motion,
            "uitleg": uitleg,
        })
        totaal += pt_motion

    # ── Forced renovation leverage (tot 10 pt) ──
    if ep_online:
        if ep_online.get("forced_renovation_sterk"):
            breakdown.append({
                "onderdeel": "Forced reno (sterk)",
                "punten": 10,
                "uitleg": f"Label {ep_online.get('label', '?')} + pre-1992 bouwjaar",
            })
            totaal += 10
        elif ep_online.get("forced_renovation"):
            breakdown.append({
                "onderdeel": "Forced reno",
                "punten": 6,
                "uitleg": f"Label {ep_online.get('label', '?')} — verhuurverbod 2028",
            })
            totaal += 6

    # ── Splits-wijk kans (tot 10 pt) ──
    if wijkcheck and wijkcheck.get("mag") is True:
        regime = wijkcheck.get("regime", "")
        pt = 10 if regime == "den_haag_2026" else 6 if regime == "rotterdam_2025" else 0
        if pt:
            breakdown.append({
                "onderdeel": "Splits-wijk",
                "punten": pt,
                "uitleg": f"{regime} — wijkcheck OK",
            })
            totaal += pt

    # ── Erfpacht afkoopkans Rotterdam (5 pt) ──
    if erfpacht and erfpacht.get("rotterdam_afkoopkans"):
        breakdown.append({
            "onderdeel": "RDAM erfpacht-afkoop",
            "punten": 5,
            "uitleg": "60% regeling 2026",
        })
        totaal += 5

    # ── Basis-score (tot 15 pt, schaal 1-10 → 0-15) ──
    if score_basis:
        pt_basis = min(15, int(score_basis * 1.5))
        breakdown.append({
            "onderdeel": "Kwaliteitsscore",
            "punten": pt_basis,
            "uitleg": f"{score_basis}/10 (bouwjaar/label/eigen grond/etc)",
        })
        totaal += pt_basis

    # ── Aftrekposten ──
    if risks:
        for f in risks.get("flags", []):
            niveau = f["niveau"]
            label = f["label"].lower()
            if "rijksmonument" in label:
                breakdown.append({"onderdeel": "Monument", "punten": -10, "uitleg": f["label"]})
                totaal -= 10
            elif niveau == "rood" and "bag:" in label:
                breakdown.append({"onderdeel": "Geen BAG-woonfunctie", "punten": -15, "uitleg": f["label"]})
                totaal -= 15
            elif niveau == "rood" and "erfpacht (hoog)" in label:
                breakdown.append({"onderdeel": "Erfpacht hoog risico", "punten": -15, "uitleg": f["label"]})
                totaal -= 15
            elif niveau == "oranje" and "oppervlak afwijking" in label:
                breakdown.append({"onderdeel": "Oppervlak-mismatch", "punten": -5, "uitleg": f["label"]})
                totaal -= 5

    totaal = max(0, min(100, totaal))
    grade = (
        "A+" if totaal >= 85 else
        "A" if totaal >= 70 else
        "B" if totaal >= 55 else
        "C" if totaal >= 40 else
        "D"
    )
    return {"score": totaal, "grade": grade, "breakdown": breakdown}
