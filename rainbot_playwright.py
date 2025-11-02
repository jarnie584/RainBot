# rainbot_playwright.py
# ---------------------------------------------------
# Banditcamp Rain notifier (Playwright) + health server
# Works on Render Free Web Service (no Background Worker needed)
# Starts health server immediately, installs Chromium from Python.
# ---------------------------------------------------

import os
import time
import threading
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests
from playwright.sync_api import sync_playwright

# ====== CONFIG ======
VERSION       = "RainBot-English-v4 (health-first + in-code install)"
CHECK_URL     = "https://bandit.camp"
POLL_SECONDS  = 20
TIMEOUT_SEC   = 25

# --- Discord webhook (REQUIRED) ---
WEBHOOK_URL   = "<<< ZET HIER JE NIEUWE WEBHOOK >>>"  # vervang dit!

# Mentions — choose ONE: everyone OR a role
PING_EVERYONE = False
ROLE_ID       = ""   # bv. "123456789012345678"

# ====== HEALTH SERVER (no Flask) ======
class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"RainBot OK")
    def log_message(self, *args, **kwargs):
        return

def start_health_server():
    port = int(os.environ.get("PORT", "10000"))
    srv = HTTPServer(("0.0.0.0", port), _HealthHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"[health] listening on :{port}")

# ====== ONE-TIME BROWSER INSTALL (from code) ======
def ensure_chromium_installed():
    # Zorg dat de health server al draait, dan kan Render niet klagen.
    print("[setup] installing Playwright Chromium (this may take ~1 min)")
    try:
        subprocess.run(
            ["python", "-m", "playwright", "install", "chromium"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        print("[setup] Chromium installed")
    except subprocess.CalledProcessError as e:
        print("[setup] Chromium install FAILED:")
        print(e.stdout)

# ====== DISCORD ======
def build_mention_prefix() -> str:
    if PING_EVERYONE:
        return "@everyone "
    if ROLE_ID:
        return f"<@&{ROLE_ID}> "
    return ""

def send_discord(content: str):
    if not WEBHOOK_URL or WEBHOOK_URL.startswith("<<<"):
        print("[discord] Missing WEBHOOK_URL – set it at the top.")
        return
    try:
        r = requests.post(WEBHOOK_URL, json={"content": content}, timeout=15)
        r.raise_for_status()
        print("[discord] sent")
    except Exception as e:
        print(f"[discord] error: {e}")

# ====== RAIN DETECTION ======
def is_rain_live(page) -> bool:
    try:
        txt = page.inner_text("body", timeout=TIMEOUT_SEC).lower()
        for needle in [
            "join rain event",
            "rakeback rain",
            "rain event is live",
            "join now to get free scrap",
        ]:
            if needle in txt:
                return True
    except Exception:
        pass
    for sel in [
        "text=JOIN RAIN EVENT",
        "button:has-text('JOIN RAIN EVENT')",
        "[data-test*='rain']",
        "text=Rakeback Rain",
    ]:
        try:
            if page.query_selector(sel, timeout=2000):
                return True
        except Exception:
            pass
    return False

# ====== MAIN LOOP ======
def run():
    print(f"[bot] starting → {CHECK_URL} | {VERSION}")
    last_seen_live = False
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
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
    # 1) Poort meteen open: Render blij
    start_health_server()
    # 2) Chromium installeren terwijl poort al open is
    ensure_chromium_installed()
    # 3) Daarna de bot starten
    try:
        run()
    except KeyboardInterrupt:
        print("[bot] stopped by user")
