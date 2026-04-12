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

# ── Database ──────────────────────────────────────────────────────────────────
DB_PATH = "panden.db"

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL = "INFO"
