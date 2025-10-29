#!/usr/bin/env python3
# radar_bot.py
# EV-Radar global — envia alertas Telegram / salva radar_ev.csv
# Modo demo padrão: roda com dados de exemplo. Para produção, implemente fetch_live_matches_prod().

import os
import sys
import csv
import time
import json
import logging
from datetime import datetime
from typing import List, Dict, Any
import requests

# ---------------------------
# CONFIG / ENV
# ---------------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
EV_THRESHOLD = int(os.getenv("EV_THRESHOLD", "65"))   # score >= this -> alert
ODD_MIN = float(os.getenv("ODD_MIN", "1.50"))        # odd mínima aceitável
MAX_GAMES = int(os.getenv("MAX_GAMES", "10"))
MODE = os.getenv("MODE", "DEMO").upper()  # DEMO or PROD

HEADERS = {"User-Agent": "EVRadarBot/1.0 (+https://your.project)"}

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger("ev-radar")

# ---------------------------
# UTIL: Telegram
# ---------------------------
def send_telegram(text: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("TELEGRAM_TOKEN/CHAT_ID not set — skipping Telegram send")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, data=payload, timeout=15)
        r.raise_for_status()
        logger.info("Telegram message sent")
        return True
    except Exception as e:
        logger.exception("Error sending Telegram message: %s", e)
        return False

# ---------------------------
# HELPERS: CSV save
# ---------------------------
def save_csv(rows: List[Dict[str, Any]], path: str = "radar_ev.csv") -> None:
    header = [
        "league","home","away","minute","score",
        "xg_total","sot","pressure","odds_over25","liquidity",
        "ev_score","decision","suggestion","timestamp"
    ]
    try:
        with open(path, "w", newline='', encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=header)
            writer.writeheader()
            for r in rows:
                writer.writerow({k: r.get(k,"") for k in header})
        logger.info("Saved CSV: %s (%d rows)", path, len(rows))
    except Exception as e:
        logger.exception("Failed to save CSV: %s", e)

# ---------------------------
# EV model (replace weights with your tuned params)
# ---------------------------
def compute_ev_score(match: Dict[str, Any]) -> int:
    """
    Simple EV scoring combining multiple signals.
    Returns integer 0..100.
    """
    score = 0.0
    pressure = float(match.get("pressure", 50))  # 0..100
    xg = float(match.get("xg_total", 0.0))
    sot = float(match.get("sot", 0))
    liquidity = float(match.get("liquidity", 0))

    # Pressure -> up to 20 points
    score += (pressure / 100.0) * 20.0

    # xG mapping (0..3) -> up to 30 points
    score += min(xg / 3.0, 1.0) * 30.0

    # SOT (shots on target) -> up to 20 points (10 SOT => full)
    score += min(sot / 10.0, 1.0) * 20.0

    # Liquidity proxy bonus: scale small bonus so high-liquidity matches prioritized
    # liquidity given in currency units — we normalize roughly (caps at +10)
    try:
        score += min(liquidity / 3_000_000.0, 1.0) * 10.0
    except Exception:
        pass

    # Context (placeholder fixed bonuses — swap for real checks)
    # Example: motivation/home trailing; here simple static bonuses to reflect our heuristics
    score += 6.0  # need/importance
    score += 4.0  # historical tendency (should be replaced by real history)

    # Clamp and return integer
    score = max(0.0, min(100.0, score))
    return int(round(score))

# ---------------------------
# Decision logic
# ---------------------------
def decide_action(match: Dict[str, Any], ev_score: int) -> Dict[str,str]:
    dec = "IGNORAR"
    suggestion = "Sem stake"
    if ev_score >= EV_THRESHOLD and float(match.get("odds_over25", 99)) >= ODD_MIN:
        dec = "ENTRAR"
        suggestion = "Stake 1% (ajustar conforme banca)"
    elif 55 <= ev_score < EV_THRESHOLD:
        dec = "MONITORAR"
        suggestion = "Aguardar confirmação"
    else:
        dec = "IGNORAR"
        suggestion = "Sem stake"
    return {"decision": dec, "suggestion": suggestion}

