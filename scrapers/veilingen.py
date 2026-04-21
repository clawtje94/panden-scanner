"""
Executieveiling scrapers — panden onder marktwaarde.

Bronnen:
1. Vastgoedveiling.nl — embedded JSON, rijkste data (90+ velden)
2. Openbareverkoop.nl — POST JSON API
"""
import logging
import re
import json
import requests
from typing import List
from datetime import datetime

from models import Property

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept-Language": "nl-NL,nl;q=0.9",
}


def scrape_vastgoedveiling() -> List[Property]:
    """Scrape vastgoedveiling.nl — alle data als JSON in 1 request."""
    results = []
    try:
        r = requests.get("https://www.vastgoedveiling.nl/veilingen", headers=HEADERS, timeout=30)
        if r.status_code != 200:
            logger.error("Vastgoedveiling HTTP %d", r.status_code)
            return results

        # Zoek de __NEXT_DATA__ JSON
        match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', r.text, re.DOTALL)
        if not match:
            logger.warning("Vastgoedveiling: geen __NEXT_DATA__ gevonden")
            return results

        data = json.loads(match.group(1))
        auctions = data.get("props", {}).get("pageProps", {}).get("auctions", [])

        for a in auctions:
            try:
                # Filter Zuid-Holland
                if a.get("provincie") != "Zuid-Holland":
                    continue

                # Filter: alleen actieve/komende veilingen
                status = a.get("status", "").lower()
                if status in ("afgelopen", "geannuleerd", "ingetrokken"):
                    continue

                adres = f"{a.get('straat', '')} {a.get('huisnummer', '')}".strip()
                if not adres:
                    adres = a.get("name", "")
                stad = a.get("plaats", "")
                postcode = a.get("postcode", "")

                # Prijs: startbod of afslag
                startbod = a.get("startbod", 0) or 0
                afslag = a.get("startbod_op_afslag", 0) or 0
                prijs = startbod if startbod > 0 else afslag

                opp = a.get("oppervlakte_object", 0) or a.get("oppervlakte_perceel", 0) or 0
                obj_type = a.get("object_type", "") or ""
                bouwjaar = a.get("bouwjaar", 0) or 0

                # Veiling datum
                starttijd = a.get("starttijd", "")
                veiling_datum = ""
                if starttijd:
                    try:
                        dt = datetime.fromisoformat(starttijd.replace("Z", "+00:00"))
                        veiling_datum = dt.strftime("%d-%m-%Y %H:%M")
                    except:
                        pass

                # URL
                slug = a.get("slug", "")
                url = f"https://www.vastgoedveiling.nl/veilingen/{a.get('id', '')}/{slug}" if slug else ""

                # Foto
                fotos = a.get("afbeeldingen", [])
                foto_url = fotos[0].get("url", "") if fotos else ""

                # Type veiling
                type_verkoop = a.get("type_verkoop", "") or ""

                prop = Property(
                    source="veiling_vastgoedveiling",
                    url=url,
                    adres=adres,
                    stad=stad,
                    postcode=postcode,
                    prijs=int(prijs) if prijs else 0,
                    opp_m2=int(opp) if opp else 0,
                    prijs_per_m2=round(prijs / opp) if prijs and opp and opp > 0 else 0,
                    type_woning=f"{obj_type} ({type_verkoop})",
                    bouwjaar=int(bouwjaar) if bouwjaar else 0,
                    foto_url=foto_url,
                )
                # Extra veiling data in calc
                prop.calc = {
                    "veiling_datum": veiling_datum,
                    "startbod": int(startbod),
                    "afslag": int(afslag),
                    "kosten_aanvullend": a.get("kosten_aanvullend", 0),
                    "type_verkoop": type_verkoop,
                    "onderhands_bod_mogelijk": a.get("onderhands_bod_mogelijk", ""),
                    "gebruikssituatie": a.get("gebruikssituatie", ""),
                    "is_veiling": True,
                }
                results.append(prop)

            except Exception as e:
                logger.debug("Vastgoedveiling parse fout: %s", e)

    except Exception as e:
        logger.error("Vastgoedveiling fout: %s", e)

    logger.info("Vastgoedveiling: %d veilingen in Zuid-Holland", len(results))
    return results


def scrape_openbareverkoop() -> List[Property]:
    """Scrape openbareverkoop.nl — POST JSON API."""
    results = []
    try:
        r = requests.post(
            "https://www.openbareverkoop.nl/kavels/searchresults",
            data={
                "view": "resultaten",
                "gebieden": "zuid-holland",
                "periode": "komende30",
            },
            headers={
                **HEADERS,
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=30,
        )
        if r.status_code != 200:
            logger.error("Openbareverkoop HTTP %d", r.status_code)
            return results

        data = r.json()
        zittingen = data.get("results", [])

        for zitting in zittingen:
            for regio in zitting.get("objectenPerRegio", []):
                for obj in regio.get("objects", []):
                    try:
                        naam = obj.get("kavelNaam", "")
                        if not naam:
                            continue

                        # Parse adres en stad uit naam (format: "Straat 12, STAD")
                        parts = naam.split(",")
                        adres = parts[0].strip() if parts else naam
                        stad = parts[-1].strip().title() if len(parts) > 1 else ""

                        # Prijs
                        inzet_txt = obj.get("inzet", "")
                        inzet = 0
                        if inzet_txt:
                            m = re.search(r'[\d.]+', inzet_txt.replace(".", ""))
                            inzet = int(m.group()) if m else 0

                        afslag_txt = obj.get("afslag", "")
                        afslag = 0
                        if afslag_txt:
                            m = re.search(r'[\d.]+', afslag_txt.replace(".", ""))
                            afslag = int(m.group()) if m else 0

                        prijs = inzet if inzet > 0 else afslag

                        # Status
                        status = obj.get("status", "").lower()
                        if status in ("gegund", "opgehouden", "ingetrokken"):
                            continue

                        obj_type = obj.get("woningtype", "")
                        veiling_url = "https://www.openbareverkoop.nl" + obj.get("url", "")
                        foto = obj.get("image", "")
                        if foto and not foto.startswith("http"):
                            foto = "https://www.openbareverkoop.nl" + foto

                        lat = obj.get("lat", 0)
                        lng = obj.get("lng", 0)

                        prop = Property(
                            source="veiling_openbareverkoop",
                            url=veiling_url,
                            adres=adres,
                            stad=stad,
                            prijs=prijs,
                            opp_m2=0,
                            type_woning=f"{obj_type} (veiling)",
                            foto_url=foto,
                        )
                        prop.calc = {
                            "inzet": inzet,
                            "afslag": afslag,
                            "veiling_datum": obj.get("verwachteTijdstip", ""),
                            "veilingwijze": obj.get("veilingwijze", ""),
                            "organisatie": obj.get("organisatie", ""),
                            "is_veiling": True,
                        }
                        results.append(prop)

                    except Exception as e:
                        logger.debug("Openbareverkoop parse fout: %s", e)

    except Exception as e:
        logger.error("Openbareverkoop fout: %s", e)

    logger.info("Openbareverkoop: %d veilingen in Zuid-Holland", len(results))
    return results


def scrape_veilingen() -> List[Property]:
    """Combineer alle veiling bronnen."""
    results = []
    try:
        results += scrape_vastgoedveiling()
    except Exception as e:
        logger.error("Vastgoedveiling gefaald: %s", e)
    try:
        results += scrape_openbareverkoop()
    except Exception as e:
        logger.error("Openbareverkoop gefaald: %s", e)

    logger.info("Veilingen totaal: %d", len(results))
    return results
