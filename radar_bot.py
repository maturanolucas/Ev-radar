#!/usr/bin/env python3
# radar_bot.py — EV+ GLOBAL RADAR (multijogo, layout minimalista)
# - Shows up to MAX_GAMES matches with potential (EV >= DISPLAY_THRESHOLD and odds >= ODD_MIN)
# - Orders by EV desc then liquidity
# - Sends a single minimalistic block to Telegram when at least one match qualifies

import os
import sys
import csv
import time
import logging
from datetime import datetime
from typing import List, Dict, Any
import requests

# ---------------------------
# CONFIG / ENV
# ---------------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
ODDS_API_KEY = os.getenv("ODDS_API_KEY")  # optional, used in fetch_live_matches_prod
MODE = os.getenv("MODE", "DEMO").upper()  # DEMO or PROD

# thresholds
EV_THRESHOLD = int(os.getenv("EV_THRESHOLD", "65"))       # threshold to "ENTRAR"
DISPLAY_THRESHOLD = int(os.getenv("DISPLAY_THRESHOLD", "55"))  # threshold to show in block
ODD_MIN = float(os.getenv("ODD_MIN", "1.50"))            # minimum acceptable odd to consider
MAX_GAMES = int(os.getenv("MAX_GAMES", "10"))            # up to 10 matches displayed

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
# SAVE CSV
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
# EV model (same core as before)
# ---------------------------
def compute_ev_score(match: Dict[str, Any]) -> int:
    score = 0.0
    pressure = float(match.get("pressure", 50))  # 0..100
    xg = float(match.get("xg_total", 0.0))
    sot = float(match.get("sot", 0))
    liquidity = float(match.get("liquidity", 0))

    # Pressure -> up to 20 points
    score += (pressure / 100.0) * 20.0

    # xG mapping (0..3) -> up to 30 points
    score += min(xg / 3.0, 1.0) * 30.0

    # SOT -> up to 20 points (10 SOT => full)
    score += min(sot / 10.0, 1.0) * 20.0

    # Liquidity proxy bonus -> up to 10
    try:
        score += min(liquidity / 3_000_000.0, 1.0) * 10.0
    except Exception:
        pass

    # Context static placeholders (tunable)
    score += 6.0  # importance/motivation baseline
    score += 4.0  # historical tendency baseline

    score = max(0.0, min(100.0, score))
    return int(round(score))

# ---------------------------
# Decision
# ---------------------------
def decide_action(match: Dict[str, Any], ev_score: int) -> Dict[str,str]:
    dec = "IGNORAR"
    suggestion = "Sem stake"
    odd = match.get("odds_over25")
    try:
        odd_val = float(odd) if odd is not None else 0.0
    except Exception:
        odd_val = 0.0

    if ev_score >= EV_THRESHOLD and odd_val >= ODD_MIN:
        dec = "ENTRAR"
        suggestion = "Stake 1% (ajustar)"
    elif DISPLAY_THRESHOLD <= ev_score < EV_THRESHOLD:
        dec = "MONITORAR"
        suggestion = "Sem stake"
    else:
        dec = "IGNORAR"
        suggestion = "Sem stake"
    return {"decision": dec, "suggestion": suggestion}

# ---------------------------
# Message builder: single minimal block with up to MAX_GAMES entries
# ---------------------------
def build_message_block(matches: List[Dict[str, Any]]) -> str:
    header = "══════════ ⚽️ EV+ GLOBAL RADAR ══════════"
    lines = [header]
    # each match formatted in compact block
    for i, m in enumerate(matches, start=1):
        league = m.get("league", "")
        home = m.get("home", "")
        away = m.get("away", "")
        minute = m.get("minute", "")
        score = m.get("score", "")
        xg = m.get("xg_total", "–")
        sot = m.get("sot", "–")
        pressure = m.get("pressure", "–")
        odd = m.get("odds_over25", "N/A")
        liq = m.get("liquidity", 0)
        ev = m.get("ev_score", 0)
        decision = m.get("decision", "IGNORAR")
        suggestion = m.get("suggestion", "Sem stake")

        # One match block (3 lines)
        lines.append(f"#{i} {league} — {home} {score} {away} | {minute}’")
        lines.append(f"xG: {float(xg) if isinstance(xg,(int,float)) else xg:.2f} | SOT: {sot} | Pressão: {pressure}%")
        lines.append(f"Odd: {odd} | Liquidez: £{int(liq):,}")
        lines.append(f"SCORE EV+: {ev}/100 — {decision}")
        lines.append(f"👉 {suggestion}")
        lines.append("")  # blank separator

    lines.append("════════════════════════════════════════")
    return "\n".join(lines)

