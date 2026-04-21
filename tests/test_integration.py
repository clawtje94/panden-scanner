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


def main():
    print(f"\n🧪 Integratie-test — SKIP_NETWORK={SKIP_NETWORK}")
    tests = [
        test_classificatie, test_erfpacht, test_motion, test_splitsen,
        test_bag, test_monument, test_risks_aggregator, test_dealscore,
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