# ---------------------------
# Message builder (minimalist visual)
# ---------------------------
def build_message(match: Dict[str,Any]) -> str:
    league = match.get("league","")
    home = match.get("home","")
    away = match.get("away","")
    minute = match.get("minute","")
    score = match.get("score","")
    xg = match.get("xg_total",0.0)
    sot = match.get("sot",0)
    pressure = match.get("pressure",0)
    odds = match.get("odds_over25","N/A")
    liquidity = match.get("liquidity",0)
    ev = match.get("ev_score",0)
    decision = match.get("decision","")
    suggestion = match.get("suggestion","")

    lines = []
    lines.append("══════════ ⚽️ EV+ GLOBAL RADAR ══════════")
    lines.append(f"{league} — {home} {score} {away} | {minute}’")
    lines.append(f"xG: {float(xg):.2f} | SOT: {sot} | Pressão: {pressure}%")
    lines.append(f"Odd Over2.5: {odds} | Liquidez: £{int(liquidity):,}")
    lines.append(f"SCORE EV+: {ev}/100 — {decision}")
    lines.append(f"👉 Sugestão: {suggestion}")
    lines.append("════════════════════════════════════════")
    return "\n".join(lines)

# ---------------------------
# DATA PROVIDERS
# ---------------------------
def fetch_live_matches_demo() -> List[Dict[str,Any]]:
    """Returns demo static list (useful for testing)."""
    demo = [
        {"id":"m1","league":"Serie A","home":"Inter","away":"Fiorentina","minute":65,"score":"1-0",
         "xg_total":1.85,"sot":8,"pressure":74,"odds_over25":1.82,"liquidity":2900000},
        {"id":"m2","league":"Ligue 1","home":"Marseille","away":"Angers","minute":74,"score":"2-1",
         "xg_total":1.52,"sot":8,"pressure":77,"odds_over25":1.50,"liquidity":2300000},
        {"id":"m3","league":"Premier League","home":"Liverpool","away":"Chelsea","minute":78,"score":"2-1",
         "xg_total":3.05,"sot":12,"pressure":79,"odds_over25":1.44,"liquidity":4200000},
        # add up to MAX_GAMES demo rows
    ]
    return demo[:MAX_GAMES]

# NOTE: Below is a placeholder function signature for production fetching.
# Implement a real scraper or API client and return the same structure as DEMO.
def fetch_live_matches_prod() -> List[Dict[str,Any]]:
    """
    PRODUCTION: implement your Sofascore/Flashscore/odds provider integration here.
    Important fields to return per match:
      - id, league, home, away, minute, score
      - xg_total (float), sot (int), pressure (0..100)
      - odds_over25 (float), liquidity (numeric)
    Example approaches:
      - Call a public JSON endpoint (some sites expose /api/ endpoints) and parse fields.
      - Scrape the live match page with requests + BeautifulSoup (use lxml parser).
      - Use an odds API or aggregator to fetch odds and liquidity (requires accounts).
    """
    # >>> EXAMPLE: pseudo-code (do not run)
    # resp = requests.get("https://api.sofascore.com/api/v1/..." , headers=HEADERS, timeout=10)
    # data = resp.json()
    # parse data into list of match dicts...
    raise NotImplementedError("Implement fetch_live_matches_prod() with your data source")

# ---------------------------
# MAIN
# ---------------------------
def main():
    logger.info("EV-Radar starting (MODE=%s) ...", MODE)
    try:
        if MODE == "PROD":
            try:
                matches = fetch_live_matches_prod()
            except NotImplementedError as e:
                logger.error("PROD fetch not implemented: %s", e)
                logger.info("Falling back to DEMO mode.")
                matches = fetch_live_matches_demo()
        else:
            matches = fetch_live_matches_demo()

        # sort by liquidity desc and cap to MAX_GAMES
        matches = sorted(matches, key=lambda m: m.get("liquidity",0), reverse=True)[:MAX_GAMES]

        output_rows = []
        alerts_sent = 0
        for m in matches:
            ev = compute_ev_score(m)
            decision_info = decide_action(m, ev)
            m["ev_score"] = ev
            m["decision"] = decision_info["decision"]
            m["suggestion"] = decision_info["suggestion"]

            row = {
                "league": m.get("league"),
                "home": m.get("home"),
                "away": m.get("away"),
                "minute": m.get("minute"),
                "score": m.get("score"),
                "xg_total": m.get("xg_total"),
                "sot": m.get("sot"),
                "pressure": m.get("pressure"),
                "odds_over25": m.get("odds_over25"),
                "liquidity": m.get("liquidity"),
                "ev_score": m.get("ev_score"),
                "decision": m.get("decision"),
                "suggestion": m.get("suggestion"),
                "timestamp": datetime.utcnow().isoformat()
            }
            output_rows.append(row)

            # alert if ENTER
            if m.get("decision") == "ENTRAR":
                msg = build_message(m)
                ok = send_telegram(msg)
                if ok:
                    alerts_sent += 1

        # save CSV for Numbers / artifact
        save_csv(output_rows)
        logger.info("Processed %d matches. Alerts sent: %d", len(output_rows), alerts_sent)

    except Exception as e:
        logger.exception("Fatal error in main: %s", e)
        sys.exit(1)

if __name__ == "__main__":
    main()
