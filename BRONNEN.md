# Bronnen — Master-lijst ALLE vastgoed databronnen Nederland

Dit is de complete master-lijst van ALLE bronnen waar vastgoed-kansen te vinden zijn in Nederland.
Niet alleen fix & flip, maar ALLE manieren om geld te verdienen met vastgoed.

**LET OP**: elke scan moet ALLE bronnen afgaan, niks mag vergeten worden.

---

## 1. WONINGEN (standaard fix & flip)

| Bron | URL | API/JSON? | Scrapable? | Listings | Zuid-Holland? | Gratis? |
|---|---|---|---|---|---|---|
| **Funda** | funda.nl/koop | Geen officieel API. PyPI `funda-scraper` + Apify scrapers | HTML scrapable (login vereist voor listing-datum) | 100.000+ | Ja, filter | Gratis browsen |
| **Pararius** | pararius.nl/koopwoningen | Geen API. Apify scraper beschikbaar | HTML scrapable (Playwright) | 10.000+ | Ja, filter | Gratis |
| **Huispedia** | huispedia.nl | Geen API | HTML scrapable | Alle woningen NL (8M+ datapunten) | Ja | Gratis (basis), betaald (rapporten) |
| **Huizenzoeker** | huizenzoeker.nl | Geen API | HTML scrapable | Groot, aggregator | Ja | Gratis |
| **Trovit** | huizen.trovit.nl | Geen API | HTML scrapable (bot-detectie) | Aggregator | Ja | Gratis |
| **Huislijn** | huislijn.nl | Geen API | HTML scrapable | ~5.000 | Ja | Gratis |
| **Marktplaats Wonen** | marktplaats.nl/l/huizen-en-kamers | Geen officieel API. Apify scraper | HTML scrapable | ~5.000+ | Ja, filter | Gratis |

## 2. EXECUTIEVEILINGEN / GEDWONGEN VERKOOP

| Bron | URL | API/JSON? | Scrapable? | Listings | Zuid-Holland? | Gratis? |
|---|---|---|---|---|---|---|
| **Veilingnotaris.nl** | veilingnotaris.nl | Geen publiek API | HTML scrapable | ~50 actief | Ja, filter op regio | Gratis |
| **Openbareverkoop.nl** | openbareverkoop.nl | Geen publiek API | HTML scrapable | ~100-200 actief | Ja, filter zuid-holland | Gratis |
| **Vastgoedveiling.nl** | vastgoedveiling.nl | Geen publiek API | HTML scrapable | ~96 actief, wekelijks nieuw | Ja | Gratis |
| **Nationale Vastgoedveiling** | nationalevastgoedveiling.nl | Geen publiek API | HTML scrapable | ~50-100 | Ja | Gratis |
| **BOG Auctions** | bog-auctions.com | Geen publiek API | HTML scrapable | ~20-50 (bedrijfsmatig OG) | Ja | Gratis |
| **Troostwijk Auctions** | troostwijkauctions.com/c/real-estate | Geen publiek API | HTML scrapable | ~20-50 | Ja, filter | Gratis registratie |
| **Veilingbiljet.nl** | veilingbiljet.nl | Geen API | HTML scrapable | ~50-100 (aankondigingen) | Ja, filter | Gratis |
| **De Eerste Amsterdamse** | eersteamsterdamse.nl | Geen API | HTML (biedt via openbareverkoop.nl) | ~20-40 | Deels (focus Randstad) | Gratis |
| **Vastgoedveiling Zuid** | vastgoedveilingzuid.nl | Geen API | HTML scrapable | ~20-30 (Brabant/Limburg) | Nee (Zuid-NL) | Gratis |
| **FaillissementsDossier** | faillissementsdossier.nl | Geen API | HTML scrapable | Dagelijks nieuwe faillissementen | Ja, zoekfunctie | Gratis (basis), betaald (pro) |
| **Centraal Insolventieregister** | insolventies.rechtspraak.nl | Geen API | HTML scrapable | Alle insolventies NL | Ja | Gratis |

## 3. GRONDPOSITIES / KAVELS

