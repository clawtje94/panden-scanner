"""
Erfpacht-detectie en analyse.

Parse erfpacht-condities uit Funda-beschrijving (jaartallen, canon, eeuwigdurend)
en flagt speciale situaties per stad:

  Rotterdam (per 2026): eenmalige afkoop-regeling voor max 60% grondwaarde —
    panden met erfpacht krijgen een directe arbitrage-flag.
  Den Haag: canon 3,3% (AB 1986), eeuwigdurend. Primair canon-afkoopbeoordeling.
  Amsterdam en kleinere gemeentes: alleen detectie, geen specifieke arbitrage.

Als erfpacht tijdelijk én eindjaar < 30 jaar in toekomst = rode vlag (pand
wordt op afloop veel minder waard, tenzij afkoop geregeld).
"""
from __future__ import annotations

import re
from typing import Optional

# Keywords die duiden op erfpacht
ERFPACHT_KEYWORDS = ("erfpacht", "canon", "voortdurende erfpacht", "tijdelijke erfpacht")
EEUWIGDUREND_KEYWORDS = ("eeuwigdurend", "voor onbepaalde tijd", "afgekocht voor altijd", "eeuwig afgekocht")
AFGEKOCHT_KEYWORDS = ("afgekocht", "afkoop", "volledig afgekocht", "canon afgekocht")
EIGEN_GROND = ("eigen grond",)

# Erfpacht-eindjaar patroon: "tot 2068", "eindigt in 2068", "einddatum 31-12-2068"
EINDJAAR_RE = re.compile(
    r"(?:tot|eindigt?\s*(?:in|op)?|einddatum|expiratie|eindjaar|looptijd\s*t/?m)[^0-9]{0,20}(\d{4})",
    re.IGNORECASE,
)
CANON_EUR_RE = re.compile(r"canon[^€\d]{0,30}€?\s*([\d.,]+)", re.IGNORECASE)

# Rotterdam (60% afkoop 2026) en Den Haag (3,3% canon AB1986) — primaire markten
ROTTERDAM_STEDEN = {"rotterdam"}
DEN_HAAG_STEDEN = {"den haag", "'s-gravenhage", "s-gravenhage"}


def detect_erfpacht(beschrijving: str, stad: str = "") -> dict:
    """Analyseer erfpacht-situatie uit Funda-beschrijving.

    Returns:
        dict met:
          - is_erfpacht: bool
          - is_eeuwigdurend: bool
          - is_afgekocht: bool
          - eindjaar: int | None   (als tijdelijke erfpacht)
          - jaren_resterend: int | None  (vanaf huidig jaar)
          - canon_euro: float | None
          - rotterdam_afkoopkans: bool  (60% afkoop-regeling 2026)
          - risk_level: 'geen' | 'laag' | 'middel' | 'hoog'
          - toelichting: str
    """
    result = {
        "is_erfpacht": False,
        "is_eeuwigdurend": False,
        "is_afgekocht": False,
        "eindjaar": None,
        "jaren_resterend": None,
        "canon_euro": None,
        "rotterdam_afkoopkans": False,
        "risk_level": "geen",
        "toelichting": "",
    }
    if not beschrijving:
        return result

    tekst = beschrijving.lower()
    stad_n = stad.lower().strip()

    # "Eigen grond" (evt gecombineerd met "geen erfpacht") → geen erfpacht
    if any(kw in tekst for kw in EIGEN_GROND):
        result["toelichting"] = "Eigen grond — geen erfpacht."
        return result

    # Expliciet "geen erfpacht" → geen erfpacht
    import re as _re
    if _re.search(r"geen\s+erfpacht|niet\s+op\s+erfpacht", tekst):
        result["toelichting"] = "Expliciet 'geen erfpacht' vermeld."
        return result

    if not any(kw in tekst for kw in ERFPACHT_KEYWORDS):
        return result

    result["is_erfpacht"] = True
    result["is_eeuwigdurend"] = any(kw in tekst for kw in EEUWIGDUREND_KEYWORDS)
    result["is_afgekocht"] = any(kw in tekst for kw in AFGEKOCHT_KEYWORDS)

    # Eindjaar zoeken (alleen relevant bij tijdelijke erfpacht)
    m = EINDJAAR_RE.search(tekst)
    if m and not result["is_eeuwigdurend"]:
        try:
            jaar = int(m.group(1))
            if 2025 <= jaar <= 2200:  # sanity range
                result["eindjaar"] = jaar
                # Huidig jaar fallback (bij runtime: datetime.now().year)
                from datetime import datetime
                result["jaren_resterend"] = jaar - datetime.now().year
        except Exception:
            pass

    # Canon
    cm = CANON_EUR_RE.search(tekst)
    if cm:
        try:
            raw = cm.group(1).replace(".", "").replace(",", ".")
            result["canon_euro"] = round(float(raw), 2)
        except Exception:
            pass

    # Rotterdam-arbitrage: afkoop tot 60% grondwaarde is een eenmalige
    # regeling 2026 en relevant als pand nu erfpacht heeft en niet afgekocht is.
    if stad_n in ROTTERDAM_STEDEN and result["is_erfpacht"] and not result["is_afgekocht"]:
        result["rotterdam_afkoopkans"] = True

    # Risk-level
    if result["is_afgekocht"] or result["is_eeuwigdurend"]:
        result["risk_level"] = "laag"
        result["toelichting"] = "Erfpacht, maar afgekocht/eeuwigdurend — beperkt risico."
    elif result["jaren_resterend"] is not None:
        jr = result["jaren_resterend"]
        if jr < 15:
            result["risk_level"] = "hoog"
            result["toelichting"] = (
                f"Tijdelijke erfpacht, nog {jr} jaar — forse waarde-afslag dreigt."
            )
        elif jr < 30:
            result["risk_level"] = "middel"
            result["toelichting"] = (
                f"Tijdelijke erfpacht, nog {jr} jaar — canon-heronderhandeling risico."
            )
        else:
            result["risk_level"] = "laag"
            result["toelichting"] = f"Tijdelijke erfpacht met {jr} jaar resterend."
    else:
        result["risk_level"] = "middel"
        result["toelichting"] = "Erfpacht gedetecteerd — looptijd onbekend, check akte."

    if result["rotterdam_afkoopkans"]:
        result["toelichting"] += (
            " Rotterdam: eenmalige afkoop-regeling 2026 (60% grondwaarde) — "
            "mogelijke arbitragekans."
        )

    return result
