# rainbot_playwright.py
# ---------------------------------------------------
# Banditcamp Rain notifier (Playwright) + health server
# Works on Render Free Web Service (no Background Worker needed)
# ---------------------------------------------------

import os
import time
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests
from playwright.sync_api import sync_playwright

# ====== CONFIG ======
VERSION       = "RainBot-English-v3 (Render + health)"
CHECK_URL     = "https://bandit.camp"      # page to check
POLL_SECONDS  = 20                          # how often to poll
TIMEOUT_SEC   = 25                          # page load / selector timeouts

# --- Discord webhook (REQUIRED) ---
WEBHOOK_URL   = "PUT_YOUR_DISCORD_WEBHOOK_URL_HERE"

# Mentions — choose ONE: everyone OR a role
PING_EVERYONE = False                       # set True to ping @everyone
ROLE_ID       = ""                          # e.g. "123456789012345678" (leave "" if unused)

# ====== HEALTH SERVER (no Flask needed) ======
# Render's Free Web Service expects a listening port.
# This tiny HTTP server keeps the service 'UP' and fixes 502/no-open-ports.
class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"RainBot OK")
    def log_message(self, *args, **kwargs):
        return  # silence default logging

def start_health_server():
    port = int(os.environ.get("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"[health] listening on :{port}")

# ====== DISCORD ======
def send_discord(content: str):
    if not WEBHOOK_URL or WEBHOOK_URL.startswith("PUT_"):
        print("[discord] Missing WEBHOOK_URL – please set it in the file.")
        return

    data = {"content": content}
    try:
        r = requests.post(WEBHOOK_URL, json=data, timeout=15)
        r.raise_for_status()
        print("[discord] sent")
    except Exception as e:
        print(f"[discord] error: {e}")

def build_mention_prefix() -> str:
    if PING_EVERYONE:
        return "@everyone "
    if ROLE_ID:
        return f"<@&{ROLE_ID}> "
    return ""

# ====== RAIN DETECTION ======
def is_rain_live(page) -> bool:
    """
    Tries multiple strategies:
    - Visible text like 'JOIN RAIN EVENT' or 'Rakeback Rain'
    - Presence of the join button
    """
    try:
        # quick contains-text checks
        txt = page.inner_text("body", timeout=TIMEOUT_SEC).lower()
        needles = [
            "join rain event",
            "rakeback rain",
            "rain event is live",
            "join now to get free scrap",
        ]
        if any(n in txt for n in needles):
            return True
    except Exception:
        pass

    # Try a few likely selectors for the join button/badge
    candidates = [
        "text=JOIN RAIN EVENT",
        "button:has-text('JOIN RAIN EVENT')",
        "[data-test*='rain']",
        "text=Rakeback Rain",
    ]
    for sel in candidates:
        try:
            el = page.query_selector(sel, timeout=2000)
            if el:
                return True
        except Exception:
            continue

    return False

# ====== MAIN LOOP ======
def run():
    print(f"[bot] starting → {CHECK_URL} | {VERSION}")
    last_seen_live = False

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
        context = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"),
            viewport={"width": 1366, "height": 768},
        )
        page = context.new_page()

        while True:
            try:
                page.goto(CHECK_URL, wait_until="domcontentloaded", timeout=TIMEOUT_SEC * 1000)
            except Exception as e:
                print(f"[check] load error: {e}")
                time.sleep(POLL_SECONDS)
                continue

            live = False
            try:
                live = is_rain_live(page)
            except Exception as e:
                print(f"[check] detect error: {e}")

            if live and not last_seen_live:
                msg = f"{build_mention_prefix()}**Rain event is live!** → {CHECK_URL}"
                print("[state] RAIN DETECTED → discord")
                send_discord(msg)
                last_seen_live = True
            elif (not live) and last_seen_live:
                print("[state] rain ended → reset")
                last_seen_live = False
            else:
                print("[state] no rain…")

            time.sleep(POLL_SECONDS)

# ====== ENTRYPOINT ======
if __name__ == "__main__":
    start_health_server()  # keeps Render Web Service happy
    try:
        run()
    except KeyboardInterrupt:
        print("[bot] stopped by user")
