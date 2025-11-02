# rainbot_playwright.py
# ---------------------------------------------------
# Banditcamp Rain notifier (Render-ready)
# - Health endpoint op $PORT (voor uptime/keepalive)
# - Discord webhook via env var WEBHOOK_URL
# - Standaard check met requests; Playwright optioneel (USE_PLAYWRIGHT=1)
# - Playwright start met --no-sandbox (vereist in containers)
# ---------------------------------------------------

import os
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import requests

VERSION = "RainBot v6 (Render-ready)"
CHECK_URL = os.getenv("CHECK_URL", "https://bandit.camp")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "30"))
WEBHOOK_URL = os.getenv("https://discordapp.com/api/webhooks/1434470166481338519/7c_bwalFDEkz3Q2f2O9PZgkC79DP2_qnp2eBDrATtohSd560kQnc-u2p1F3564wUpDhJ")  # <-- zet op Render als env var
TIMEOUT_SEC = int(os.getenv("TIMEOUT_SEC", "20"))
USE_PLAYWRIGHT = os.getenv("USE_PLAYWRIGHT", "0").strip() in ("1", "true", "True")

# Pas deze woorden aan op echte signalen die op de site staan bij 'rain'
TRIGGERS = ["rain", "join rain", "rain event", "rain pot", "raining"]

# -----------------------
# Health HTTP server
# -----------------------
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/health"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()

def start_health_server(port: int):
    server = HTTPServer(("", port), HealthHandler)
    print(f"[INFO] Health server luistert op :{port} (GET /health)")
    threading.Thread(target=server.serve_forever, daemon=True).start()

# -----------------------
# Discord helper
# -----------------------
def send_discord(msg: str):
    if not WEBHOOK_URL:
        print("[WARN] WEBHOOK_URL ontbreekt (zet deze env var op Render).")
        return
    try:
        r = requests.post(WEBHOOK_URL, json={"content": msg}, timeout=10)
        if r.status_code >= 300:
            print(f"[ERR] Discord response {r.status_code}: {r.text[:500]}")
        else:
            print("[INFO] Discord-bericht verstuurd.")
    except Exception as e:
        print(f"[ERR] Fout bij posten naar Discord: {e}")

# -----------------------
# Trigger matching
# -----------------------
def _match_triggers(text: str) -> bool:
    t = text.lower()
    return any(trigger in t for trigger in TRIGGERS)

# -----------------------
# Checkers
# -----------------------
def check_with_requests() -> bool:
    try:
        print(f"[DBG] Requests check -> {CHECK_URL}")
        r = requests.get(CHECK_URL, timeout=TIMEOUT_SEC, headers={"User-Agent": VERSION})
        r.raise_for_status()
        return _match_triggers(r.text)
    except Exception as e:
        print(f"[ERR] Requests-check gefaald: {e}")
        return False

def check_with_playwright() -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        print(f"[ERR] Playwright import mislukt: {e}")
        return False

    try:
        print(f"[DBG] Playwright check -> {CHECK_URL}")
        with sync_playwright() as p:
            # Belangrijk op Render/containers: --no-sandbox
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(TIMEOUT_SEC * 1000)
            page.goto(CHECK_URL, wait_until="domcontentloaded")
            html = page.content()
            browser.close()
            return _match_triggers(html)
    except Exception as e:
        print(f"[ERR] Playwright-check gefaald: {e}")
        return False

# -----------------------
# Main loop
# -----------------------
def main_loop():
    print(f"[INFO] Start {VERSION}")
    print(f"[INFO] CHECK_URL={CHECK_URL} | POLL_SECONDS={POLL_SECONDS} | USE_PLAYWRIGHT={USE_PLAYWRIGHT}")
    if not WEBHOOK_URL:
        print("[WARN] Geen WEBHOOK_URL gezet — er worden geen Discord-meldingen verstuurd.")

    checker = check_with_playwright if USE_PLAYWRIGHT else check_with_requests
    already_notified = False

    while True:
        try:
            has_rain = checker()
            if has_rain and not already_notified:
                send_discord("🌧️ **Rain gedetecteerd op bandit.camp!** Ga nu kijken/joinen.")
                already_notified = True
                print("[INFO] Rain gedetecteerd -> melding gestuurd.")
            elif not has_rain and already_notified:
                print("[INFO] Rain lijkt voorbij -> reset notification state.")
                already_notified = False
        except Exception as loop_err:
            print(f"[ERR] Onverwachte loop-fout: {loop_err}")
        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    # Health server op de poort die Render meegeeft
    port = int(os.getenv("PORT", "10000"))
    start_health_server(port=port)
    main_loop()

