"""
Bouwkundige checklist generator — per bouwperiode + label + type.

Bedoeld als bezichtigings-hulp. Geen garantie, maar vangt 80% van de
verwachte aandachtspunten zonder dure keuring op elk pand.

Bronnen: Vereniging Eigen Huis, Bouw Garant, Perfectkeur KB's 2023-2025.
"""
from __future__ import annotations

from typing import Optional


def genereer_checklist(
    bouwjaar: Optional[int] = None,
    energie_label: str = "",
    type_woning: str = "",
    is_rijksmonument: bool = False,
) -> list:
    """Retourneer lijst van checks: [{categorie, punt, urgentie}].
    urgentie: 'hoog' | 'middel' | 'laag'
    """
    checks = []
    bj = bouwjaar or 0
    label = (energie_label or "").upper().strip()[:1]
    tw = (type_woning or "").lower()

    # ── Leeftijd-gebonden (bouwperiode) ──
    if bj and bj < 1940:
        checks += [
            {"categorie": "Constructie", "punt": "Houten vloeren — check op houtworm, schimmel, veerkracht", "urgentie": "hoog"},
            {"categorie": "Constructie", "punt": "Fundering op staal/houten palen — evt verzakking", "urgentie": "hoog"},
            {"categorie": "Water", "punt": "Loden waterleidingen nog aanwezig? (vervang verplicht)", "urgentie": "hoog"},
            {"categorie": "Vocht", "punt": "Kelder/kruipruimte — vochtdoorslag muren", "urgentie": "middel"},
            {"categorie": "Asbest", "punt": "Asbest in dakbeschot, leidingisolatie, vloerbedekking mogelijk", "urgentie": "hoog"},
            {"categorie": "Elektra", "punt": "Mogelijk nog stoffen omwikkelde bedrading", "urgentie": "middel"},
        ]
    elif bj and 1940 <= bj < 1975:
        checks += [
            {"categorie": "Asbest", "punt": "Asbest in plaatmateriaal (gevel, dak, CV-ruimte)", "urgentie": "hoog"},
            {"categorie": "Constructie", "punt": "Beton-rot in galerijen/balkons (check wapening)", "urgentie": "hoog"},
            {"categorie": "Isolatie", "punt": "Vrijwel zeker ongeïsoleerd — spouw + dak + vloer", "urgentie": "middel"},
            {"categorie": "Water", "punt": "Galvaniseerd of koperleiding — check lekkagesporen", "urgentie": "middel"},
            {"categorie": "Ramen", "punt": "Waarschijnlijk enkel/isolerend dubbel glas (HR++ zelden)", "urgentie": "middel"},
            {"categorie": "Elektra", "punt": "Check groepenkast — voldoet aan 2020-eisen?", "urgentie": "middel"},
        ]
    elif bj and 1975 <= bj < 1992:
        checks += [
            {"categorie": "Isolatie", "punt": "Spouwisolatie meestal aanwezig, dakisolatie variabel", "urgentie": "middel"},
            {"categorie": "Constructie", "punt": "Kierdichting + thermische bruggen controleren", "urgentie": "laag"},
            {"categorie": "CV", "punt": "CV-ketel mogelijk 20+ jaar — vervanging plannen", "urgentie": "middel"},
            {"categorie": "Ramen", "punt": "Mogelijk dubbelglas, HR++ meestal bij latere upgrade", "urgentie": "laag"},
            {"categorie": "Asbest", "punt": "Klein deel asbest-afwerkingen nog mogelijk", "urgentie": "laag"},
        ]
    elif bj and 1992 <= bj < 2010:
        checks += [
            {"categorie": "Isolatie", "punt": "HR++ en vloer/dak/spouw isolatie standaard — meet thermisch", "urgentie": "laag"},
            {"categorie": "CV", "punt": "HR-ketel origineel mogelijk toe aan vervanging (15-20 jr)", "urgentie": "middel"},
            {"categorie": "Afwerking", "punt": "Standaard afwerking — upgrade keuken/badkamer gangbaar", "urgentie": "laag"},
        ]
    elif bj and bj >= 2010:
        checks += [
            {"categorie": "Algemeen", "punt": "Recente bouw — focus op afwerkingskwaliteit en VvE-onderhoud", "urgentie": "laag"},
        ]

    # ── Energielabel-gebonden ──
    if label in ("E", "F", "G"):
        checks += [
            {"categorie": "Verhuurverbod 2028", "punt": f"Label {label} — verhuurverbod dreigt, energielabel B verplicht voor verhuur 2028", "urgentie": "hoog"},
            {"categorie": "Energie", "punt": "Ramen HR++/HR+++ vervangen + isolatie verbeteren vereist", "urgentie": "hoog"},
        ]
    elif label in ("C", "D"):
        checks += [
            {"categorie": "Energie", "punt": f"Label {label} — met gerichte ingrepen naar A/B te tillen", "urgentie": "middel"},
        ]

    # ── Type-gebonden ──
    if "appartement" in tw or "portiek" in tw or "galerij" in tw:
        checks += [
            {"categorie": "VvE", "punt": "VvE gezond? Reserves voor groot onderhoud aanwezig?", "urgentie": "hoog"},
            {"categorie": "VvE", "punt": "MJOP (meerjarenonderhoudsplan) opvragen en lezen", "urgentie": "hoog"},
            {"categorie": "VvE", "punt": "Geluidsisolatie tussen woningen — NEN 5077 check", "urgentie": "middel"},
        ]
    if "herenhuis" in tw or (bj and bj < 1930):
        checks += [
            {"categorie": "Monumentenstatus", "punt": "Check of straat/pand op gemeentelijk/rijks monumentenregister staat", "urgentie": "hoog"},
        ]

    # ── Monumentstatus ──
    if is_rijksmonument:
        checks += [
            {"categorie": "Monument", "punt": "Rijksmonument — alleen onderhoud/reno na omgevingsvergunning + erfgoed-akkoord", "urgentie": "hoog"},
            {"categorie": "Monument", "punt": "Subsidie mogelijk voor historische elementen (Sim-regeling RCE)", "urgentie": "laag"},
            {"categorie": "Monument", "punt": "Verzekering monumenten-specifiek (hogere premie)", "urgentie": "middel"},
        ]

    # ── Universele dingen (altijd checken) ──
    checks += [
        {"categorie": "Algemeen", "punt": "Bouwkundige keuring door erkend keurder (bij kans)", "urgentie": "hoog"},
        {"categorie": "Algemeen", "punt": "Eigenaars-historie & eerdere WOZ-bezwaren opvragen", "urgentie": "laag"},
        {"categorie": "Algemeen", "punt": "Check bestemmingsplan (omgevingsplan) voor wijzigingsplannen omgeving", "urgentie": "middel"},
        {"categorie": "Algemeen", "punt": "Buurt-parkeerdruk + OV-bereikbaarheid voor toekomstige verkoop", "urgentie": "laag"},
    ]

    return checks
