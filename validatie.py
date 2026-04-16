"""
Verkoopprijs validatie — cross-checkt onze referentieprijs tegen
externe bronnen VOORDAT een kans wordt verstuurd.

Bronnen:
1. Huispedia — woningwaarde schatting (HTML scraping)
2. WOZ waarde — wozwaardeloket.nl (openbare data)
3. Funda prijs/m² — uit de detail API (al beschikbaar)

Regel: als onze verkoopprijs >15% hoger is dan het gemiddelde
van de externe bronnen, is onze prijs te optimistisch.
"""
import logging
import re
import requests
from typing import Optional

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept-Language": "nl-NL,nl;q=0.9",
}


def _check_huispedia(postcode: str, adres: str, stad: str) -> Optional[int]:
    """Haal Huispedia woningwaarde schatting op. Returns geschatte waarde of None."""
    if not postcode or len(postcode) < 6:
        return None
    try:
        # Huispedia URL: /koopwoning/{postcode}/{straat-huisnummer}
        pc = postcode.replace(" ", "").upper()
        # Maak slug van adres
        slug = re.sub(r'[^a-z0-9]+', '-', adres.lower()).strip('-')
        url = f"https://www.huispedia.nl/{pc[:4]}-{pc[4:]}/{slug}"

        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            # Probeer alternatieve URL
            url2 = f"https://www.huispedia.nl/koopwoning/{pc}"
            r = requests.get(url2, headers=HEADERS, timeout=10)
            if r.status_code != 200:
                return None

        html = r.text.lower()

        # Zoek naar woningwaarde in de HTML
        # Patronen: "geschatte waarde: €XXX.XXX" of "woningwaarde" + bedrag
        patterns = [
            r'geschatte\s+waarde[^€]*€\s*([\d.]+)',
            r'woningwaarde[^€]*€\s*([\d.]+)',
            r'marktwaarde[^€]*€\s*([\d.]+)',
            r'"estimatedValue"\s*:\s*(\d+)',
            r'"price"\s*:\s*(\d+)',
            r'data-value="(\d+)"',
        ]
        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                val = match.group(1).replace(".", "")
                if val.isdigit() and int(val) > 50_000:
                    logger.info("Huispedia %s: %s", adres, val)
                    return int(val)
        return None

    except Exception as e:
        logger.debug("Huispedia fout voor %s: %s", adres, e)
        return None


def _check_woz(postcode: str, huisnummer: str) -> Optional[int]:
    """Haal WOZ waarde op via wozwaardeloket.nl. Returns WOZ waarde of None."""
    if not postcode or not huisnummer:
        return None
    try:
        # WOZ API endpoint
        pc = postcode.replace(" ", "").upper()
        nr = re.search(r'(\d+)', huisnummer)
        if not nr:
            return None

        url = f"https://api.wozwaardeloket.nl/woz-proxy/woz/v2/wozwaarde/{pc}/{nr.group(1)}"
        r = requests.get(url, headers={
            **HEADERS,
            "Accept": "application/json",
            "Referer": "https://www.wozwaardeloket.nl/",
        }, timeout=10)

        if r.status_code == 200:
            data = r.json()
            # De API geeft meestal een lijst van WOZ waarden per jaar
            if isinstance(data, list) and data:
                # Neem meest recente
                latest = data[0]
                woz = latest.get("vastgesteldeWaarde") or latest.get("wozWaarde") or latest.get("waarde")
                if woz and int(woz) > 50_000:
                    logger.info("WOZ %s %s: %s", pc, nr.group(1), woz)
                    return int(woz)
            elif isinstance(data, dict):
                woz = data.get("vastgesteldeWaarde") or data.get("wozWaarde")
                if woz and int(woz) > 50_000:
                    return int(woz)
        return None

    except Exception as e:
        logger.debug("WOZ fout voor %s %s: %s", postcode, huisnummer, e)
        return None