# ---------------------------
# Demo data provider
# ---------------------------
def fetch_live_matches_demo() -> List[Dict[str, Any]]:
    demo = [
        {"id":"m1","league":"Ligue 1","home":"Marseille","away":"Angers","minute":74,"score":"2-1",
         "xg_total":1.52,"sot":8,"pressure":77,"odds_over25":1.50,"liquidity":2300000},
        {"id":"m2","league":"Serie A","home":"Inter","away":"Fiorentina","minute":65,"score":"1-0",
         "xg_total":1.85,"sot":8,"pressure":74,"odds_over25":1.82,"liquidity":2900000},
        {"id":"m3","league":"Copa Libertadores","home":"Racing","away":"Flamengo","minute":44,"score":"0-0",
         "xg_total":0.46,"sot":3,"pressure":58,"odds_over25":1.68,"liquidity":280000},
        # add more demo rows if needed
    ]
    return demo[:MAX_GAMES]

# ---------------------------
# PRODUCTION: placeholder / integrate your fetch_live_matches_prod()
# ---------------------------
def fetch_live_matches_prod() -> List[Dict[str, Any]]:
    """
    Replace this with your Sofascore + odds provider implementation.
    Should return a list of dicts with the fields used in demo.
    """
    # The previously provided robust function can be pasted here.
    raise NotImplementedError("Implement fetch_live_matches_prod() to fetch real live matches")

# ---------------------------
# MAIN FLOW
# ---------------------------
def main():
    logger.info("EV-Radar starting (MODE=%s) ...", MODE)
    try:
        if MODE == "PROD":
            try:
                matches = fetch_live_matches_prod()
            except NotImplementedError as e:
                logger.error("PROD fetch not implemented: %s", e)
                logger.info("Falling back to DEMO")
                matches = fetch_live_matches_demo()
        else:
            matches = fetch_live_matches_demo()

        # compute EVs
        processed = []
        for m in matches:
            ev = compute_ev_score(m)
            m["ev_score"] = ev
            decinfo = decide_action(m, ev)
            m["decision"] = decinfo["decision"]
            m["suggestion"] = decinfo["suggestion"]
            processed.append(m)

        # filter: show only matches with EV >= DISPLAY_THRESHOLD and odds >= ODD_MIN
        def valid_for_display(m):
            try:
                odd = float(m.get("odds_over25")) if m.get("odds_over25") is not None else 0.0
            except Exception:
                odd = 0.0
            return (m.get("ev_score", 0) >= DISPLAY_THRESHOLD) and (odd >= ODD_MIN)

        candidates = [m for m in processed if valid_for_display(m)]

        # sort by ev desc then liquidity desc
        candidates = sorted(candidates, key=lambda x: (x.get("ev_score",0), x.get("liquidity",0)), reverse=True)[:MAX_GAMES]

        # If there are candidates, build block and send single message
        if candidates:
            # re-evaluate decisions for display: ENTAR if ev>=EV_THRESHOLD and odd>=ODD_MIN
            for c in candidates:
                ev = c.get("ev_score",0)
                c.update(decide_action(c, ev))
            # build single block
            msg = build_message_block(candidates)
            send_telegram(msg)
        else:
            logger.info("No candidates with EV >= %d and odd >= %.2f", DISPLAY_THRESHOLD, ODD_MIN)

        # Save CSV with all processed (for record/Numbers)
        save_csv(processed)

        logger.info("Run complete. Candidates shown: %d", len(candidates))
    except Exception as e:
        logger.exception("Fatal error: %s", e)
        sys.exit(1)

if __name__ == "__main__":
    main()
