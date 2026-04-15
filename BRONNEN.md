# Bronnen — Wat de scanner ALTIJD moet checken

Dit is de master-lijst van alle bronnen waar we nieuwe leads zoeken.
**LET OP**: elke scan moet ALLE bronnen afgaan, niks mag vergeten worden.

## 1. Woningen (standaard fix & flip)

| Bron | Scraper | Status | URL |
|---|---|---|---|
| Funda | `scrapers/funda.py` (pyfunda API) | Werkt | funda.nl/koop |
| Pararius | `scrapers/pararius.py` (Playwright) | Werkt | pararius.nl/koopwoningen |
| Trovit | `scrapers/trovit.py` | Werkt lokaal, blocked op GH | huizen.trovit.nl |
| Funda in Business (woonbestemming) | `scrapers/funda_ib.py` | TODO — koopobjecten met herontwikkeling naar wonen | fundainbusiness.nl |
| Planviewer | `scrapers/planviewer.py` | TODO — bestemmingsplan woningbouw | planviewer.nl |

## 2. Commercieel / Transformatie

| Bron | Scraper | Status |
|---|---|---|
| Funda in Business (kantoor/winkel) | `scrapers/funda_ib.py` | Werkt soms |
| Bedrijfspand.com | `scrapers/bedrijfspand.py` | Selectors controleren |
| COG Makelaars | `scrapers/makelaars.py` | Werkt |

## 3. Makelaar-websites (30+ bronnen)

Zie `scrapers/makelaars.py` voor de volledige lijst.
Platformen:
- OGonline/SiteLive — JSON API `/nl/realtime-listings/consumer` (20+ makelaars)
- Ooms — JSON API `/api/properties/available.json`
- Kolpa — REST API `/api/listings`
- WordPress + Realworks — HTML scraping (Meesters, Voorberg)
- TopSite — HTML scraping (Beeuwkes, Prins, Waltmann)
- DailyCMS — HTML scraping (Kooyman)

## 4. Veilingen / Biedingen (info-only)

| Bron | Scraper | Status |
|---|---|---|
| Biedboek | `scrapers/biedboek.py` | Werkt (JSON API) |
| Veilingbiljet | TODO | veilingbiljet.nl |
| BOG Auctions | TODO | bog-auctions.com |
| Onlineveilingmeester | TODO | onlineveilingmeester.nl |

## 5. Extra bronnen (TODO)

- **NVM Funda partners** — eigen websites van NVM leden met eigen aanbod
- **Marktplaats Wonen** — marktplaats.nl/l/huizen-en-kamers
- **Huislijn** — huislijn.nl
- **Vastgoed Actueel** — vastgoedactueel.nl
- **Walcheren panden** — walcherenpanden.nl (regionaal)
- **Jaap.nl** — jaap.nl
- **Huizen zoeker** — huizenzoeker.nl
- **Zitter** — zitter.nl

## 6. Data verificatie bronnen

Voor het valideren van een gevonden kans:

- **WOZ-waarde** — wozwaardeloket.nl (gratis public data)
- **Kadaster** — kadaster.nl (eigendomsinfo, hypotheek, beperkingen)
- **BAG** — bag.kadaster.nl (officieel bouwjaar, oppervlak, gebruiksfunctie)
- **Huispedia** — huispedia.nl (geschatte marktwaarde)
- **Calcasa** — calcasa.nl (waardeschatting via algoritme)
- **RVO Energielabel** — ep-online.nl (officieel energielabel)
- **Bestemmingsplan** — ruimtelijkeplannen.nl (mag je splitsen/transformeren?)

## Workflow: als je nieuwe leads wilt vinden

1. Run `python scanner.py` — draait alle scrapers
2. Check Telegram voor nieuwe kansen
3. Open dashboard: https://panden-scanner.vercel.app
4. Swipe door de kansen
5. Voor opgeslagen panden: check de verificatie-bronnen (WOZ, Kadaster, BAG)

## Prioriteit bij toevoegen nieuwe bron

1. **Werkbare URL + stabiele data structuur** (JSON API > HTML)
2. **Geen captcha/bot detectie** (of goed te omzeilen)
3. **Unieke panden die niet op Funda staan** (waarom anders?)
4. **Zuid-Holland focus** (of landelijk met stad-filter)
5. **Dagelijks/wekelijks nieuwe panden**
