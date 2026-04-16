# Scanner Flow — Hoe het hele proces werkt

## Dagelijkse scan (07:00 UTC / 09:00 NL)

```
GitHub Actions daily_scan.yml
         │
         ▼
    scanner.py
         │
    ┌────┴────────────────────────────────────┐
    │         STAP 1: BRONNEN SCRAPEN         │
    │                                          │
    │  Funda (pyfunda API) ─────── 315+ panden │
    │  Pararius (Playwright) ───── 25+ panden  │
    │  30+ Makelaars ──────────── 660+ panden  │
    │    ├─ OGonline JSON (24 makelaars)       │
    │    ├─ Ooms JSON API                      │
    │    ├─ Kolpa REST API                     │
    │    ├─ WordPress+Realworks (Meesters etc) │
    │    ├─ TopSite (Beeuwkes, Prins, Waltmann)│
    │    └─ DailyCMS (Kooyman)                 │
    │  Trovit ─────────────────── HTML scrape  │
    │  Biedboek ───────────────── JSON API     │
    │                                          │
    │  TOTAAL: ~1000-1500 panden per scan      │
    └────┬────────────────────────────────────┘
         │
    ┌────┴────────────────────────────────────┐
    │      STAP 2: SANITY FILTER              │
    │                                          │
    │  Verwijder:                               │
    │  - Prijs < €25.000 (huur/parse fout)     │
    │  - Opp < 10 m²                           │
    │  - Prijs/m² < €500                       │
    │  - Geen URL                              │
    │  - Status != beschikbaar (bij bron)      │
    └────┬────────────────────────────────────┘
         │
    ┌────┴────────────────────────────────────┐
    │      STAP 3: EVALUEER PER PAND          │
    │                                          │
    │  Voor elk pand:                           │
    │                                          │
    │  3a. Referentieprijs ophalen             │
    │      → Zoek op POSTCODE (= zelfde wijk)  │
    │      → Alleen ZELFDE TYPE (app vs huis)   │
    │      → Vergelijkbaar oppervlak ±30%       │
    │      → Neem bovenste helft = gerenoveerd  │
    │                                          │
    │  3b. Renovatiekosten schatten            │
    │      → Per component (keuken, bad, etc)   │
    │      → Op basis van bouwjaar + label      │
    │      → Cosmetisch €650/m² tot casco €1800 │
    │                                          │
    │  3c. Fix & Flip berekening               │
    │      → Aankoop + OVB + notaris            │
    │      → Verbouwing (slimme calculator)     │
    │      → Financiering (9mnd, 8%)            │
    │      → Verkoop (ref prijs/m²)             │
    │      → Winst, marge, ROI                  │
    │      → Bod scenario (-8%)                 │
    │                                          │
    │  3d. Marge check                         │
    │      → < 8% marge = geen kans, skip       │
    └────┬────────────────────────────────────┘
         │
    ┌────┴────────────────────────────────────┐
    │      STAP 4: VERKOCHT CHECK             │
    │                                          │
    │  Funda panden: detail API status check    │
    │  → Alleen status=available door            │
    │                                          │
    │  Makelaar panden: Playwright pagina check │
    │  → Open URL, render JS, zoek "verkocht"   │
    └────┬────────────────────────────────────┘
         │
    ┌────┴────────────────────────────────────┐
    │      STAP 5: PRIJS VALIDATIE ← NIEUW!   │
    │                                          │
    │  Cross-check verkoopprijs tegen:          │
    │  - Huispedia woningwaarde                 │
    │  - WOZ waarde + 20% markt factor          │
    │  - Funda eigen prijs/m²                   │
    │                                          │
    │  Als >15% te hoog: CORRIGEER omlaag       │
    │  Na correctie <8% marge: SKIP             │
    └────┬────────────────────────────────────┘
         │
    ┌────┴────────────────────────────────────┐
    │      STAP 6: OUTPUT                     │
    │                                          │
    │  → Telegram notificatie (nieuwe kansen)   │
    │  → leads.json (alle kansen + biedboek)    │
    │  → panden.db (SQLite, geziene panden)     │
    │  → data branch op GitHub (voor dashboard) │
    └────┬────────────────────────────────────┘
         │
         ▼
    Dashboard: panden-scanner.vercel.app
    → Swipe interface (Tinder-style)
    → Foto carrousel
    → Volledige businesscase per pand
    → Opslaan / Afwijzen / Top deal
    → Notities per pand
```

## Bestanden

| Bestand | Wat het doet |
|---|---|
| `scanner.py` | Hoofdorchestrator — roept alles aan |
| `config.py` | Criteria (max prijs, min marge, steden, etc) |
| `models.py` | Property dataclass + financieel model |
| `renovatie.py` | Slimme renovatiekosten per component |
| `referentie.py` | Verkoopprijs op basis van wijkdata |
| `validatie.py` | Cross-check tegen Huispedia/WOZ |
| `database.py` | SQLite voor geziene panden |
| `notifier.py` | Telegram berichten |
| `scrapers/funda.py` | Funda via pyfunda mobile API |
| `scrapers/pararius.py` | Pararius via Playwright |
| `scrapers/makelaars.py` | 30+ makelaar websites |
| `scrapers/trovit.py` | Trovit aggregator |
| `scrapers/biedboek.py` | Biedboek veilingen |
| `dashboard/` | Next.js Vercel dashboard |
| `BRONNEN.md` | Master-lijst alle bronnen |

## Remote Agents

| Agent | Schedule | Taak |
|---|---|---|
| Verbetering Agent | Elke 4 uur | Bugs fixen, makelaars toevoegen, features |
| Calculatie Validator | Elke 6 uur | Financiële checks, externe bronvalidatie |
| GitHub Actions | Dagelijks 07:00 | Volledige scan |

## TODO — Volgende verbeteringen

### Data kwaliteit
- [ ] Plattegrond toevoegen (van Funda detail API: floorplan_urls)
- [ ] Bouwlaag/verdieping ophalen
- [ ] Erfpacht/eigen grond detectie
- [ ] VvE bijdrage ophalen
- [ ] Energielabel verificatie via RVO/ep-online.nl

### Analyse features
- [ ] Mag je opbouwen? → Bestemmingsplan check via Ruimtelijke Plannen API
- [ ] Mag je splitsen? → Gemeente splitsingbeleid ophalen
- [ ] Bestemmingsplan: woonbestemming check voor zakelijke panden
- [ ] Wijk-trend: stijgende of dalende prijzen
- [ ] Huurrendement berekening (alternatief voor verkoop)
- [ ] BAG data validatie (officieel bouwjaar/oppervlak)

### Meer bronnen
- [ ] Meer makelaars (58 nieuwe gevonden, zie BRONNEN.md)
- [ ] Zakelijke makelaars uitbreiden (27 nieuwe, zie agent research)
- [ ] Jaap.nl, Huislijn.nl, Marktplaats Wonen
- [ ] Veilingbiljet.nl, BOG Auctions
- [ ] Kadaster transactieprijzen

### Dashboard verbeteringen
- [ ] Renovatie componenten breakdown tonen
- [ ] Validatie resultaat tonen (Huispedia/WOZ/afwijking)
- [ ] Plattegrond viewer
- [ ] Google Maps/Streetview embed
- [ ] Vergelijk 2 panden naast elkaar
- [ ] Export naar PDF (businesscase rapport)
