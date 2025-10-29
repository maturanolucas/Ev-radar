# radar_bot.py
# Bot para monitorar partidas e enviar alertas EV+ via Telegram
# Feito para deploy automático no Render.com

import os
import time
import requests
import json
import logging
from bs4 import BeautifulSoup
from urllib.parse import quote_plus

# -----------------------
# CONFIGURAÇÕES BÁSICAS
# -----------------------
TG_BOT_TOKEN = os.environ.get('TG_BOT_TOKEN')
TG_CHAT_ID = os.environ.get('TG_CHAT_ID')

POLL_INTERVAL = int(os.environ.get('POLL_INTERVAL', '60'))  # tempo entre verificações (segundos)
EV_THRESHOLD = float(os.environ.get('EV_THRESHOLD', '0.02'))  # valor mínimo de EV para alerta
CMD_MIN = float(os.environ.get('CMD_MIN', '0.95'))  # confiança emocional mínima
FALLBACK_ODD = float(os.environ.get('FALLBACK_ODD', '1.50'))

MONITORED_LEAGUES = os.environ.get('MONITORED_LEAGUES',
    'Premier League,La Liga,Serie A,Bundesliga,Ligue 1,Championship,Brazil Serie A,Serie B').split(',')

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; EVRadarBot/1.0)"}

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
log = logging.getLogger("EVRadar")

# -----------------------
# TELEGRAM
# -----------------------
def send_telegram_message(text, url=None):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        log.error("Faltam TG_BOT_TOKEN ou TG_CHAT_ID.")
        return
    payload = {
        "chat_id": TG_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False
    }
    if url:
        payload["reply_markup"] = json.dumps({
            "inline_keyboard": [[{"text": "Abrir partida", "url": url}]]
        })
    r = requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage", data=payload)
    if r.status_code != 200:
        log.error("Erro Telegram: %s", r.text)

# -----------------------
# COLETA DE DADOS
# -----------------------
def get_live_matches():
    """Obtém partidas ao vivo do SofaScore"""
    url = "https://www.sofascore.com/football/live"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, "lxml")
        matches = []
        for item in soup.select(".event-row")[:50]:
            league = item.select_one(".event-league, .tournament-name")
            teams = item.select(".team-name")
            score = item.select_one(".current-result")
            minute = item.select_one(".minute, .status")
            link = item.find("a", href=True)
            if not teams or len(teams) < 2:
                continue
            matches.append({
                "league": league.get_text(strip=True) if league else "",
                "home": teams[0].get_text(strip=True),
                "away": teams[1].get_text(strip=True),
                "score": score.get_text(strip=True) if score else "0–0",
                "minute": minute.get_text(strip=True) if minute else "",
                "url": f"https://www.sofascore.com{link['href']}" if link else ""
            })
        return matches
    except Exception as e:
        log.error("Erro ao buscar partidas: %s", e)
        return []

def get_superbet_odds(home, away):
    """Busca cotação over no Superbet"""
    query = quote_plus(f"{home} {away}")
    url = f"https://www.superbet.com.br/search?query={query}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, "lxml")
        odd = soup.select_one(".odd, .odds__value")
        if odd:
            val = odd.get_text(strip=True).replace(",", ".")
            return float(val)
    except Exception:
        pass
    return None

# -----------------------
# MODELO SIMPLES DE EV
# -----------------------
def calc_p_model(match):
    # Modelo simplificado (será aprimorado conforme base cresce)
    minute = 0
    try:
        minute = int(''.join(filter(str.isdigit, match.get("minute", "0"))))
    except:
        pass
    base = 0.55
    if minute >= 70:
        base += 0.05
    if "cup" in match["league"].lower() or "libertadores" in match["league"].lower():
        base += 0.05
    if "0–0" in match["score"]:
        base -= 0.1
    elif "1–1" in match["score"] or "2–2" in match["score"]:
        base += 0.03
    return min(max(base, 0.01), 0.99)

def calc_ev(p_model, odd):
    return p_model * (odd - 1) - (1 - p_model)

# -----------------------
# LOOP PRINCIPAL
# -----------------------
def main():
    sent = set()
    while True:
        log.info("Buscando partidas ao vivo...")
        matches = get_live_matches()
        log.info("Encontradas: %d partidas", len(matches))
        for m in matches:
            # filtrar ligas
            if not any(l.lower().strip() in m["league"].lower() for l in MONITORED_LEAGUES):
                continue
            # minuto de interesse
            try:
                minute = int(''.join(filter(str.isdigit, m["minute"])))
            except:
                minute = 0
            if minute < 45 or minute > 80:
                continue

            key = f"{m['home']}-{m['away']}"
            if key in sent:
                continue

            odd = get_superbet_odds(m["home"], m["away"]) or FALLBACK_ODD
            p_model = calc_p_model(m)
            ev = calc_ev(p_model, odd)

            log.info("%s x %s | %s | odd %.2f | EV %.3f", m["home"], m["away"], m["league"], odd, ev)

            if ev >= EV_THRESHOLD:
                msg = (
                    f"🚨 *EV+ Detectado*\n"
                    f"⚽ {m['league']} | {m['minute']}\n"
                    f"*{m['home']}* – *{m['away']}*\n\n"
                    f"*Over 2.5* @ *{odd:.2f}*\n"
                    f"P_model: *{p_model:.3f}* | EV: *{ev:.3f}*\n"
                    f"[Abrir no SofaScore]({m['url']})"
                )
                send_telegram_message(msg)
                sent.add(key)

        log.info("Ciclo completo, aguardando %d segundos...", POLL_INTERVAL)
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
