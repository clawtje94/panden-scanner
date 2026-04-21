"""
Panden Scanner — Configuratie.
Pas TELEGRAM_TOKEN en TELEGRAM_CHAT_ID aan na aanmaken van de bot.
"""
import os

# ── Telegram ──────────────────────────────────────────────────────────────────
# 1. Open Telegram → zoek @BotFather → stuur /newbot → volg stappen
# 2. Kopieer het token dat je krijgt naar TELEGRAM_TOKEN
# 3. Start een gesprek met je bot, ga dan naar:
#    https://api.telegram.org/bot<TOKEN>/getUpdates
#    Zoek naar "chat" -> "id" → dat is je TELEGRAM_CHAT_ID
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "VERVANG_MET_JOUW_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "VERVANG_MET_JOUW_CHAT_ID")

# ── EP-Online (RVO energielabel) ──────────────────────────────────────────────
# Gratis key aanvragen op https://apikey.ep-online.nl
# Key in Authorization-header (geen 'Bearer' prefix).
EP_ONLINE_API_KEY = os.environ.get("EP_ONLINE_API_KEY", "")

# ── Altum AI (gratis tier Kadaster-koopsom + modelwaarde) ────────────────────
# Registreer op https://altum.ai/sign-up, 50 calls/maand gratis.
# Scanner roept alleen aan voor top-deals (dealscore ≥ 65) om budget te sparen.
ALTUM_API_KEY = os.environ.get("ALTUM_API_KEY", "")

# ── Zoekgebied ────────────────────────────────────────────────────────────────
STEDEN_FUNDA = [
    "den-haag", "rotterdam", "delft", "leiden",
    "zoetermeer", "schiedam", "rijswijk", "dordrecht",
    "westland", "pijnacker-nootdorp",
]

# ── Fix & Flip criteria ───────────────────────────────────────────────────────
FIX_FLIP = {
    "max_aankoopprijs":   350_000,   # Max aankoopprijs in €
    "min_opp_m2":         55,        # Min woonoppervlak in m²
    "min_marge_pct":      11.0,      # Min nettomarge % voor notificatie
    "renovatie_per_m2":   750,       # Schatting renovatiekosten per m²
    "verwacht_verkoop_m2": 4_800,    # Verwachte verkoopprijs per m² na renovatie
    "looptijd_maanden":   9,
    "ovb_pct":            8.0,       # OVB 2026 niet-hoofdverblijf woning
    "rente_pct":          8.0,
}

# ── Splitsing criteria ────────────────────────────────────────────────────────
SPLITSING = {
    "min_opp_m2":         150,       # Min totaal woonoppervlak
    "max_aankoopprijs":   900_000,
    "min_marge_pct":      14.0,
    "renovatie_per_m2":   1_400,
    "verwacht_verkoop_m2": 5_000,
    "min_units":          2,
    "looptijd_maanden":   18,
    "ovb_pct":            8.0,
    "rente_pct":          8.0,
}

# ── Transformatie criteria (commercieel → wonen) ──────────────────────────────
TRANSFORMATIE = {
    "max_aankoopprijs":   2_000_000,
    "min_opp_m2":         200,
    "max_prijs_per_m2":   2_500,     # Max commerciële aankoopprijs/m² BVO
    "min_marge_pct":      14.0,
    "renovatie_per_m2":   1_700,
    "verwacht_verkoop_m2": 5_200,
    "looptijd_maanden":   24,
    "ovb_pct":            10.4,      # OVB 2026 zakelijk
    "rente_pct":          8.0,
}

# ── Verkoop-kwaliteit filter (kill-switch bij slechte data) ──────────────────
# Als scanner alleen "onvoldoende" verkoop-data heeft EN worst-case marge
# onder deze drempel ligt, dan skippen. Anders alleen flaggen.
VERKOOP_KWALITEIT = {
    "skip_bij_onvoldoende_confidence":  True,
    "min_worst_marge_bij_onvoldoende":  5.0,     # % netto marge
    "min_worst_marge_bij_laag":         8.0,
    "min_refs_voor_commit":             3,
}

# ── Motion signals (motivated seller detectie) ───────────────────────────────
SIGNALEN = {
    "motivated_dagen_online":   120,     # dagen online waarna "lang online" telt
    "motivated_dagen_lang":     180,
    "motivated_dagen_zeer_lang": 365,
    "prijsverlaging_min_pct":   1.0,     # onder deze drempel negeren we ruis
    "prijsverlaging_sterk_pct": 5.0,     # hierboven = sterk motivated signaal
    "makelaarswissel_dagen":    90,      # wissel binnen X dagen = gefrustreerd
    "motivated_score_drempel":  5,       # vanaf deze score flag voor Telegram
}

# ── Database ──────────────────────────────────────────────────────────────────
DB_PATH = "panden.db"

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL = "INFO"