| Bron | URL | API/JSON? | Scrapable? | Listings | Zuid-Holland? | Gratis? |
|---|---|---|---|---|---|---|
| **Funda Bouwgrond** | funda.nl/koop/bouwgrond | Geen API (zelfde als Funda) | HTML scrapable | ~224 in ZH | Ja, filter | Gratis |
| **Funda in Business Bouwgrond** | fundainbusiness.nl/bouwgrond | Geen API | HTML scrapable | ~100+ landelijk | Ja, filter ZH | Gratis |
| **Bouwkavelsonline.nl** | bouwkavelsonline.nl | Geen API | HTML scrapable | ~500+ landelijk | Ja, filter ZH | Gratis |
| **KavelOnline.nl** | kavelonline.nl | Geen API | HTML scrapable | ~200+ | Ja | Gratis (zoeken), betaald (plaatsen) |
| **Grondplatform.nl** | grondplatform.nl | Geen API | HTML scrapable | 100K+ bezoekers/mnd | Ja, filter ZH | Gratis |
| **VerkoopUwKavel.nl** | verkoopuwkavel.nl | Geen API | HTML scrapable | ~50-100 | Ja (incl. Rhoon) | Gratis |
| **Kavelplatform.nl** | kavelplatform.nl | Geen API | HTML scrapable | ~100+ | Ja | Gratis |
| **ZelfbouwinNederland.nl** | zelfbouwinnederland.nl/kavels | Geen API | HTML scrapable | ~1.300 landelijk | Ja (overheid-site) | Gratis |
| **Zelfbouw-info.nl** | zelfbouw-info.nl/kavels | Geen API | HTML scrapable | ~500+ | Ja | Gratis |
| **BouwkavelTekoop.com** | bouwkaveltekoop.com | Geen API | HTML scrapable | ~200+ | Ja | Gratis |
| **BouwgrondVinden.nl** | bouwgrondvinden.nl | Geen API | HTML scrapable | ~100+ | Ja (Rotterdam focus) | Gratis |
| **Marktplaats Kavels** | marktplaats.nl/l/huizen-en-kamers/kavels-en-percelen | Geen API. Apify scraper | HTML scrapable | ~500+ | Ja, filter | Gratis |

## 4. BELEGGINGSPANDEN

| Bron | URL | API/JSON? | Scrapable? | Listings | Zuid-Holland? | Gratis? |
|---|---|---|---|---|---|---|
| **Beleggingspanden.nl** | beleggingspanden.nl | Geen API | HTML scrapable | 300+ transacties/jaar, 100K investeerders | Ja | Gratis (browsen) |
| **Funda in Business Belegging** | fundainbusiness.nl/belegging | Geen API | HTML scrapable | ~830 landelijk | Ja, filter ZH | Gratis |
| **VastGoedBeleggingenOnline (VGBO)** | vastgoedbeleggingenonline.nl | Geen API | HTML scrapable | ~100-200 | Ja | Gratis |
| **Vastiva.nl** | vastiva.nl | Geen API | HTML scrapable | ~50-100 (incl. off-market) | Ja | Gratis |
| **Pandjekopen.nl** | pandjekopen.nl | Geen API | HTML scrapable | ~50-100 (off-market, 7-9% rendement) | Ja | Gratis |
| **Beleggingsmakelaar.nl** | beleggingsmakelaar.nl | Geen API | Beperkt (off-market = op aanvraag) | Groot off-market aanbod | Ja | Gratis (aanmelden), wekelijkse mailing |
| **PropertyNL.com** | propertynl.com | Geen API | HTML scrapable | Nieuws + transacties professioneel OG | Ja | Betaald abonnement |
| **Vastgoedmarkt.nl** | vastgoedmarkt.nl | Geen API | HTML scrapable | Nieuws, geen listings | Ja | Betaald abonnement |
| **Beleggingspanden Rotterdam** | beleggingspandenrotterdam.nl | Geen API | HTML scrapable | ~20-50 (regionaal) | Ja (Rotterdam focus) | Gratis |

## 5. COMMERCIEEL VASTGOED / TRANSFORMATIE

