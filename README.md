# Panden Scanner — Bateau Vastgoed

Development-intelligence platform voor vastgoed in Zuid-Holland.
Scant dagelijks 1.000+ panden, verrijkt met BAG / monument / erfpacht /
WOZ-cijfers, rekent 3-scenarios verkoopprijs, en serveert een PWA-dashboard.

Live: **https://panden-scanner.vercel.app**

---

## Features

### Data-bronnen
- **Funda** (pyfunda mobile API)
- **Pararius** (Playwright)
- **30+ makelaars**: OGonline, Ooms, Kolpa, Meesters, Beeuwkes, Prins,
  Waltmann, Kooyman, etc.
- **Beleggingspanden.nl** (verhuurd aanbod, aparte categorie)
- **Biedboek** (tenders, notarisverkoop)
- **Veilingen** (Vastgoedveiling.nl + Openbareverkoop)
- **Kavels** (bouwgrond)

### Risk intelligence
- **BAG (Kadaster)** — officieel bouwjaar, gebruiksdoel, oppervlak,
  pandstatus. Hard-skip bij `industriefunctie`/`sportfunctie`/`celfunctie`.
- **RCE Rijksmonumenten** — via open WFS, per pand vermelding in
  monumentenregister + reno-waarschuwing +30-50%.
- **Erfpacht-detectie** — uit Funda-beschrijving: eeuwigdurend /
  afgekocht / eindjaar / canon. Rotterdam 60%-afkoopregeling 2026 flag.
- **EP-Online (RVO energielabel)** — forced-renovation kandidaten
  (E/F/G met bouwjaar <1992 = sterk).
- **CBS Kerncijfers wijken & buurten** — per gemeente: WOZ-gem, %koop,
  %corp, bevolkingsdichtheid → wijk-kwaliteit score 0-100.
- **Classificatie** — whitelist woon-types, blacklist
  hallen/loodsen/motorboten/kavels/beleggingsobjecten.

### Verkoopprijs-engine v2
- Cascade filter: PC6 → PC4 → stad, met/zonder label A/B/C en
  days-on-market ≤ 120.
- **P25 / P50 / P75 scenarios** (worst / realistic / best).
- **Confidence-score 0-100** op N refs + spread + %A-B-C + match-niveau.
- **Dealscore** rekent op **worst-case marge** — een deal die alleen
  bij gemiddelde verkoop rendeert is geen robuuste deal.

### Motion signalen
- Prijs-historie tracking per URL (SQLite `pand_geschiedenis`).
- Detectie: prijsverlaging %, aantal verlagingen, makelaarswissel,
  "onder bod → terug te koop", dagen online.
- `motivated_score` 0-10 composite.
- **Prijs-verlaging alert** via Telegram bij verse mutaties (<48u).

### Bod-advies
Per pand 3 bod-niveaus (aggressief / markt / plafond) + onderhandelings-
argumenten gegenereerd uit motion/risks/erfpacht/forced-reno/BAG.

### Dashboard (PWA)
- **Swipe-interface** (Tinder-stijl) met keyboard shortcuts
- **Stats** met grade-verdeling, heatmap per stad, CSV-export, makelaar-intel
- **Portfolio** tab: eigen panden + kanban view
- **💎 ROI** tab: aggregaten gerealiseerd vs verwacht
- **Compare** tab: 2 panden naast elkaar met 16 metrics
- **Recent viewed**, **Verdwenen**, **Beleggingen** tabs
- **Detail-modal**: dealscore, risks, bod-advies, scenarios,
  actieplan-checklist, bouwkundige checklist per bouwperiode, Maps-links,
  price-history chart, foto-grid
