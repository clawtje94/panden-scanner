# Panden Scanner Zuid-Holland

Dagelijkse automatische scanner voor vastgoed kansen in Zuid-Holland.
Zoekt naar fix & flip, splitsing en transformatie projecten met positief rendement.

## Features
- Scrapet Funda.nl (Playwright), Funda in Business, Pararius, Bedrijfspand.com
- Berekent automatisch netto marge, ROI en verwachte winst
- Filtert op minimale marge (11-14%)
- Stuurt Telegram notificatie bij nieuwe kansen
- Draait dagelijks om 07:00 via GitHub Actions (gratis)
- Slaat alle resultaten op in SQLite database

## Setup in 5 stappen

### 1. Telegram bot aanmaken
1. Open Telegram, zoek **@BotFather**, stuur `/newbot`
2. Kopieer je **bot token**
3. Start een gesprek met je bot
4. Ga naar `https://api.telegram.org/bot<TOKEN>/getUpdates`
5. Zoek `"chat": {"id": ...}` — dat is je **chat ID**

### 2. GitHub Secrets instellen
Ga naar je repo > Settings > Secrets > New repository secret:
- `TELEGRAM_TOKEN` — jouw bot token
- `TELEGRAM_CHAT_ID` — jouw chat ID

### 3. Lokaal testen
```bash
pip install -r requirements.txt
playwright install chromium

# Zet je Telegram credentials als environment variables
export TELEGRAM_TOKEN="jouw_token"
export TELEGRAM_CHAT_ID="jouw_chat_id"
python scanner.py
```

### 4. GitHub Actions activeren
Push naar GitHub > Actions tab > workflow staat automatisch aan

### 5. Criteria aanpassen
Pas `config.py` aan:
- `FIX_FLIP["max_aankoopprijs"]` — max budget fix & flip
- `FIX_FLIP["min_marge_pct"]` — minimale marge die je wilt
- `STEDEN_FUNDA` — welke steden scannen

## Hoe werkt het financieel model?

**Fix & Flip:**
Aankoopprijs + OVB 8% + renovatie 750/m2 + rente 8% vs verwachte verkoopprijs 4.800/m2

**Splitsing:**
Aankoopprijs + OVB 8% + renovatie 1.400/m2 + splitsingsvergunning vs 2-3x 5.000/m2

**Transformatie:**
Aankoopprijs + OVB 10.4% + verbouwing 1.700/m2 + financiering vs 5.200/m2 woonoppervlak