| Bron | URL | API/JSON? | Scrapable? | Listings | Zuid-Holland? | Gratis? |
|---|---|---|---|---|---|---|
| **Funda in Business** | fundainbusiness.nl | Geen API. Apify scraper | HTML scrapable | ~5.000+ landelijk | Ja, filter | Gratis |
| **Bedrijfspand.com** | bedrijfspand.com | Geen API | HTML scrapable | ~2.000+ | Ja | Gratis |
| **Nationaal Transformatie Loket** | rvo.nl/onderwerpen/expertteam-woningbouw/nationaal-transformatie-loket | Geen API | HTML (info, geen listings) | N.v.t. (advies) | Ja | Gratis |
| **Rijksoverheid Transformatie** | rijksoverheid.nl/onderwerpen/ruimtelijke-ordening-en-gebiedsontwikkeling/transformatie-vastgoed | Geen API | HTML | N.v.t. (beleid) | Ja | Gratis |

## 6. OVERHEID VERKOPEN

| Bron | URL | API/JSON? | Scrapable? | Listings | Zuid-Holland? | Gratis? |
|---|---|---|---|---|---|---|
| **Biedboek.nl** | biedboek.nl | JSON API (bevestigd werkend) | Ja, JSON | ~50-100 actief | Ja | Gratis |
| **Rijksvastgoedbedrijf** | rijksvastgoedbedrijf.nl | Geen API (verwijst naar Biedboek) | HTML | Verkoopt via Biedboek | Ja | Gratis |
| **Defensie Vastgoed** | defensie.nl/onderwerpen/vastgoed | Geen API | HTML (info/beleid) | 468 objecten totaal, focus op behoud/modernisering | Ja (verspreide kazernes) | Gratis |
| **Domeinen Roerende Zaken** | domeinenrz.nl | Geen API | HTML scrapable | Roerende zaken, GEEN vastgoed (vastgoed via Biedboek) | N.v.t. | Gratis |
| **Gemeentes (Den Haag)** | denhaag.nl (zoek op "grond kopen") | Geen API | HTML | Wisselend | Ja | Gratis |
| **Gemeentes (Rotterdam)** | rotterdam.nl (zoek op "kavels") | Geen API | HTML | Wisselend | Ja | Gratis |
| **Openbareverkoop.nl Kavels ZH** | openbareverkoop.nl/kavels/?gebieden=zuid-holland | Geen API | HTML scrapable | ~10-30 | Ja | Gratis |

## 7. NIEUWBOUW / ONTWIKKELING

| Bron | URL | API/JSON? | Scrapable? | Listings | Zuid-Holland? | Gratis? |
|---|---|---|---|---|---|---|
| **Nieuwbouw-Nederland.nl** | nieuwbouw-nederland.nl | Geen API | HTML scrapable | 81.000+ woningen in 1.479 projecten | Ja, filter | Gratis |
| **Nieuwbouw.nl** | nieuwbouw.nl | Geen API | HTML scrapable | Groot aanbod | Ja | Gratis |
| **NieuwWonenNederland.nl** | nieuwwonennederland.nl | Geen API | HTML scrapable | ~500+ projecten | Ja | Gratis |
| **Funda Nieuwbouw** | funda.nl/nieuwbouw | Geen API | HTML scrapable | ~200+ projecten | Ja | Gratis |

## 8. AGRARISCH / BOERDERIJEN

| Bron | URL | API/JSON? | Scrapable? | Listings | Zuid-Holland? | Gratis? |
|---|---|---|---|---|---|---|
| **Agriteam** | agriteam.nl/te-koop/boerderij | Geen API | HTML scrapable | ~200+ boerderijen | Beperkt (meer Oost-NL) | Gratis |
| **AgriVastgoed** | agrivastgoed.nl/te-koop | Geen API | HTML scrapable | ~50-100 | Beperkt | Gratis |
| **NVM Agrarisch & Landelijk** | nvm.nl/agrarisch-landelijk | Geen API | HTML (verwijst naar Funda) | Via Funda | Ja | Gratis |
| **VastgoedVanHetLand.nl** | vastgoedvanhetland.nl | Geen API | HTML scrapable | ~100+ | Ja | Gratis |
| **Landelijk-Wonen.nl** | landelijk-wonen.nl | Geen API | HTML scrapable | ~100+ woonboerderijen | Ja | Gratis |
| **Boerderij.nl** | boerderij.nl | Geen API | HTML (meer nieuws dan listings) | Nieuws/info | Beperkt | Gratis |

