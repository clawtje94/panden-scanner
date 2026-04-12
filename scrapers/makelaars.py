"""
Makelaar-website scrapers — 40+ makelaars in Zuid-Holland.

Platform-types:
  1. OGonline/SiteLive — JSON API /nl/realtime-listings/consumer
  2. Ooms — JSON API /api/properties/available.json
  3. Kolpa — REST API /api/listings
  4. WordPress+Realworks — HTML scraping
  5. TopSite — HTML scraping
  6. DailyCMS — HTML scraping
  7. Requests+BeautifulSoup — generiek HTML
"""
import logging
import re
import time
import random
from typing import List

import requests
from bs4 import BeautifulSoup
from models import Property

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "nl-NL,nl;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ══════════════════════════════════════════════════════════════════════════════
# MAKELAAR CONFIGURATIE — alle makelaars per platform
# ══════════════════════════════════════════════════════════════════════════════

# Platform 1: OGonline/SiteLive — JSON API
OGONLINE_MAKELAARS = [
    {"naam": "Hekking", "url": "https://www.hekking.nl/nl/realtime-listings/consumer", "stad": "Den Haag"},
    {"naam": "Nelisse", "url": "https://www.nelisse.nl/nl/realtime-listings/consumer", "stad": "Den Haag"},
    {"naam": "BjornD", "url": "https://www.bjornd.nl/nl/realtime-listings/consumer", "stad": "Delft"},
    {"naam": "Doen Makelaars", "url": "https://www.doenmakelaars.com/nl/realtime-listings/consumer", "stad": "Leiden"},
    {"naam": "Reibestein", "url": "https://www.reibestein.nl/nl/realtime-listings/commercial", "stad": "Den Haag", "commercieel": True},
    {"naam": "Langezaal", "url": "https://www.langezaal.nl/nl/realtime-listings/consumer", "stad": "Den Haag"},
    {"naam": "Oosterhof", "url": "https://www.oosterhofmakelaars.nl/nl/realtime-listings/consumer", "stad": "Den Haag"},
    {"naam": "Rottgering", "url": "https://www.rottgering.nl/nl/realtime-listings/consumer", "stad": "Den Haag"},
    {"naam": "Agterberg", "url": "https://www.agterbergmakelaardij.nl/nl/realtime-listings/consumer", "stad": "Den Haag"},
    {"naam": "Hooghlanden", "url": "https://www.hooghlanden.nl/nl/realtime-listings/consumer", "stad": "Den Haag"},
    {"naam": "De Lange BM", "url": "https://delangemakelaars.nl/nl/realtime-listings/commercial", "stad": "Den Haag", "commercieel": True},
    {"naam": "JNW", "url": "https://www.jnwmakelaars.nl/nl/realtime-listings/commercial", "stad": "Den Haag", "commercieel": True},
    {"naam": "Blok BM", "url": "https://blokmakelaars.nl/nl/realtime-listings/commercial", "stad": "Rotterdam", "commercieel": True},
    {"naam": "Dupont", "url": "https://www.dupont.nl/nl/realtime-listings/consumer", "stad": "Schiedam"},
    {"naam": "Hogenboom", "url": "https://www.hogenboommakelaardij.nl/nl/realtime-listings/consumer", "stad": "Leidschendam"},
    {"naam": "Hoogenraad", "url": "https://www.hoogenraad.nl/nl/realtime-listings/consumer", "stad": "Rijswijk"},
    {"naam": "Olsthoorn", "url": "https://www.olsthoornmakelaars.nl/nl/realtime-listings/consumer", "stad": "Delft"},
    {"naam": "Fides Leiden", "url": "https://www.fidesmakelaarsleiden.nl/nl/realtime-listings/consumer", "stad": "Leiden"},
    {"naam": "Kerkvliet", "url": "https://kerkvlietmakelaars.nl/nl/realtime-listings/consumer", "stad": "Leiden"},
    {"naam": "Kompas", "url": "https://www.kompasmakelaardij.nl/nl/realtime-listings/consumer", "stad": "Leiden"},
    {"naam": "Holland Huis", "url": "https://www.holland-huis.nl/nl/realtime-listings/consumer", "stad": "Zoetermeer"},
    {"naam": "Schieland Borsboom", "url": "https://www.schielandborsboom.nl/nl/realtime-listings/consumer", "stad": "Zoetermeer"},
    {"naam": "Boogerman", "url": "https://boogerman.nl/nl/realtime-listings/consumer", "stad": "Dordrecht"},
    {"naam": "Vijfvinkel", "url": "https://vijfvinkel.nl/nl/realtime-listings/consumer", "stad": "Dordrecht"},
]


