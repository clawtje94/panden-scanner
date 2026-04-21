"""
Referentieprijs-engine v2.

Doel: realistische verkoopprijs/m² na renovatie voor een pand, met expliciete
betrouwbaarheids-score zodat Bateau een deal niet op valse voorspelling doet.

Wat er beter is dan v1:
  - Energielabel-filter (A/B/C = gerenoveerde proxy) ipv "bovenste helft"
  - Days-on-market filter (> 120d = onverkoopbare vraagprijs, uitsluiten)
  - PC6 primaire match, PC4 fallback, stad als laatste redmiddel
  - Meerdere match-niveaus worden gescoord → confidence
  - P25/P50/P75 scenarios ipv 1 getal — dealscore op worst-case (P25)
  - Audit-log: per kandidaat waarom wel/niet meegenomen
  - Days-online signaal → feedback op verwachte verkooptijd (looptijd)

Filter-cascade (van strict naar loose, stopt bij eerste succes met genoeg N):
  1. PC6 + label A/B/C + ≤120 dagen online
  2. PC6 + alle labels + ≤120 dagen
  3. PC4 + label A/B/C + ≤120 dagen
  4. PC4 + alle labels + ≤120 dagen
  5. PC4 + alle labels + alle dagen
  6. Stad + label A/B/C + ≤120 dagen
  7. Stad + alles (laatste redmiddel)

`MIN_REFS_PER_LEVEL` bepaalt wanneer we door-cascaden (default 5). Meer is
beter, maar in dunne markten pakken we ook 3.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import List, Tuple, Optional
from statistics import median

from funda import Funda

logger = logging.getLogger(__name__)

# ── Tunables ─────────────────────────────────────────────────────────────────
HIGH_LABELS = {"A", "A+", "A++", "A+++", "A++++", "A+++++", "B", "C"}
MAX_DAYS_ON_MARKET_DEFAULT = 120
MIN_REFS_PER_LEVEL = 5           # vanaf hier stoppen met verder zoeken
MIN_REFS_ACCEPTED = 3             # minder dan dit = geen data
MIN_REFS_HIGH_CONFIDENCE = 10
MIN_FRACTION_HIGH_LABEL = 0.4     # 40% met A/B/C = goede spread

# Simple process-cache (per scanner-run)
_cache: dict = {}
_funda: Funda | None = None


def _get_funda() -> Funda:
    global _funda
    if _funda is None:
        _funda = Funda()
    return _funda


def _bepaal_funda_type(type_woning: str, opp_m2: int) -> str:
    t = (type_woning or "").lower()
    if any(kw in t for kw in ["appartement", "apartment", "flat", "portiek", "bovenwoning",
                                "benedenwoning", "maisonnette", "penthouse", "etage", "galerij"]):
        return "apartment"
    if any(kw in t for kw in ["huis", "house", "woonhuis", "tussenwoning", "hoekwoning",
                                "twee-onder-een-kap", "vrijstaand", "geschakeld",
                                "herenhuis", "villa", "bungalow", "eengezins"]):
        return "house"
    return "apartment" if opp_m2 < 120 else "house"


def _days_online(publish_date: str) -> Optional[int]:
    """Parse Funda publish_date (ISO met offset) naar dagen sinds publicatie."""
    if not publish_date:
        return None
    try:
        dt = datetime.fromisoformat(publish_date.replace("Z", "+00:00"))
        now = datetime.now(tz=dt.tzinfo or timezone.utc)
        return max(0, (now - dt).days)
    except Exception:
        return None


def _percentiel(waarden: List[float], p: int) -> float:
    if not waarden:
        return 0.0
    s = sorted(waarden)
    k = (len(s) - 1) * p / 100
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    frac = k - lo
    return s[lo] * (1 - frac) + s[hi] * frac


def _match_niveau_score(niv: str) -> int:
    """Heuristisch: hoe strict was de match?"""
    return {
        "pc6_label_fresh": 10, "pc6_all_fresh": 8,
        "pc4_label_fresh": 7,  "pc4_all_fresh": 5, "pc4_all_any": 3,
        "stad_label_fresh": 2, "stad_all_any": 1,
    }.get(niv, 0)


def _search(funda, location, min_opp, max_opp, funda_type, max_price=2_500_000):
    """Veilige Funda search-wrapper."""
    try:
        return funda.search_listing(
            location=location,
            offering_type="buy",
            price_min=50_000,
            price_max=max_price,
            area_min=min_opp,
            area_max=max_opp,
            object_type=[funda_type],
            sort="newest",
            page=0,
        ) or []
    except Exception as e:
        logger.debug("Funda search fout %s: %s", location, e)
        return []


def _to_ref(listing) -> Optional[dict]:
    """Funda Listing → ons dict-formaat."""
    d = listing.data if hasattr(listing, "data") else listing
    prijs = d.get("price") or 0
    opp = d.get("living_area") or 0
    if prijs <= 0 or opp <= 0:
        return None
    pm2 = round(prijs / opp)
    label_raw = (d.get("energy_label") or "").strip().upper()
    # Normalize A+, A++, etc. to "A"-family
    label = label_raw[:1] if label_raw else ""
    days = _days_online(d.get("publish_date"))
    detail_url = d.get("detail_url") or ""
    url = "https://www.funda.nl" + detail_url if detail_url and not detail_url.startswith("http") else detail_url
    return {
        "adres": d.get("title") or "",
        "prijs": int(prijs),
        "opp_m2": int(opp),
        "prijs_per_m2": pm2,
        "energie_label": label_raw or "?",
        "is_high_label": label in HIGH_LABELS or label_raw in HIGH_LABELS,
        "days_online": days,
        "is_fresh": (days is not None and days <= MAX_DAYS_ON_MARKET_DEFAULT),
        "postcode": d.get("postcode") or "",
        "neighbourhood": d.get("neighbourhood") or "",
        "type": d.get("object_type") or "",
        "url": url,
        "broker": d.get("broker_name") or "",
    }


def _cascade_search(funda, stad_slug, pc4, pc6, min_opp, max_opp, funda_type):
    """Doorloop filter-cascade. Retourneert (refs, audit, match_niveau)."""
    cascade = []
    if pc6:
        cascade.append(("pc6_label_fresh", pc6, True, True))
        cascade.append(("pc6_all_fresh", pc6, False, True))
    if pc4:
        cascade.append(("pc4_label_fresh", pc4, True, True))
        cascade.append(("pc4_all_fresh", pc4, False, True))
        cascade.append(("pc4_all_any", pc4, False, False))
    if stad_slug:
        cascade.append(("stad_label_fresh", stad_slug, True, True))
        cascade.append(("stad_all_any", stad_slug, False, False))

    audit = []
    for niveau, loc, req_label, req_fresh in cascade:
        raw = _search(funda, loc, min_opp, max_opp, funda_type)
        if not raw:
            audit.append({"niveau": niveau, "loc": loc, "n_raw": 0, "n_passed": 0})
            continue

        cand = []
        for listing in raw:
            r = _to_ref(listing)
            if not r:
                continue
            cand.append(r)

        passed = []
        for r in cand:
            reasons = []
            if req_label and not r["is_high_label"]:
                reasons.append(f"label={r['energie_label']}")
            if req_fresh and r["is_fresh"] is False:
                reasons.append(f"days={r['days_online']}")
            if reasons:
                r["_excluded_reason"] = ";".join(reasons)
            else:
                passed.append(r)
        audit.append({
            "niveau": niveau, "loc": loc,
            "n_raw": len(cand), "n_passed": len(passed),
            "req_label": req_label, "req_fresh": req_fresh,
        })

        if len(passed) >= MIN_REFS_ACCEPTED:
            # Kleine pauze alleen bij daadwerkelijke hit
            time.sleep(0.2)
            return passed, audit, niveau

        # Te weinig — ga door naar volgend niveau
        time.sleep(0.15)

    return [], audit, "geen"


def _confidence_score(n: int, spread_pct: float, high_label_frac: float,
                       match_niveau: str, avg_days: Optional[float]) -> int:
    """Confidence 0-100 op basis van 4 dimensies."""
    score = 0
    # N (max 30)
    score += min(30, int(n * 3)) if n <= 10 else 30
    # Spread (max 25) — smaller = better. spread_pct = (p75 - p25) / p50 * 100
    if spread_pct <= 10: score += 25
    elif spread_pct <= 20: score += 18
    elif spread_pct <= 35: score += 10
    elif spread_pct <= 50: score += 4
    # High-label fraction (max 20)
    score += int(high_label_frac * 20) if high_label_frac <= 1 else 20
    # Match niveau (max 15)
    score += min(15, _match_niveau_score(match_niveau))
    # Days on market (max 10) — verser = meer confidence
    if avg_days is not None:
        if avg_days <= 45: score += 10
        elif avg_days <= 90: score += 6
        elif avg_days <= 180: score += 2
    return min(100, score)


def zoek_vergelijkbare(
    stad: str,
    opp_m2: int,
    strategie: str = "fix_flip",
    type_woning: str = "",
    postcode: str = "",
) -> Tuple[float, List[dict]]:
    """Backwards-compat wrapper: retourneert (P50 pm2, top5 refs).

    Voor rijkere data (scenarios, confidence, audit) gebruik
    `zoek_vergelijkbare_detail`.
    """
    detail = zoek_vergelijkbare_detail(stad, opp_m2, type_woning, postcode)
    return (detail["p50_pm2"], detail["top"])


def zoek_vergelijkbare_detail(
    stad: str,
    opp_m2: int,
    type_woning: str = "",
    postcode: str = "",
) -> dict:
    """Zoek referenties met volledige breakdown.

    Returns:
        {
          'p25_pm2': float,    # pessimistisch (verkoop zonder top-afwerking)
          'p50_pm2': float,    # realistisch (mediaan)
          'p75_pm2': float,    # optimistisch (gerenoveerd top-segment)
          'gem_pm2': float,    # rekenkundig gemiddelde (legacy)
          'n_refs': int,
          'n_total_seen': int,
          'n_high_label': int,
          'avg_days_online': float | None,
          'spread_pct': float,  # (P75-P25)/P50
          'match_niveau': str,
          'confidence': int (0-100),
          'confidence_label': 'hoog' | 'middel' | 'laag' | 'onvoldoende',
          'top': [top-5 panden met details],
          'audit': list[per cascade-stap wat er gebeurde],
          'waarschuwingen': list[str],
        }
    """
    funda_type = _bepaal_funda_type(type_woning, opp_m2)
    pc_clean = (postcode or "").replace(" ", "").upper()
    pc4 = pc_clean[:4] if len(pc_clean) >= 4 else ""
    pc6 = pc_clean if len(pc_clean) == 6 else ""
    stad_slug = stad.lower().replace(" ", "-").strip() if stad else ""
    cache_key = f"{pc6 or pc4 or stad_slug}|{opp_m2}|{funda_type}"
    if cache_key in _cache:
        return _cache[cache_key]

    min_opp = max(30, int(opp_m2 * 0.7))
    max_opp = int(opp_m2 * 1.3)

    refs, audit, niveau = _cascade_search(
        _get_funda(), stad_slug, pc4, pc6, min_opp, max_opp, funda_type,
    )

    waarschuwingen = []
    if not refs:
        result = _empty_result(waarschuwingen + [
            "Geen vergelijkbare panden gevonden — verkoop-schatting valt terug op config",
        ], audit)
        _cache[cache_key] = result
        return result

    # Sorteer en compute percentielen
    pm2s = sorted(r["prijs_per_m2"] for r in refs)
    p25 = _percentiel(pm2s, 25)
    p50 = _percentiel(pm2s, 50)
    p75 = _percentiel(pm2s, 75)
    gem = sum(pm2s) / len(pm2s)
    spread_pct = round((p75 - p25) / p50 * 100, 1) if p50 > 0 else 0.0
    n_high = sum(1 for r in refs if r["is_high_label"])
    frac_high = n_high / len(refs) if refs else 0.0
    days_vals = [r["days_online"] for r in refs if r["days_online"] is not None]
    avg_days = round(sum(days_vals) / len(days_vals), 1) if days_vals else None

    conf = _confidence_score(len(refs), spread_pct, frac_high, niveau, avg_days)
    conf_label = (
        "hoog" if conf >= 70 else
        "middel" if conf >= 50 else
        "laag" if conf >= 30 else
        "onvoldoende"
    )

    if len(refs) < MIN_REFS_HIGH_CONFIDENCE:
        waarschuwingen.append(f"Weinig referenties ({len(refs)}) — confidence gedrukt")
    if spread_pct > 35:
        waarschuwingen.append(f"Grote spread ({spread_pct}%) — wijk ongelijk")
    if frac_high < MIN_FRACTION_HIGH_LABEL:
        waarschuwingen.append(
            f"Maar {n_high}/{len(refs)} referenties met label A/B/C — "
            "post-renovatie prijs moeilijk te onderbouwen"
        )
    if avg_days and avg_days > 180:
        waarschuwingen.append(
            f"Gemiddeld {int(avg_days)} dagen online — traag verkopende wijk"
        )

    # Top 5: hoogste prijs/m² met label A/B/C indien mogelijk
    refs_sorted = sorted(
        refs,
        key=lambda r: (r["is_high_label"], r["prijs_per_m2"]),
        reverse=True,
    )
    top = refs_sorted[:5]

    # Wijk-label uit eerste referentie (voor UI)
    wijk = refs[0].get("neighbourhood", "")

    result = {
        "p25_pm2": round(p25),
        "p50_pm2": round(p50),
        "p75_pm2": round(p75),
        "gem_pm2": round(gem),
        "n_refs": len(refs),
        "n_total_seen": sum(a.get("n_raw", 0) for a in audit),
        "n_high_label": n_high,
        "avg_days_online": avg_days,
        "spread_pct": spread_pct,
        "match_niveau": niveau,
        "confidence": conf,
        "confidence_label": conf_label,
        "top": top,
        "audit": audit,
        "waarschuwingen": waarschuwingen,
        "wijk": wijk,
    }
    logger.info(
        "Referentie %s (%s, %d-%dm²): N=%d p50=%d p25=%d p75=%d conf=%d(%s) niveau=%s",
        pc6 or pc4 or stad_slug, funda_type, min_opp, max_opp,
        len(refs), result["p50_pm2"], result["p25_pm2"], result["p75_pm2"],
        conf, conf_label, niveau,
    )
    _cache[cache_key] = result
    return result


def _empty_result(waarschuwingen, audit):
    return {
        "p25_pm2": 0, "p50_pm2": 0, "p75_pm2": 0, "gem_pm2": 0,
        "n_refs": 0, "n_total_seen": sum(a.get("n_raw", 0) for a in audit),
        "n_high_label": 0, "avg_days_online": None, "spread_pct": 0.0,
        "match_niveau": "geen", "confidence": 0, "confidence_label": "onvoldoende",
        "top": [], "audit": audit, "waarschuwingen": waarschuwingen,
        "wijk": "",
    }