## 9. HUURWONINGEN (rendement analyse)

| Bron | URL | API/JSON? | Scrapable? | Listings | Zuid-Holland? | Gratis? |
|---|---|---|---|---|---|---|
| **Pararius Huur** | pararius.nl/huurwoningen | Geen API. Apify scraper | HTML scrapable | ~15.000+ | Ja, filter | Gratis |
| **Kamernet** | kamernet.nl | Geen API. Apify scraper (deprecated) | HTML scrapable | ~10.000+ kamers | Ja (Den Haag, Rotterdam) | Betaald (messaging) |
| **HousingAnywhere** | housinganywhere.com | Geen API | HTML scrapable | ~67.000 objecten | Ja | Betaald (booking) |
| **Huurwoningen.nl** | huurwoningen.nl | Geen API. GitHub scraper | HTML scrapable | ~5.000+ | Ja, regionaal | Gratis |
| **RentSlam** | rentslam.com | Geen API (aggregator) | Niet scrapable (achter login) | Scant 1.000+ sites | Ja | Betaald |
| **Funda Huur** | funda.nl/huur | Geen API | HTML scrapable | ~10.000+ | Ja | Gratis |

## 10. MAKELAAR-WEBSITES (30+ bronnen)

Zie `scrapers/makelaars.py` voor de volledige lijst.

| Platform-type | Techniek | Voorbeelden |
|---|---|---|
| **OGonline/SiteLive** | JSON API `/nl/realtime-listings/consumer` | 20+ makelaars |
| **Ooms** | JSON API `/api/properties/available.json` | Ooms Makelaars |
| **Kolpa** | REST API `/api/listings` | Kolpa Makelaars |
| **WordPress + Realworks** | HTML scraping | Meesters, Voorberg |
| **TopSite** | HTML scraping | Beeuwkes, Prins, Waltmann |
| **DailyCMS** | HTML scraping | Kooyman |

---

## 11. DATA / VERRIJKING / VERIFICATIE BRONNEN

### Gratis Open Data (overheid)

| Bron | URL | API? | Wat? | Gratis? |
|---|---|---|---|---|
| **BAG (Adressen & Gebouwen)** | bag.kadaster.nl / pdok.nl | Ja: REST API (OGC Features) | Bouwjaar, oppervlak, gebruiksfunctie, status alle 10M+ panden NL | Gratis (open data) |
| **WOZ Waardeloket** | wozwaardeloket.nl | Geen officieel API (wet blokkering). Apify scraper beschikbaar | WOZ-waarde per adres | Gratis (handmatig), scraper via Apify |
| **Kadaster Open Data** | kadaster.nl/zakelijk/datasets/open-datasets | Ja: PDOK API's | Kadastrale kaart, perceelgrenzen, eigendom | Gratis (open data) |
| **Kadaster Vastgoeddashboard** | kadaster.nl/zakelijk/vastgoedinformatie/vastgoedcijfers/vastgoeddashboard | Geen API | Transactie-statistieken per provincie | Gratis |
| **Ruimtelijkeplannen.nl** | ruimtelijkeplannen.nl | Ja: REST API v4 (JSON + GeoJSON) op ruimte.omgevingswet.overheid.nl | Bestemmingsplannen, wijzigingsplannen, inpassingsplannen | Gratis |
| **CBS StatLine** | opendata.cbs.nl | Ja: OData API | Woningmarkt stats, prijsindex, transacties, bevolking | Gratis (open data) |
| **PDOK** | pdok.nl | Ja: 235+ datasets, OGC API's | Topo, kadaster, BAG, BGT, BRT | Gratis (open data) |
| **Officielebekendmakingen.nl** | officielebekendmakingen.nl | Beperkt (zoek API) | Omgevingsvergunningen, bestemmingsplan wijzigingen, gemeenteblad | Gratis |
| **RVO Energielabel** | ep-online.nl | Geen publiek API | Officieel energielabel per adres | Gratis |
| **Overheid Open Data** | data.overheid.nl | Ja: catalogus API | 15.000+ datasets overheid | Gratis |