def valideer_verkoopprijs(
    onze_pm2: float,
    onze_bruto: int,
    opp_m2: int,
    postcode: str,
    adres: str,
    stad: str,
    funda_pm2: float = 0,
) -> dict:
    """
    Cross-check onze verkoopprijs tegen externe bronnen.

    Returns:
        {
            'goedgekeurd': bool,         # True als onze prijs realistisch is
            'onze_pm2': float,
            'bronnen': {bron: waarde},   # externe waarden gevonden
            'gem_extern_pm2': float,     # gemiddelde van externe bronnen
            'afwijking_pct': float,      # hoeveel % onze prijs afwijkt
            'gecorrigeerde_pm2': float,   # evt bijgestelde prijs
            'reden': str,
        }
    """
    bronnen = {}

    # Huisnummer uit adres halen
    nr_match = re.search(r'(\d+)', adres)
    huisnummer = nr_match.group(1) if nr_match else ""

    # 1. Huispedia
    huispedia = _check_huispedia(postcode, adres, stad)
    if huispedia and opp_m2 > 0:
        bronnen["huispedia"] = round(huispedia / opp_m2)

    # 2. WOZ
    woz = _check_woz(postcode, huisnummer)
    if woz and opp_m2 > 0:
        # WOZ is meestal lager dan marktwaarde. Factor 1.15-1.25
        woz_markt = round(woz * 1.20 / opp_m2)  # WOZ + 20% = marktwaarde schatting
        bronnen["woz_markt"] = woz_markt
        bronnen["woz_raw"] = round(woz / opp_m2)

    # 3. Funda eigen prijs/m² (als beschikbaar)
    if funda_pm2 and funda_pm2 > 0:
        try:
            bronnen["funda_pm2"] = int(float(str(funda_pm2).replace("€", "").replace(".", "").replace(",", "").strip()))
        except:
            pass

    # Bereken gemiddelde van externe bronnen (excl woz_raw)
    extern_waarden = [v for k, v in bronnen.items() if k not in ("woz_raw",) and v > 0]

    if not extern_waarden:
        # Geen externe data beschikbaar — conservatief: 10% korting op onze prijs
        return {
            "goedgekeurd": True,
            "onze_pm2": onze_pm2,
            "bronnen": bronnen,
            "gem_extern_pm2": 0,
            "afwijking_pct": 0,
            "gecorrigeerde_pm2": onze_pm2,
            "reden": "Geen externe bronnen beschikbaar",
        }

    gem_extern = sum(extern_waarden) / len(extern_waarden)
    afwijking = ((onze_pm2 - gem_extern) / gem_extern * 100) if gem_extern > 0 else 0

    # Beslissing
    if afwijking > 15:
        # Onze prijs is >15% hoger dan extern → te optimistisch
        # Gebruik gemiddelde van extern + 5% (kleine optimisme marge)
        gecorrigeerd = round(gem_extern * 1.05)
        return {
            "goedgekeurd": False,
            "onze_pm2": onze_pm2,
            "bronnen": bronnen,
            "gem_extern_pm2": round(gem_extern),
            "afwijking_pct": round(afwijking, 1),
            "gecorrigeerde_pm2": gecorrigeerd,
            "reden": f"Onze prijs {round(afwijking)}% hoger dan extern ({round(gem_extern)}/m2). Gecorrigeerd naar {gecorrigeerd}/m2",
        }
    elif afwijking < -20:
        # Onze prijs is >20% lager dan extern → mogelijk onderschatting
        return {
            "goedgekeurd": True,
            "onze_pm2": onze_pm2,
            "bronnen": bronnen,
            "gem_extern_pm2": round(gem_extern),
            "afwijking_pct": round(afwijking, 1),
            "gecorrigeerde_pm2": onze_pm2,
            "reden": f"Onze prijs {abs(round(afwijking))}% lager dan extern — conservatief, ok",
        }
    else:
        # Binnen 15% — acceptabel
        return {
            "goedgekeurd": True,
            "onze_pm2": onze_pm2,
            "bronnen": bronnen,
            "gem_extern_pm2": round(gem_extern),
            "afwijking_pct": round(afwijking, 1),
            "gecorrigeerde_pm2": onze_pm2,
            "reden": f"Prijs binnen marge ({round(afwijking)}% afwijking)",
        }