- **Cmd+K** command palette voor quick navigation
- **Deep-links** naar specifiek pand (#pand=<base64>)
- **iCal export** bezichtigingen, **batch email** naar makelaars
- **Offline-ready** via service worker
- **Auto-save** motivated hoge-scorers, **auto-refresh** elke 10 min

### Notificaties
- **Telegram per kans**: header `[grade] score — strategie`, bod-advies,
  verkoop-scenarios, risico-profiel, motion, EP-Online, referentie-panden.
- **Prijs-verlaging alert** bij mutaties <48u.
- **Weekly digest** elke maandag 09:00 NL.
- **Maandrapport** eerste week van de maand (uitgebreider).
- **Grade-filter**: `TELEGRAM_MIN_GRADE = "B"` in config om spam te voorkomen.

---

## Technische stack

| Component | Tech |
|---|---|
| Scanner | Python 3.12, Playwright, SQLite |
| Dashboard | Next.js 14, React 18, CSS (PWA) |
| Deploy | GitHub Actions daily cron + auto-deploy workflow, Vercel |
| Data-branch | `data` branch op GitHub, raw.githubusercontent.com als CDN |

## Modules (Python)

| File | Doel |
|---|---|
| `scanner.py` | Hoofdorchestrator |
| `config.py` | Criteria + env-vars |
| `models.py` | Property + fix_flip/splits/transformatie calc met scenarios |
| `classificatie.py` | Wonen / transformatie / verhuurd / skip |
| `referentie.py` | Verkoop-engine v2 met P25/P50/P75 + confidence |
| `risks.py` | Aggregeert alle risico-flags per pand |
| `dealscore.py` | Composite 0-100 + grade (A+ … D) |
| `bod_advies.py` | 3-niveau bod + argumenten |
| `bouwkundig.py` | Checklist per bouwperiode + label + type |
| `erfpacht.py` | Erfpacht-parse uit Funda-beschrijving |
| `wijkdata.py` | Leefbaarometer + parkeerdruk (DH) + NPRZ (RDAM) |
| `renovatie.py` | Verbouwkosten per component + wijk-multipliers |
| `looptijd.py` | Dynamische looptijd met verkoop-snelheid feedback |
| `database.py` | SQLite observaties, caches, cleanup |
| `notifier.py` | Telegram met volledige businesscase |
| `weekly_digest.py` | Wekelijks/maandelijks Telegram-overzicht |
| `scrapers/bag.py` | PDOK BAG WFS verrijking |
| `scrapers/monument.py` | RCE rijksmonumenten WFS |
| `scrapers/ep_online.py` | EP-Online energielabel API |
| `scrapers/cbs_buurt.py` | CBS Kerncijfers gemeentes |
| `scrapers/altum.py` | Altum AI Kadaster (scaffold, key vereist) |

## Setup (nieuw)

```bash
pip install -r requirements.txt
playwright install chromium --with-deps
cp .env.example .env        # vul TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
python scanner.py            # eerste run (duurt ~15 min)
```

### Optionele API-keys
- `EP_ONLINE_API_KEY` — gratis via https://apikey.ep-online.nl
- `ALTUM_API_KEY` — gratis tier (50 calls/mnd) via https://altum.ai/sign-up

GitHub secrets voor CI:
```bash
gh secret set TELEGRAM_TOKEN --repo clawtje94/panden-scanner
gh secret set TELEGRAM_CHAT_ID --repo clawtje94/panden-scanner
gh secret set EP_ONLINE_API_KEY --repo clawtje94/panden-scanner
gh secret set ALTUM_API_KEY --repo clawtje94/panden-scanner
gh secret set VERCEL_TOKEN --repo clawtje94/panden-scanner
gh secret set VERCEL_ORG_ID --repo clawtje94/panden-scanner
gh secret set VERCEL_PROJECT_ID --repo clawtje94/panden-scanner
```

## GitHub Actions

- `daily_scan.yml` — elke dag 07:00 UTC (09:00 NL)
- `deploy_dashboard.yml` — op push naar `dashboard/**`
- `weekly_digest.yml` — elke maandag 07:00 UTC

## Tests

```bash
python3 tests/test_integration.py
```
57 checks: classificatie, erfpacht, motion, splitsen, BAG (live PDOK),
monument (live RCE), risks, dealscore, scenarios, confidence, percentiel,
full pipeline op bekende adressen.

## Configuratie

`config.py` knoppen:
- `FIX_FLIP` / `SPLITSING` / `TRANSFORMATIE` — marge-drempels, looptijd, OVB
- `VERKOOP_KWALITEIT` — hard-skip bij onvoldoende confidence + lage marge
- `TELEGRAM_MIN_GRADE` — "A+" / "A" / "B" / "C" / "D"
- `SIGNALEN` — motion detectie drempels
- `STEDEN_FUNDA` — te scannen gemeentes

## Filosofie

**Voor ontwikkelaars, niet hobbyisten.** Een developer beoordeelt ~50
goede leads per week, niet 500 ruwe. Daarom:
- Bij twijfel eerder skippen dan doorlaten
- Worst-case marge is leidend (niet realistic)
- Risk-flags zichtbaar vóór aankoopbeslissing
- Referentie-prijs met expliciete confidence (geen blind vertrouwen)

---

Built as a professional dev-tool voor Bateau Vastgoed.
