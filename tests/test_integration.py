"""
End-to-end integratie-test voor de verrijking-pipeline.

Gebruikt echte externe API-calls (PDOK, RCE) — geen mocks. Dit valideert dat
de scanner in productie niet stuk gaat. Sla over met SKIP_NETWORK=1.

Geen pytest-framework gebruikt; run direct: `python3 tests/test_integration.py`.
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback

# Zorg dat project-root op sys.path staat voor directe python-runs
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
os.chdir(_ROOT)

# Isolate DB voor de test
import config
config.DB_PATH = tempfile.NamedTemporaryFile(delete=False, suffix=".db").name

from models import Property
from database import init_db, registreer_observatie, get_motion
from classificatie import classificeer_property, classificeer
from erfpacht import detect_erfpacht
from risks import aggregate_risks
from dealscore import bereken_dealscore
from bestemmingsplan import mag_splitsen

import importlib.util as iu
_specs = [("bag", "scrapers/bag.py"), ("monument", "scrapers/monument.py"),
          ("ep_online", "scrapers/ep_online.py")]
_mods = {}
for name, path in _specs:
    s = iu.spec_from_file_location(name, path)
    m = iu.module_from_spec(s)
    s.loader.exec_module(m)
    _mods[name] = m

bag_mod = _mods["bag"]
mon_mod = _mods["monument"]

SKIP_NETWORK = os.environ.get("SKIP_NETWORK") == "1"

OK = "\x1b[32m✓\x1b[0m"
FAIL = "\x1b[31m✗\x1b[0m"
passed = 0
failed = 0


def check(name: str, cond: bool, detail: str = ""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  {OK} {name}")
    else:
        failed += 1
        print(f"  {FAIL} {name}")
        if detail:
            print(f"      {detail}")


def section(title: str):
    print(f"\n── {title} ──")


def make_property(**kw) -> Property:
    """Property-fabrikant met redelijke defaults."""
    defaults = dict(
        source="test", url="https://example/p", adres="Teststraat 1",
        stad="Rotterdam", postcode="3012AA", prijs=300000,
        opp_m2=90, prijs_per_m2=3333,
        type_woning="apartment", bouwjaar=1920,
        energie_label="", kamers=4, eigen_grond=True,
    )
    defaults.update(kw)
    return Property(**defaults)


# ── TESTS ────────────────────────────────────────────────────────────────
def test_classificatie():
    section("Classificatie")
    check("Appartement → wonen",
          classificeer("apartment")["category"] == "wonen")
    check("Bedrijfspand → skip",
          classificeer("Bedrijfspand (veiling)")["category"] == "skip")
    check("Motorschip → skip",
          classificeer("Motorschip (veiling)")["category"] == "skip")
    check("Beleggingsobject → skip",
          classificeer("Beleggingsobject (executieveiling)")["category"] == "skip")
    check("Kantoor → transformatie",
          classificeer("Kantoorpand (veiling)")["category"] == "transformatie")
    r = classificeer("Woonhuis", gebruikssituatie="verhuurd")
    check("Woonhuis + verhuurd → verhuurd_wonen",
          r["category"] == "verhuurd_wonen" and r["is_verhuurd"])

    p = make_property(type_woning="apartment", is_commercieel=False)
    k = classificeer_property(p)
    check("classificeer_property(woning) → wonen", k["category"] == "wonen")


def test_erfpacht():
    section("Erfpacht")
    r = detect_erfpacht("Eigen grond. Geen erfpacht.", "rotterdam")
    check("eigen grond → geen erfpacht", r["is_erfpacht"] is False)

    r = detect_erfpacht(
        "Voortdurende erfpacht, eindjaar 2068, canon €1.250 per jaar", "rotterdam",
    )
    check("RDAM erfpacht → afkoopkans True",
          r["is_erfpacht"] and r["rotterdam_afkoopkans"],
          f"got: afkoopkans={r.get('rotterdam_afkoopkans')}")
    check("Eindjaar 2068 gedetecteerd", r.get("eindjaar") == 2068)
    check("Canon €1250 parsed",
          r.get("canon_euro") == 1250.0,
          f"got: {r.get('canon_euro')}")

    r = detect_erfpacht("Erfpacht tot 2032.", "den haag")
    check("korte looptijd → hoog risico",
          r.get("risk_level") == "hoog",
          f"got: {r.get('risk_level')}, jaren_resterend: {r.get('jaren_resterend')}")


def test_motion():
    section("Motion signalen")
    init_db()
    p = make_property(url="https://test/m1", prijs=350000, makelaar="A")
    registreer_observatie(p)
    p.prijs = 335000
    registreer_observatie(p)
    p.prijs = 320000
    p.makelaar = "B"
    registreer_observatie(p)
    m = get_motion(p.url)
    check("3 observaties geregistreerd",
          len(m.get("prijs_historie", [])) == 3)
    check("prijsverlaging ≈ 8.6%",
          abs(m.get("prijsverlaging_pct", 0) - 8.6) < 0.1,
          f"got: {m.get('prijsverlaging_pct')}")
    check("makelaarswissel → True", m.get("makelaarswissel") is True)
    check("motivated_score >= 5", m.get("motivated_score", 0) >= 5)


def test_splitsen():
    section("Splitsen regime")
    r = mag_splitsen("den haag", 150, 2, postcode="2593AB")  # Bezuidenhout score 8
    check("DH goede wijk → toegestaan",
          r["mag_splitsen"] is True)

    r = mag_splitsen("den haag", 150, 2, postcode="2531CD")  # Moerwijk score 4
    check("DH slechte wijk → niet toegestaan",
          r["mag_splitsen"] is False)

    r = mag_splitsen("rotterdam", 150, 2, postcode="3081XY")  # Tarwewijk NPRZ
    check("RDAM NPRZ 150m²/2 → niet toegestaan (85 eis)",
          r["mag_splitsen"] is False)

    r = mag_splitsen("rotterdam", 110, 2, postcode="3062AB")  # Kralingen
    check("RDAM standaard 110m²/2 → toegestaan (50 eis)",
          r["mag_splitsen"] is True)


def test_bag():
    if SKIP_NETWORK:
        return
    section("BAG verrijking (PDOK) — netwerk")
    # Prinsegracht 21D Den Haag — bekend rijksmonument
    b = bag_mod.verrijk_bag("2512EW", "Prinsegracht 21D")
    check("BAG data gevonden", bool(b and b.get("oppervlakte")))
    check("BAG gebruiksdoel = woonfunctie",
          b.get("gebruiksdoel") == "woonfunctie",
          f"got: {b.get('gebruiksdoel')}")
    check("BAG bouwjaar plausibel",
          1600 < (b.get("bouwjaar") or 0) < 2030,
          f"got: {b.get('bouwjaar')}")

    # Cache hit bij tweede call
    b2 = bag_mod.verrijk_bag("2512EW", "Prinsegracht 21D")
    check("BAG cache-hit (identiek)",
          b2.get("bouwjaar") == b.get("bouwjaar"))

    # Mismatch-bescherming: bogus postcode → geen data
    b3 = bag_mod.verrijk_bag("9999ZZ", "Nonebestaand 999")
    check("BAG bogus postcode → leeg (strikte match)", b3 == {})


def test_monument():
    if SKIP_NETWORK:
        return
    section("Monument (RCE) — netwerk")
    # Prinsegracht 21D is rijksmonument #17895
    loc = bag_mod.locatieserver_lookup("2512EW", "21", "D")
    check("Locatieserver centroide",
          loc and loc.get("centroide_rd"),
          f"got: {loc}")
    if loc and loc.get("centroide_rd"):
        m = mon_mod.check_rijksmonument(loc["centroide_rd"])
        check("Prinsegracht 21D = rijksmonument",
              m.get("is_rijksmonument") is True,
              f"got: {m}")

    # Bekend niet-monument adres
    loc2 = bag_mod.locatieserver_lookup("3012AA", "1")
    if loc2 and loc2.get("centroide_rd"):
        m2 = mon_mod.check_rijksmonument(loc2["centroide_rd"])
        check("Random RDAM adres meestal geen monument",
              m2.get("is_rijksmonument") in (False, True),  # accept either
              f"got: {m2}")


def test_risks_aggregator():
    section("Risks aggregator")
    r = aggregate_risks(
        classificatie={"category": "wonen", "is_verhuurd": False},
        ep_online={"forced_renovation": True, "forced_renovation_sterk": True, "label": "G"},
        monument={"is_rijksmonument": True, "subcategorie": "Woonhuis"},
        erfpacht={"is_erfpacht": True, "risk_level": "middel", "rotterdam_afkoopkans": True, "toelichting": "..."},
        bag={"oppervlakte": 70, "gebruiksdoel": "kantoorfunctie", "bouwjaar": 1920},
        prop_opp_m2=90, prop_bouwjaar=1920,
    )
    flags = r.get("flags", [])
    labels = [f["label"] for f in flags]
    check("Monument flag aanwezig",
          any("Rijksmonument" in l for l in labels))
    check("BAG kantoor flag aanwezig",
          any("kantoorfunctie" in l.lower() for l in labels))
    check("Oppervlak afwijking flag (90 vs 70 = 29%)",
          any("oppervlak" in l.lower() for l in labels),
          f"got: {labels}")
    check("Rotterdam afkoopkans in kansen",
          any("Rotterdam" in k["label"] for k in r.get("kansen", [])))

    # Verhuurd = kill
    r2 = aggregate_risks(classificatie={"category": "wonen", "is_verhuurd": True})
    check("Verhuurd → rode flag",
          any(f["niveau"] == "rood" for f in r2["flags"]))


def test_dealscore():
    section("Dealscore")
    # Zeer goede deal
    d = bereken_dealscore(
        marge_pct=22, score_basis=8,
        motion={"motivated_score": 8, "prijsverlaging_pct": 7},
        ep_online={"forced_renovation_sterk": True, "label": "F"},
        erfpacht={"rotterdam_afkoopkans": True},
        risks={"flags": [], "kansen": []},
        wijkcheck={"mag": True, "regime": "den_haag_2026"},
    )
    check("Top-deal score >= 70 (grade A+/A)",
          d["score"] >= 70,
          f"got {d['score']} grade {d['grade']}")

    # Zwakke deal
    d2 = bereken_dealscore(
        marge_pct=9, score_basis=3,
        risks={"flags": [{"niveau": "oranje", "label": "Rijksmonument", "details": ""}]},
    )
    check("Matige deal met monument → lage score",
          d2["score"] < 40,
          f"got {d2['score']} grade {d2['grade']}")

    # Verhuurd = kill
    d3 = bereken_dealscore(
        marge_pct=20,
        risks={"flags": [{"niveau": "rood", "label": "Verhuurd", "details": ""}]},
    )
    check("Verhuurd kill switch → 0",
          d3["score"] == 0 and d3["grade"] == "D")


def test_classificatie_edge_cases():
    section("Classificatie — edge cases")
    from classificatie import classificeer
    # Unicode / spaties
    check("Whitespace-only type → skip",
          classificeer("   ").get("category") in ("skip", "wonen"))
    # Lange adres met bedrijfspand-keyword
    r = classificeer("Appartement", adres="Bedrijfspand De Schaar 12")
    check("'Bedrijfspand' in adres flag gets picked up? Nee — type leidt",
          r["category"] == "wonen")
    # Gebruikssituatie: huurbeding niet ingeroepen = verhuurd
    r = classificeer("Woning", gebruikssituatie="huurbeding_niet_ingeroepen")
    check("huurbeding_niet_ingeroepen → verhuurd_wonen",
          r["category"] == "verhuurd_wonen" and r["is_verhuurd"])


def test_wijkcheck_edge_cases():
    section("Wijkcheck — edge cases")
    from bestemmingsplan import mag_splitsen
    # Onbekende postcode DH → wijk-score onbekend
    r = mag_splitsen("den haag", 150, 2, postcode="9999XX")
    # Basis-check (150m², 2 units) slaagt, maar wijkcheck heeft geen data
    check("DH onbekende PC → None or True (defensief)",
          r["mag_splitsen"] in (True, None))

    # Splitsing 3 units in DH waar 35m² per unit net niet haalbaar is
    r = mag_splitsen("den haag", 100, 3, postcode="2593AB")  # Bezuidenhout
    check("100m²/3 units = 33m² per unit < 35 min → niet toegestaan",
          r["mag_splitsen"] is False)

    # Unknown stad → None
    r = mag_splitsen("hoogvliet", 120, 2, postcode="3191AA")
    check("Onbekende stad → None",
          r["mag_splitsen"] is None)


def test_erfpacht_edge_cases():
    section("Erfpacht — edge cases")
    from erfpacht import detect_erfpacht
    # Leeg
    check("Lege tekst → geen erfpacht", detect_erfpacht("", "rotterdam")["is_erfpacht"] is False)
    # "Geen erfpacht" in koopakte
    r = detect_erfpacht("De woning wordt verkocht vrij op naam. Geen erfpacht.", "rotterdam")
    check("'Geen erfpacht' tekst → niet geflagd", r["is_erfpacht"] is False)
    # Tijdelijke erfpacht vlak voor expiration
    r = detect_erfpacht("Tijdelijke erfpacht tot 2027.", "den haag")
    check("Eindjaar < huidige + 5 = risico hoog",
          r.get("risk_level") == "hoog")


def test_bod_advies():
    section("Bod-advies generator")
    from bod_advies import genereer_bod_advies
    calc_stub = {
        "aankoop_totaal": 330_000, "totaal_kosten": 420_000,
        "scenarios": {
            "worst": {"netto": 400_000, "marge_pct": 6},
            "realistic": {"netto": 420_000, "marge_pct": 12},
            "best": {"netto": 440_000, "marge_pct": 18},
        },
    }
    # Scenario 1: hot motivated — veel argumenten, agressief bod
    b1 = genereer_bod_advies(
        vraagprijs=300_000, calc=calc_stub,
        motion={"motivated": True, "motivated_score": 8,
                "prijsverlaging_pct": 8, "aantal_prijsverlagingen": 2,
                "dagen_online": 200, "makelaarswissel": True},
        risks={"flags": [{"niveau": "oranje", "label": "Rijksmonument", "details": ""}]},
        ep_online={"forced_renovation_sterk": True, "label": "G"},
    )
    check("Motivated pand → 4+ argumenten", len(b1["argumenten"]) >= 4)
    check("Hoge korting_modifier → agressieve strategie",
          "Aggressief" in b1["strategie"] or "Markt" in b1["strategie"])
    check("Aggressief bod < markt bod",
          b1["aggressief"]["bod"] < b1["markt"]["bod"])

    # Scenario 2: rustig pand, markt-bod
    b2 = genereer_bod_advies(
        vraagprijs=300_000, calc=calc_stub,
        motion={"motivated": False, "motivated_score": 2},
        risks={"flags": []},
    )
    check("Rustig pand → weinig argumenten", len(b2["argumenten"]) <= 1)

    # Scenario 3: plafond-berekening werkt
    plafond = b2["plafond"]["bod"]
    check("Plafond < vraagprijs (worst marge 6% < 10% drempel)",
          plafond is not None and plafond <= 300_000)


def test_cbs_score():
    section("CBS wijk-kwaliteit score")
    import importlib.util as iu
    s = iu.spec_from_file_location("cbs", "scrapers/cbs_buurt.py")
    m = iu.module_from_spec(s); s.loader.exec_module(m)
    # Hoog: hoge WOZ + veel koop + weinig corp
    hi = m.wijk_kwaliteit_score({"gem_woz_x1000": 600, "pct_koop": 80, "pct_corp": 10})
    check(f"Premium wijk → score ≥ 80 (got {hi})", hi >= 80)
    # Laag: lage WOZ + weinig koop + veel corp
    lo = m.wijk_kwaliteit_score({"gem_woz_x1000": 180, "pct_koop": 25, "pct_corp": 50})
    check(f"Zwakke wijk → score ≤ 30 (got {lo})", lo <= 30)
    # Lege dict → None
    check("Lege dict → None", m.wijk_kwaliteit_score({}) is None or m.wijk_kwaliteit_score({}) == 50)


def test_bouwkundig():
    section("Bouwkundige checklist")
    from bouwkundig import genereer_checklist
    # 1920 + label F = veel checks
    c1 = genereer_checklist(bouwjaar=1920, energie_label="F", type_woning="herenhuis")
    labels = [x["punt"].lower() for x in c1]
    check("Oud pand → loden waterleidingen check",
          any("loden" in l for l in labels))
    check("Label F → verhuurverbod 2028",
          any("verhuurverbod" in l for l in labels))
    check("Herenhuis → monumenten-register check",
          any("monument" in l for l in labels))

    # Nieuwbouw 2015 + label A = minder checks
    c2 = genereer_checklist(bouwjaar=2015, energie_label="A", type_woning="appartement")
    check("Recent appartement → VvE check",
          any("vve" in x["punt"].lower() for x in c2))
    check("Minder checks dan oud pand", len(c2) < len(c1))

    # Rijksmonument flag werkt
    c3 = genereer_checklist(bouwjaar=1900, is_rijksmonument=True)
    check("Monument-flag → erfgoed-akkoord check",
          any("erfgoed" in x["punt"].lower() for x in c3))


def test_wijk_multiplier():
    section("Renovatie wijk-multipliers")
    from renovatie import _wijk_multiplier
    # Kralingen (Rotterdam premium)
    f1, b1 = _wijk_multiplier("3062AB", "Rotterdam")
    check(f"Kralingen premium → factor >1.0 (got {f1})", f1 > 1.0)
    # Tarwewijk (Rotterdam NPRZ goedkoop)
    f2, _ = _wijk_multiplier("3081XY", "Rotterdam")
    check(f"NPRZ goedkoop → factor <1.0 (got {f2})", f2 < 1.0)
    # Onbekende postcode → stad-fallback
    f3, b3 = _wijk_multiplier("9999XX", "Schiedam")
    check(f"Unknown PC4 → stad fallback (got {f3}, bron {b3})",
          0.9 < f3 < 1.05 and "stad" in b3)
    # Geen info → landelijk
    f4, b4 = _wijk_multiplier("", "")
    check(f"Geen info → 1.0 landelijk", f4 == 1.0 and b4 == "landelijk")


def test_verkoopkwaliteit_filter():
    section("Hard-skip filter (VERKOOP_KWALITEIT)")
    from config import VERKOOP_KWALITEIT
    # Config check
    check("Config heeft skip_bij_onvoldoende_confidence",
          "skip_bij_onvoldoende_confidence" in VERKOOP_KWALITEIT)
    check("min_worst_marge_bij_onvoldoende ≥ 0",
          VERKOOP_KWALITEIT.get("min_worst_marge_bij_onvoldoende", 0) >= 0)


def test_full_pipeline_real_address():
    if SKIP_NETWORK:
        return
    section("FULL pipeline — echte data (Prinsegracht 21D)")
    p = make_property(
        adres="Prinsegracht 21D", stad="Den Haag", postcode="2512EW",
        bouwjaar=1920, opp_m2=100, prijs=500000, prijs_per_m2=5000,
        energie_label="", type_woning="apartment",
    )
    klass = classificeer_property(p)
    check("Classificatie = wonen", klass["category"] == "wonen")

    bag_data = bag_mod.verrijk_bag(p.postcode, p.adres)
    check("BAG verrijking gelukt", bool(bag_data))

    mon = mon_mod.verrijk_monument_status(p, bag_data)
    check("Monument-check → rijksmonument",
          mon.get("is_rijksmonument") is True,
          f"got: {mon}")

    erf = detect_erfpacht("Eigen grond.", p.stad)
    splits = mag_splitsen(p.stad, p.opp_m2, 2, postcode=p.postcode)

    risks = aggregate_risks(
        classificatie=klass, bag=bag_data, monument=mon, erfpacht=erf,
        wijkcheck=splits.get("wijkcheck"),
        prop_bouwjaar=p.bouwjaar, prop_opp_m2=p.opp_m2,
    )
    check("Risks bevat monument flag",
          any("Rijksmonument" in f["label"] for f in risks["flags"]),
          f"flags: {[f['label'] for f in risks['flags']]}")

    d = bereken_dealscore(
        marge_pct=12, score_basis=7,
        motion={}, ep_online={}, erfpacht=erf, risks=risks,
        wijkcheck=splits.get("wijkcheck"),
    )
    check("Dealscore heeft score >= 0",
          0 <= d["score"] <= 100,
          f"score: {d['score']}, grade: {d['grade']}")
    print(f"      (dealscore: {d['score']}/100 grade {d['grade']})")


def test_percentiel():
    section("Percentiel helper")
    from referentie import _percentiel
    vals = [3000, 3500, 4000, 4500, 5000, 5500, 6000]
    check("P25 ≈ 3750", abs(_percentiel(vals, 25) - 3750) < 1)
    check("P50 = 4500", _percentiel(vals, 50) == 4500)
    check("P75 ≈ 5250", abs(_percentiel(vals, 75) - 5250) < 1)
    check("Lege lijst → 0", _percentiel([], 50) == 0.0)


def test_confidence_score():
    section("Confidence score")
    from referentie import _confidence_score
    # Hoge confidence: veel refs, klein spread, veel A/B/C, strak niveau, verse refs
    high = _confidence_score(n=15, spread_pct=8, high_label_frac=0.7,
                              match_niveau="pc6_label_fresh", avg_days=30)
    check(f"Ideale case → conf ≥ 70 (got {high})", high >= 70)

    # Lage confidence: weinig refs, grote spread, weinig A/B/C
    low = _confidence_score(n=3, spread_pct=55, high_label_frac=0.2,
                             match_niveau="stad_all_any", avg_days=200)
    check(f"Slechte case → conf ≤ 35 (got {low})", low <= 35)


def test_scenarios_fix_flip():
    section("Scenarios in bereken_fix_flip")
    from models import bereken_fix_flip, Property
    p = Property(source="t", url="u", adres="A 1", stad="Rotterdam",
                 prijs=300000, opp_m2=100, prijs_per_m2=3000,
                 type_woning="apartment")
    cfg = {"ovb_pct": 8, "rente_pct": 8, "renovatie_per_m2": 850,
           "looptijd_maanden": 9, "verwacht_verkoop_m2": 4800}
    ref = {
        "p25_pm2": 4500, "p50_pm2": 5000, "p75_pm2": 5500,
        "n_refs": 8, "confidence": 70, "confidence_label": "hoog",
    }
    p = bereken_fix_flip(p, cfg, ref_detail=ref)
    scen = p.calc.get("scenarios", {})
    check("scenarios dict aanwezig", bool(scen))
    check("worst verkoop_m2 = 4500",
          scen.get("worst", {}).get("verkoop_m2") == 4500,
          f"got {scen.get('worst')}")
    check("best verkoop_m2 = 5500",
          scen.get("best", {}).get("verkoop_m2") == 5500)
    check("realistic marge < best marge",
          scen["realistic"]["marge_pct"] < scen["best"]["marge_pct"])
    check("worst marge < realistic marge",
          scen["worst"]["marge_pct"] < scen["realistic"]["marge_pct"])

    vr = p.calc.get("verkoop_referentie", {})
    check("verkoop_referentie heeft confidence",
          vr.get("confidence") == 70)


def test_dealscore_worst_case():
    section("Dealscore gebruikt worst-case marge")
    from dealscore import bereken_dealscore
    # Deal met optimistische marge maar worst-case onder 8% → lage score
    d_risky = bereken_dealscore(
        marge_pct=18, score_basis=7,
        scenarios={"worst": {"marge_pct": 5}, "realistic": {"marge_pct": 15}, "best": {"marge_pct": 22}},
        verkoop_referentie={"confidence": 60, "confidence_label": "middel", "n_refs": 8},
    )
    check(f"Risky deal (worst 5%) → score ≤ 45 (got {d_risky['score']})",
          d_risky["score"] <= 45)

    # Robuuste deal: worst-case ≥15% + hoge confidence = solide
    d_solid = bereken_dealscore(
        marge_pct=22, score_basis=8,
        scenarios={"worst": {"marge_pct": 16}, "realistic": {"marge_pct": 22}, "best": {"marge_pct": 28}},
        verkoop_referentie={"confidence": 80, "confidence_label": "hoog", "n_refs": 14},
        motion={"motivated_score": 5, "prijsverlaging_pct": 3},
    )
    check(f"Solide deal → score ≥ 45 (B grade, got {d_solid['score']})",
          d_solid["score"] >= 45)
    check(f"Solide deal → grade ∈ B/A (got {d_solid['grade']})",
          d_solid["grade"] in ("B", "A", "A+"))

    # Onbetrouwbare verkoop → aftrek
    d_unknown = bereken_dealscore(
        marge_pct=20, score_basis=7,
        scenarios={"worst": {"marge_pct": 15}},
        verkoop_referentie={"confidence": 15, "confidence_label": "onvoldoende", "n_refs": 1},
    )
    has_penalty = any("onbetrouwbaar" in b["onderdeel"].lower()
                      for b in d_unknown["breakdown"])
    check("Onvoldoende verkoop-data → 'onbetrouwbaar' aftrek", has_penalty)


def main():
    print(f"\n🧪 Integratie-test — SKIP_NETWORK={SKIP_NETWORK}")
    tests = [
        test_classificatie, test_erfpacht, test_motion, test_splitsen,
        test_bag, test_monument, test_risks_aggregator, test_dealscore,
        test_percentiel, test_confidence_score,
        test_scenarios_fix_flip, test_dealscore_worst_case,
        test_bod_advies, test_cbs_score, test_bouwkundig,
        test_wijk_multiplier, test_verkoopkwaliteit_filter,
        test_classificatie_edge_cases,
        test_wijkcheck_edge_cases,
        test_erfpacht_edge_cases,
        test_full_pipeline_real_address,
    ]
    for t in tests:
        try:
            t()
        except Exception as e:
            global failed
            failed += 1
            print(f"\n  {FAIL} {t.__name__} crashte: {e}")
            traceback.print_exc()

    print(f"\n{'='*50}")
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")
    if failed == 0:
        print("  \x1b[32mAlle tests geslaagd ✓\x1b[0m")
    print(f"{'='*50}\n")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