### Betaalde Data Providers

| Bron | URL | API? | Wat? | Prijs |
|---|---|---|---|---|
| **Matrixian** | matrixian.com/en/api | Ja: 10+ REST API's (WOZ, BAG, Woningwaarde, Transacties, Buurtinfo, Hypotheek) | Meest uitgebreide vastgoed-API suite NL | Betaald (op aanvraag) |
| **Altum AI** | altum.ai/api | Ja: 20+ API's (WOZ, Woningwaarde, Kadaster Transacties, Energielabel) | 8M+ datapunten, 150 variabelen | Betaald (op aanvraag) |
| **Brainbay (NVM)** | brainbay.nl/en/products/brainbay-api | Ja: Marktinfo API, Modelwaarde API, Referentie API | Grootste vastgoed database NL (MIDAS), alle NVM transacties sinds 1974 | Betaald |
| **Kadasterdata.nl** | kadasterdata.nl | Geen API | Koopsommen, WOZ, woningwaarde per adres | Betaald per rapport (niet Kadaster zelf) |
| **Kadaster Koopsom** | kadaster.nl/producten/woning/koopsominformatie | Geen API | Officieel koopsom per woning | EUR 3,50 per opvraging |
| **Calcasa** | calcasa.nl | Via Brainbay | Woningwaarde model, taxatie-ondersteuning | Betaald |
| **Vastgoeddata.nl** | vastgoeddata.nl | Onbekend | Vastgoed data aggregatie | Onbekend |

---

## 12. SAMENVATTING: TOP BRONNEN PER CATEGORIE

### Beste gratis API's (programmeerbaar)
1. **BAG/PDOK** — pdok.nl — Gratis, REST API, alle gebouwen NL
2. **CBS StatLine** — opendata.cbs.nl — Gratis, OData API, marktstatistieken
3. **Ruimtelijkeplannen.nl** — REST API v4, bestemmingsplannen met GeoJSON
4. **Biedboek.nl** — JSON API, overheidsvastgoed verkoop

### Beste betaalde API's
1. **Altum AI** — Meest compleet (WOZ + transacties + waarde)
2. **Matrixian** — Breed aanbod (10+ API's)
3. **Brainbay/NVM** — Diepste historische data (sinds 1974)

### Grootste kans op onderschatting (alpha)
1. **Executieveilingen** — Veilingnotaris + Openbareverkoop + Vastgoedveiling (dagelijks nieuwe kansen)
2. **FaillissementsDossier** — Failliet vastgoed-BV's, curator-verkopen
3. **Biedboek** — Overheid verkoopt vaak onder marktwaarde
4. **Bestemmingsplan wijzigingen** — Via Officielebekendmakingen.nl + Ruimtelijkeplannen API
5. **Off-market** — Beleggingsmakelaar.nl + Vastiva (niet op Funda)
6. **Agrarisch naar wonen** — Vastgoedvanhetland.nl (functiewijziging = waardestijging)

---

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
6. **Hoge alpha** — bronnen waar anderen NIET kijken (veilingen, faillissementen, overheid, agrarisch)

---

## Technische notities scraping

| Site | Moeilijkheidsgraad | Aanpak |
|---|---|---|
| Funda | Middel (login voor datum-data) | PyPI `funda-scraper`, Apify, Selenium |
| Pararius | Middel | Playwright, Apify scraper |
| Kamernet | Moeilijk (deprecated scraper) | Apify (check status) |
| Openbareverkoop | Makkelijk | Standaard HTML scraping |
| Veilingnotaris | Makkelijk | Standaard HTML scraping |
| Vastgoedveiling | Makkelijk | Standaard HTML scraping |
| Biedboek | Makkelijk | JSON API |
| Marktplaats | Middel | Apify scraper |
| BAG/PDOK | Makkelijk | Officieel REST API |
| CBS | Makkelijk | OData protocol |
| Ruimtelijkeplannen | Makkelijk | REST API v4 met JSON |
| WOZ Waardeloket | Moeilijk (geen API, wet blokkeert) | Apify scraper of Altum AI |
| FaillissementsDossier | Makkelijk | HTML scraping |