def _scrape_ogonline(config: dict) -> List[Property]:
    """Scrape OGonline/SiteLive JSON API."""
    results = []
    naam = config["naam"]
    is_comm = config.get("commercieel", False)

    try:
        r = requests.get(config["url"], headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return results

        data = r.json()
        if not isinstance(data, list):
            return results

        for item in data:
            try:
                # Filter: alleen koop
                is_koop = item.get("isSales", False)
                sales_price = item.get("salesPrice", 0) or 0
                if not is_koop or sales_price <= 0:
                    continue

                # Filter: ALLEEN status "Beschikbaar" doorlaten
                status = str(item.get("status", "")).lower().strip()
                if status != "beschikbaar" and status != "available" and status != "nieuw" and status != "":
                    continue  # alles behalve beschikbaar/nieuw → skip

                adres = item.get("address", "") or ""
                stad = item.get("city", config["stad"]) or config["stad"]
                postcode = item.get("zipcode", "") or ""
                opp = item.get("livingSurface", 0) or 0
                kamers = item.get("rooms", 0) or 0
                url = item.get("url", "")
                # OGonline URLs zijn relatief — base URL toevoegen
                if url and not url.startswith("http"):
                    base = config["url"].split("/nl/")[0]
                    url = base + url
                if sales_price < 25_000 or opp <= 0:
                    continue

                # Filter Zuid-Holland
                zh_steden = ["den haag", "rotterdam", "delft", "leiden", "zoetermeer",
                             "schiedam", "rijswijk", "dordrecht", "westland", "leidschendam",
                             "voorburg", "pijnacker", "nootdorp", "capelle", "vlaardingen",
                             "gouda", "alphen", "wassenaar"]
                stad_lower = stad.lower()
                if not any(s in stad_lower for s in zh_steden):
                    continue

                prop = Property(
                    source=f"mkl_{naam.lower().replace(' ','_')}",
                    url=url,
                    adres=adres,
                    stad=stad,
                    postcode=postcode,
                    prijs=int(sales_price),
                    opp_m2=int(opp),
                    prijs_per_m2=round(sales_price / opp) if opp > 0 else 0,
                    kamers=int(kamers),
                    is_commercieel=is_comm,
                )
                results.append(prop)
            except Exception as e:
                logger.debug("%s parse fout: %s", naam, e)

    except Exception as e:
        logger.debug("%s fout: %s", naam, e)

    return results


# Platform 2: Ooms JSON API
def _scrape_ooms() -> List[Property]:
    results = []
    try:
        r = requests.get("https://ooms.com/api/properties/available.json", headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return results
        data = r.json()
        objects = data.get("objects", []) if isinstance(data, dict) else data

        zh_steden = ["den haag", "rotterdam", "delft", "leiden", "zoetermeer",
                     "schiedam", "rijswijk", "dordrecht", "capelle", "spijkenisse",
                     "vlaardingen", "barendrecht", "hoogvliet", "ridderkerk"]

        for item in objects:
            try:
                # Status check: ALLEEN beschikbaar doorlaten
                status = str(item.get("availability_status", item.get("status", ""))).lower().strip()
                if status != "beschikbaar" and status != "available" and status != "":
                    continue

                buy_price = item.get("buy_price", 0) or 0
                if buy_price < 25_000:
                    continue
                opp = item.get("usable_area_living_function", 0) or 0
                if opp <= 0:
                    continue
                stad = item.get("place", "") or ""
                if not any(s in stad.lower() for s in zh_steden):
                    continue

                adres = f"{item.get('street_name', '')} {item.get('house_number', '')}".strip()
                suffix = item.get("house_number_addition", "")
                if suffix:
                    adres += f" {suffix}"

                prop = Property(
                    source="mkl_ooms",
                    url=item.get("url", f"https://ooms.com/wonen/aanbod/{item.get('slug', '')}"),
                    adres=adres,
                    stad=stad,
                    postcode=item.get("zip_code", "") or "",
                    prijs=int(buy_price),
                    opp_m2=int(opp),
                    prijs_per_m2=round(buy_price / opp) if opp > 0 else 0,
                    kamers=int(item.get("amount_of_rooms", 0) or 0),
                )
                results.append(prop)
            except Exception as e:
                logger.debug("Ooms parse fout: %s", e)

    except Exception as e:
        logger.error("Ooms fout: %s", e)

    logger.info("Ooms: %d panden", len(results))
    return results


# Platform 3: Kolpa REST API
def _scrape_kolpa() -> List[Property]:
    results = []
    zh_steden = ["den haag", "rotterdam", "delft", "leiden", "zoetermeer",
                 "schiedam", "rijswijk", "dordrecht", "capelle", "spijkenisse"]

    for page in range(1, 20):
        try:
            r = requests.get(
                f"https://www.kolpa.nl/api/listings?limit=50&page={page}&depth=0",
                headers=HEADERS, timeout=15,
            )
            if r.status_code != 200:
                break
            data = r.json()
            docs = data.get("docs", [])
            if not docs:
                break

            for doc in docs:
                try:
                    status = doc.get("status", "")
                    if status != "available":
                        continue
                    price_data = doc.get("price", {})
                    sales = price_data.get("sales", price_data.get("specifications", {}))
                    if isinstance(sales, dict):
                        prijs = sales.get("amount", 0) or 0
                    elif isinstance(sales, (int, float)):
                        prijs = int(sales)
                    else:
                        continue
                    if prijs < 25_000:
                        continue

                    addr = doc.get("address", {})
                    stad = addr.get("city", "") or ""
                    if not any(s in stad.lower() for s in zh_steden):
                        continue
                    opp = 0
                    details = doc.get("details", {})
                    surface = details.get("surface", {})
                    opp = surface.get("amount", 0) or 0
                    if opp <= 0:
                        continue

                    adres = f"{addr.get('street', '')} {addr.get('houseNumber', '')}".strip()
                    kamers = details.get("rooms", {}).get("amount", 0) or 0

                    # Kolpa URL: /aanbod/{city}/{slug}/{id}
                    kolpa_city = stad.lower().replace(" ", "-")
                    kolpa_slug = doc.get("slug", "")
                    kolpa_id = doc.get("id", "")
                    kolpa_url = f"https://www.kolpa.nl/aanbod/{kolpa_city}/{kolpa_slug}/{kolpa_id}"

                    prop = Property(
                        source="mkl_kolpa",
                        url=kolpa_url,
                        adres=adres,
                        stad=stad,
                        postcode=addr.get("postalCode", "") or "",
                        prijs=int(prijs),
                        opp_m2=int(opp),
                        prijs_per_m2=round(prijs / opp) if opp > 0 else 0,
                        kamers=int(kamers),
                    )
                    results.append(prop)
                except Exception as e:
                    logger.debug("Kolpa parse fout: %s", e)

            if not data.get("hasNextPage", False):
                break
            time.sleep(0.3)

        except Exception as e:
            logger.error("Kolpa fout pagina %d: %s", page, e)
            break

    logger.info("Kolpa: %d panden", len(results))
    return results


# Platform 4: WordPress + Realworks (Voorberg, Meesters)
WP_REALWORKS_MAKELAARS = [
    {
        "naam": "Meesters",
        "base": "https://www.meestersmakelaars.nl",
        "url_pattern": "/woningen/page/{page}/",
        "first_page": "/woningen/",
        "selectors": {
            "container": "div.item-inner",
            "adres": "a.h5",
            "prijs": "p.price",
            "opp": "span.living-square-meters",
            "kamers": "span.rooms-count",
            "link": "a.h5",
            "status": "p.avaiable",
        },
    },
    {
        "naam": "Voorberg",
        "base": "https://www.voorberg.nl",
        "url_pattern": "/woningaanbod/koop/page/{page}/",
        "first_page": "/woningaanbod/koop/",
        "selectors": {
            "container": "div.object",
            "adres": "span.object-street",
            "prijs": "span.object-price-value",
            "opp": "span.object-surface-value",
            "link": "a",
            "status": "div.object-status-beschikbaar",
        },
    },
]


def _scrape_wp_realworks(config: dict, max_pages: int = 5) -> List[Property]:
    results = []
    naam = config["naam"]
    base = config["base"]
    sel = config["selectors"]

    for page_num in range(1, max_pages + 1):
        url = base + (config["first_page"] if page_num == 1 else config["url_pattern"].format(page=page_num))
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                break
            soup = BeautifulSoup(r.text, "lxml")
            items = soup.select(sel["container"])
            if not items:
                break

            for item in items:
                try:
                    # Status check
                    if sel.get("status"):
                        status_el = item.select_one(sel["status"])
                        if status_el and "verkocht" in status_el.get_text().lower():
                            continue

                    adres_el = item.select_one(sel["adres"])
                    adres = adres_el.get_text(strip=True) if adres_el else ""

                    prijs_el = item.select_one(sel["prijs"])
                    prijs_txt = prijs_el.get_text(strip=True) if prijs_el else ""
                    prijs_clean = re.sub(r'[^\d]', '', prijs_txt.split("k.k.")[0].split("v.o.n.")[0])
                    prijs = int(prijs_clean) if prijs_clean else 0

                    opp = 0
                    if sel.get("opp"):
                        opp_el = item.select_one(sel["opp"])
                        if opp_el:
                            opp_match = re.search(r'(\d+)', opp_el.get_text())
                            opp = int(opp_match.group(1)) if opp_match else 0

                    kamers = 0
                    if sel.get("kamers"):
                        kamers_el = item.select_one(sel["kamers"])
                        if kamers_el:
                            kamers_match = re.search(r'(\d+)', kamers_el.get_text())
                            kamers = int(kamers_match.group(1)) if kamers_match else 0

                    link_el = item.select_one(sel["link"])
                    href = link_el.get("href", "") if link_el else ""
                    full_url = href if href.startswith("http") else base + href

                    if prijs < 25_000 or opp <= 0:
                        continue

                    prop = Property(
                        source=f"mkl_{naam.lower()}",
                        url=full_url,
                        adres=adres,
                        stad=config.get("stad", ""),
                        prijs=prijs,
                        opp_m2=opp,
                        prijs_per_m2=round(prijs / opp) if opp > 0 else 0,
                        kamers=kamers,
                    )
                    results.append(prop)
                except Exception as e:
                    logger.debug("%s parse fout: %s", naam, e)

            time.sleep(random.uniform(0.5, 1.0))
        except Exception as e:
            logger.debug("%s fout pagina %d: %s", naam, page_num, e)
            break

    return results


# Platform 5: TopSite (Beeuwkes, Prins, Waltmann)
TOPSITE_MAKELAARS = [
    {"naam": "Beeuwkes", "base": "https://www.beeuwkes.nl", "url": "/aanbod", "stad": "Den Haag"},
    {"naam": "Prins", "base": "https://www.prinsmakelaardij.nl", "url": "/aanbod", "stad": "Rotterdam"},
    {"naam": "Waltmann", "base": "https://www.waltmann.com", "url": "/aanbod/", "stad": "Dordrecht"},
]


def _scrape_topsite(config: dict, max_pages: int = 5) -> List[Property]:
    results = []
    naam = config["naam"]
    base = config["base"]
    zh_steden = ["den haag", "rotterdam", "delft", "leiden", "zoetermeer",
                 "schiedam", "rijswijk", "dordrecht", "capelle", "spijkenisse",
                 "sliedrecht", "zwijndrecht", "papendrecht", "barendrecht",
                 "gorinchem", "vlaardingen", "gouda"]

    for page_num in range(1, max_pages + 1):
        url = base + config["url"] + (f"?page={page_num}" if page_num > 1 else "")
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                break
            soup = BeautifulSoup(r.text, "lxml")

            cards = soup.select("a.property, a.property.d-flex")
            if not cards:
                break

            for card in cards:
                try:
                    href = card.get("href", "")
                    full_url = base + href if href.startswith("/") else href

                    title_el = card.select_one("span.title")
                    adres = title_el.get_text(strip=True) if title_el else ""

                    city_el = card.select_one("span.city")
                    stad = city_el.get_text(strip=True).title() if city_el else config["stad"]

                    if not any(s in stad.lower() for s in zh_steden):
                        continue

                    prijs_el = card.select_one("span.price")
                    prijs_txt = prijs_el.get_text(strip=True) if prijs_el else ""
                    prijs_clean = re.sub(r'[^\d]', '', prijs_txt.split("k.k.")[0].split("v.o.n.")[0].replace(",-", ""))
                    prijs = int(prijs_clean) if prijs_clean else 0

                    opp = 0
                    all_text = card.get_text()
                    opp_match = re.search(r'(\d+)\s*m', all_text)
                    if opp_match:
                        opp = int(opp_match.group(1))

                    if prijs < 25_000:
                        continue

                    prop = Property(
                        source=f"mkl_{naam.lower()}",
                        url=full_url,
                        adres=adres,
                        stad=stad,
                        prijs=prijs,
                        opp_m2=opp,
                        prijs_per_m2=round(prijs / opp) if opp > 0 else 0,
                    )
                    results.append(prop)
                except Exception as e:
                    logger.debug("%s parse fout: %s", naam, e)

            time.sleep(random.uniform(0.5, 1.0))
        except Exception as e:
            logger.debug("%s fout: %s", naam, e)
            break

    return results


# Platform 6: DailyCMS (Kooyman)
def _scrape_kooyman() -> List[Property]:
    results = []
    try:
        r = requests.get("https://www.kooyman.com/kopen/", headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return results
        soup = BeautifulSoup(r.text, "lxml")

        for card in soup.select("div.realEstateObject"):
            try:
                link = card.select_one("a.realEstateObjectLink")
                if not link:
                    continue
                href = link.get("href", "")
                full_url = "https://www.kooyman.com" + href if href.startswith("/") else href

                h2 = card.select_one(".h2")
                adres = h2.get_text(strip=True) if h2 else ""

                city_el = card.select_one(".place")
                stad = city_el.get_text(strip=True) if city_el else ""

                prijs_el = card.select_one(".price")
                prijs_txt = prijs_el.get_text(strip=True) if prijs_el else ""
                prijs_clean = re.sub(r'[^\d]', '', prijs_txt.split("k.k.")[0].replace(",-", ""))
                prijs = int(prijs_clean) if prijs_clean else 0

                opp_el = card.select_one(".surface")
                opp_txt = opp_el.get_text(strip=True) if opp_el else ""
                opp_match = re.search(r'(\d+)', opp_txt)
                opp = int(opp_match.group(1)) if opp_match else 0

                kamers_el = card.select_one(".bedrooms")
                kamers = 0
                if kamers_el:
                    km = re.search(r'(\d+)', kamers_el.get_text())
                    kamers = int(km.group(1)) if km else 0

                if prijs < 25_000:
                    continue

                prop = Property(
                    source="mkl_kooyman",
                    url=full_url,
                    adres=adres,
                    stad=stad,
                    prijs=prijs,
                    opp_m2=opp,
                    prijs_per_m2=round(prijs / opp) if opp > 0 else 0,
                    kamers=kamers,
                )
                results.append(prop)
            except Exception as e:
                logger.debug("Kooyman parse fout: %s", e)

    except Exception as e:
        logger.error("Kooyman fout: %s", e)

    logger.info("Kooyman: %d panden", len(results))
    return results


# ══════════════════════════════════════════════════════════════════════════════
# HOOFDFUNCTIE
# ══════════════════════════════════════════════════════════════════════════════

def scrape_makelaars() -> List[Property]:
    """Scrape alle 40+ makelaars en combineer resultaten."""
    results: List[Property] = []

    # ── OGonline makelaars (JSON API — snel) ──
    for config in OGONLINE_MAKELAARS:
        try:
            panden = _scrape_ogonline(config)
            if panden:
                logger.info("%s: %d panden", config["naam"], len(panden))
            results.extend(panden)
            time.sleep(0.2)
        except Exception as e:
            logger.debug("%s fout: %s", config["naam"], e)

    # ── Ooms (JSON API) ──
    try:
        results.extend(_scrape_ooms())
    except Exception as e:
        logger.error("Ooms fout: %s", e)

    # ── Kolpa (REST API) ──
    try:
        results.extend(_scrape_kolpa())
    except Exception as e:
        logger.error("Kolpa fout: %s", e)

    # ── WordPress + Realworks ──
    for config in WP_REALWORKS_MAKELAARS:
        try:
            panden = _scrape_wp_realworks(config)
            if panden:
                logger.info("%s: %d panden", config["naam"], len(panden))
            results.extend(panden)
        except Exception as e:
            logger.debug("%s fout: %s", config["naam"], e)

    # ── TopSite makelaars ──
    for config in TOPSITE_MAKELAARS:
        try:
            panden = _scrape_topsite(config)
            if panden:
                logger.info("%s: %d panden", config["naam"], len(panden))
            results.extend(panden)
        except Exception as e:
            logger.debug("%s fout: %s", config["naam"], e)

    # ── Kooyman (DailyCMS) ──
    try:
        results.extend(_scrape_kooyman())
    except Exception as e:
        logger.error("Kooyman fout: %s", e)

    logger.info("Makelaars totaal: %d panden van %d bronnen",
                len(results), len(OGONLINE_MAKELAARS) + 6)
    return results
